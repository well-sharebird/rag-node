"""
#3 完整 HITL 断点续跑 与 #8 每子 Agent 审计 测试

- resume_sub_agent：mock 图（`_build_agent_graph`）分别走成功与 GraphInterrupt 两路，
  验证续跑入口按 thread_id 重建图续跑、中断时 approvals 附 thread_id；
- _save_execution_trace：验证 steps 内含每子 Agent 独立审计条目
  （id/success/content 摘要/approvals 数/thread_id），而非只记 id。
"""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import app.models  # noqa: F401  （满足 SQLAlchemy mapper 顺序）

from packages.agent.orchestrator.graph import OrchestratorRuntime
from packages.agent.orchestrator.agent_loader import LoadedAgentConfig


def _loaded_config():
    return LoadedAgentConfig(
        agent_id="sub-a", name="SubA", system_prompt="sys",
        tools_whitelist=["search"],
        sandbox_policy={}, require_approval_tools=["save_workspace_file"],
        max_step=3, inherit_main_context=False,
    )


class _Config:
    recursion_limit = 25
    timeout_seconds = 60


@pytest.mark.asyncio
async def test_resume_continues_from_checkpoint_success():
    from langchain_core.messages import AIMessage

    rt = OrchestratorRuntime.__new__(OrchestratorRuntime)
    rt.loader = SimpleNamespace(load_sub_agent=AsyncMock(return_value=_loaded_config()))
    rt.config = _Config()
    rt._create_llm = AsyncMock(return_value="llm")
    rt._load_sub_tools = lambda wl: []
    rt._get_checkpointer = lambda: "ckp"  # 有 HITL 时启用

    class FakeGraph:
        async def ainvoke(self, inp, config=None):
            self.seen_config = config
            return {"messages": [AIMessage(content="断点续跑完成")]}

    fg = FakeGraph()
    rt._build_agent_graph = lambda **kw: fg

    res = await rt.resume_sub_agent("sub-a", "1:sub-a:123")
    assert res["success"] is True
    assert res["content"] == "断点续跑完成"
    assert res["thread_id"] == "1:sub-a:123"
    # 续跑用 None 输入 + 原 thread_id 从断点恢复
    assert fg.seen_config["configurable"]["thread_id"] == "1:sub-a:123"


@pytest.mark.asyncio
async def test_resume_interrupt_attaches_thread_id_to_approval():
    from langgraph.errors import GraphInterrupt

    rt = OrchestratorRuntime.__new__(OrchestratorRuntime)
    rt.loader = SimpleNamespace(load_sub_agent=AsyncMock(return_value=_loaded_config()))
    rt.config = _Config()
    rt._create_llm = AsyncMock(return_value="llm")
    rt._load_sub_tools = lambda wl: []
    rt._get_checkpointer = lambda: "ckp"

    class FakeGraph:
        async def ainvoke(self, inp, config=None):
            exc = GraphInterrupt()
            exc.value = {
                "pending": [
                    {"tool": "save_workspace_file", "request_id": "r1",
                     "risk_level": "high"},
                ],
            }
            raise exc

    rt._build_agent_graph = lambda **kw: FakeGraph()

    res = await rt.resume_sub_agent("sub-a", "1:sub-a:123")
    assert res["approvals"][0]["request_id"] == "r1"
    # #3b：审批事件携带恢复定位 thread_id
    assert res["approvals"][0]["thread_id"] == "1:sub-a:123"
    assert res["success"] is True


class _TraceDB:
    def __init__(self):
        self.added = None

    def add(self, obj):
        self.added = obj

    async def commit(self):
        pass

    async def rollback(self):
        pass


@pytest.mark.asyncio
async def test_execution_trace_has_per_sub_audit_entries():
    rt = OrchestratorRuntime.__new__(OrchestratorRuntime)
    db = _TraceDB()
    rt.db = db

    await rt._save_execution_trace(
        run_id="r1", query="q", intent="intent", final_output="终答",
        sub_agents=["sub-a"], user_id=1,
        sub_results=[
            {
                "sub_agent_id": "sub-a", "success": True,
                "content": "子Agent干了活", "error": None,
                "approvals": [{"request_id": "r1", "thread_id": "1:sub-a:9"}],
            },
            {
                "sub_agent_id": "sub-b", "success": False,
                "content": "", "error": "失败原因",
                "approvals": [],
            },
        ],
    )

    assert db.added is not None
    entries = db.added.steps[0]["sub_agent_results"]
    assert len(entries) == 2
    a = entries[0]
    assert a["sub_agent_id"] == "sub-a"
    assert a["success"] is True
    assert a["content_summary"] == "子Agent干了活"
    assert a["approval_count"] == 1
    assert a["thread_id"] == "1:sub-a:9"
    b = entries[1]
    assert b["success"] is False
    assert b["error"] == "失败原因"
    assert b["approval_count"] == 0
