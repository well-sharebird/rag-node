"""思考过程（reasoning）与最终答案流分离测试。

后端把模型的 reasoning_content / reasoning 与 content 分开产出并打标
（additional_kwargs["reasoning"]=True），使前端能按不同样式渲染思考块与答案。
核心逻辑在 `_astream`（agent_runtime_service.py）。用一个假 httpx AsyncClient
回放 SSE 行，验证 reasoning chunk 打标、answer chunk 不打标。
"""
import pytest
from langchain_core.messages import HumanMessage

from packages.agent.services.agent_runtime_service import create_langchain_llm


class _FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeClient:
    def __init__(self, lines):
        self._resp = _FakeStreamResponse(lines)

    def stream(self, method, url, **kwargs):
        # httpx 的 stream() 返回上下文管理器本身（非协程），async with 直接接管
        return self._resp


class _Cfg:
    model = "test-model"
    provider = ""  # 走默认 OpenAI 兼容分支（SimpleChatHttp）
    temperature = 0.7
    max_tokens = 256
    top_p = 1.0


def _sse(lines):
    return [f"data: {line}" if not line.startswith("data:") else line for line in lines]


@pytest.mark.asyncio
async def test_astream_separates_reasoning_from_answer():
    lines = _sse([
        '{"choices":[{"delta":{"reasoning_content":"想"}}]}',
        '{"choices":[{"delta":{"reasoning_content":"法"}}]}',
        '{"choices":[{"delta":{"content":"答"}}]}',
        '{"choices":[{"delta":{"content":"案"}}]}',
        "[DONE]",
    ])
    llm = await create_langchain_llm(_Cfg())
    llm._client = _FakeClient(lines)

    chunks = []
    async for c in llm._astream([HumanMessage(content="hi")]):
        chunks.append(c.message)

    assert len(chunks) == 4
    # 思考片段：打标 reasoning，content 承载思考文本
    assert chunks[0].additional_kwargs.get("reasoning") is True
    assert chunks[0].content == "想"
    assert chunks[1].additional_kwargs.get("reasoning") is True
    assert chunks[1].content == "法"
    # 答案片段：不打标
    assert chunks[2].additional_kwargs.get("reasoning") is None
    assert chunks[2].content == "答"
    assert chunks[3].additional_kwargs.get("reasoning") is None
    assert chunks[3].content == "案"


@pytest.mark.asyncio
async def test_astream_plain_answer_has_no_reasoning_tag():
    # 无 reasoning 的普通模型：全部作为答案输出，不打标（不回归现状）
    lines = _sse([
        '{"choices":[{"delta":{"content":"hi"}}]}',
        "[DONE]",
    ])
    llm = await create_langchain_llm(_Cfg())
    llm._client = _FakeClient(lines)

    chunks = []
    async for c in llm._astream([HumanMessage(content="hi")]):
        chunks.append(c.message)

    assert len(chunks) == 1
    assert chunks[0].additional_kwargs.get("reasoning") is None
    assert chunks[0].content == "hi"


@pytest.mark.asyncio
async def test_astream_reasoning_field_fallback():
    # 有的模型用 reasoning 而非 reasoning_content
    lines = _sse([
        '{"choices":[{"delta":{"reasoning":"想"}}]}',
        '{"choices":[{"delta":{"content":"答"}}]}',
        "[DONE]",
    ])
    llm = await create_langchain_llm(_Cfg())
    llm._client = _FakeClient(lines)

    chunks = []
    async for c in llm._astream([HumanMessage(content="hi")]):
        chunks.append(c.message)

    assert chunks[0].additional_kwargs.get("reasoning") is True
    assert chunks[0].content == "想"
    assert chunks[1].additional_kwargs.get("reasoning") is None
    assert chunks[1].content == "答"
