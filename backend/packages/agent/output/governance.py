"""输出治理节点"""
from typing import Any
import logging

logger = logging.getLogger(__name__)


class OutputGovernanceNode:
    """输出治理节点 — 作为 LangGraph 图的最后一个节点"""

    def __init__(self, llm=None, enable_structured: bool = False):
        self.llm = llm
        self.enable_structured = enable_structured
        self._filters = None

    def _init_filters(self):
        from .filters import get_filters
        self._filters = get_filters()

    @property
    def filters(self):
        if self._filters is None:
            self._init_filters()
        return self._filters

    async def __call__(self, state: dict) -> dict:
        """LangGraph 节点入口"""
        from .schema import AgentOutput, GovernanceResult

        raw_output = self._extract_raw_output(state)

        # Step 1: 结构化（可选）
        if self.enable_structured and self.llm:
            structured = await self._structure_output(raw_output)
        else:
            structured = AgentOutput(answer=raw_output)

        # Step 2: 内容过滤
        filtered_answer, filtered_items = self._apply_filters(structured.answer)
        structured.answer = filtered_answer

        # Step 3: 置信度检查
        warnings = []
        if structured.confidence < 0.3:
            warnings.append("低置信度回答，建议人工复核")

        # Step 4: 组装结果
        result = GovernanceResult(
            output=structured,
            filtered=bool(filtered_items),
            filtered_content=filtered_items,
            warnings=warnings,
            passed=True,
        )

        return {
            **state,
            "final_output": result.output.answer,
            "governance_result": result.model_dump(),
        }

    def _extract_raw_output(self, state: dict) -> str:
        """从 State 中提取原始输出"""
        messages = state.get("messages", [])
        if not messages:
            return ""
        last = messages[-1]
        return last.content if hasattr(last, "content") else str(last)

    async def _structure_output(self, raw: str):
        """用 LLM 将原始输出结构化"""
        from .schema import AgentOutput
        try:
            structured_llm = self.llm.with_structured_output(AgentOutput)
            return await structured_llm.ainvoke(
                f"将以下回答结构化:\n\n{raw}"
            )
        except Exception as e:
            logger.warning(f"结构化失败，降级为纯文本：{e}")
            return AgentOutput(answer=raw, confidence=0.5)

    def _apply_filters(self, text: str) -> tuple[str, list[str]]:
        """依次应用所有过滤器"""
        all_filtered = []
        for f in self.filters:
            text, filtered = f.check(text)
            all_filtered.extend(filtered)
        return text, all_filtered
