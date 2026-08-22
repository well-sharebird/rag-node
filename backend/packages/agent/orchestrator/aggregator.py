"""Result Aggregator - 负责结果的聚合。

职责:
- 流式聚合子 Agent 结果
- 非流式聚合子 Agent 结果
- PII 脱敏处理
"""

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# Prompts
AGGREGATE_PROMPT = """你是一个结果聚合助手。请将多个子 Agent 的执行结果整合为一个连贯的回答。

子 Agent 结果:
{results}

请:
1. 总结各子 Agent 的贡献
2. 整合为一个连贯的回答
3. 避免重复和矛盾
4. 保持逻辑清晰
"""


def redact_block(redactor: Optional[Any], block: str) -> str:
    """对文本块进行 PII 脱敏。
    
    Args:
        redactor: PII 脱敏器
        block: 待脱敏文本
        
    Returns:
        str: 脱敏后的文本
    """
    if redactor is None:
        return block
    try:
        return redactor.push(block) + redactor.flush()
    except Exception:
        return block


class ResultAggregator:
    """结果聚合器。
    
    职责:
    - 流式聚合子 Agent 结果
    - 非流式聚合子 Agent 结果
    - PII 脱敏处理
    """
    
    def __init__(self, llm: Any):
        """初始化 ResultAggregator。
        
        Args:
            llm: LLM 实例
        """
        self.llm = llm
    
    async def aggregate_stream(
        self,
        results: List[Any],  # List[SubAgentResult]
        main_prompt: str,
        redactor: Optional[Any] = None
    ):
        """流式聚合：逐 token 产出最终回答。
        
        修复：移除流式 PII 脱敏，因为会破坏跨 token 的敏感信息匹配并阻塞流式输出。
        移除子 Agent 内容的截断，确保聚合时使用完整内容。
        
        Args:
            results: 子 Agent 结果列表
            main_prompt: 主提示词
            redactor: PII 脱敏器（可选，当前不使用）
            
        Yields:
            str: 聚合后的文本块
        """
        # ✅ 移除子 Agent 内容的截断，确保聚合时使用完整内容
        results_text = json.dumps(
            [
                {
                    "sub_agent_id": r.sub_agent_id,
                    "success": r.success,
                    "content": str(r.content),
                    "error": r.error
                }
                for r in results
            ],
            ensure_ascii=False
        )
        
        prompt = AGGREGATE_PROMPT.replace("{results}", results_text)
        msgs = [
            SystemMessage(content=main_prompt),
            HumanMessage(content=prompt)
        ]

        try:
            async for chunk in self.llm.astream(msgs):
                c = getattr(chunk, "content", "") or ""
                if c:
                    # ✅ 直接返回原文，不阻塞流式输出
                    yield str(c)
        except Exception as e:
            logger.error("[ResultAggregator] 流式聚合失败，降级：%s", e)
            # 降级为一次性汇总
            parts = [
                f"[{r.sub_agent_id}] {r.content if r.success else '执行失败：' + str(r.error)}"
                for r in results
            ]
            block = "以下为子 Agent 执行结果汇总：\n" + "\n".join(parts)
            # ✅ 直接返回完整内容，不进行 PII 脱敏
            yield block
    
    def aggregate_blocking(
        self,
        results: List[Any],  # List[SubAgentResult]
        main_prompt: str,
        redactor: Optional[Any] = None
    ) -> str:
        """非流式聚合：一次性返回聚合结果。
        
        Args:
            results: 子 Agent 结果列表
            main_prompt: 主提示词
            redactor: PII 脱敏器（可选）
            
        Returns:
            str: 聚合后的文本
        """
        # 简单实现：直接拼接结果
        parts = []
        for r in results:
            if r.success:
                parts.append(f"[{r.sub_agent_id}] {r.content}")
            else:
                parts.append(f"[{r.sub_agent_id}] 执行失败：{r.error}")
        
        result = "\n\n".join(parts)
        
        if redactor is not None:
            result = redactor.push(result) + redactor.flush()
        
        return result
