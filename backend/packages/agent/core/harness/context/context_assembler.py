"""上下文组装器 - 多轮对话上下文管理（设计文档 2.1）

职责：
1. 管理多轮对话历史
2. 上下文去重、污染检测
3. 对话摘要生成
"""
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class ContextAssembler:
    """上下文组装器

    将对话历史、Agent 配置、任务指令组装为 LangGraph State 可接受的 messages 格式
    """

    def __init__(self, max_turns: int = 50):
        self.max_turns = max_turns
        self._messages: List[Dict[str, str]] = []

    def add_message(self, role: str, content: str):
        """添加单条消息

        Args:
            role: "user" | "assistant" | "system"
            content: 消息内容
        """
        self._messages.append({"role": role, "content": content})
        # 保持最大轮数限制
        if len(self._messages) > self.max_turns * 2:  # 每轮=user+assistant
            self._messages = self._messages[-self.max_turns * 2:]

    def add_messages(self, messages: List[Dict[str, str]]):
        """批量添加消息"""
        for msg in messages:
            self.add_message(msg.get("role", "user"), msg.get("content", ""))

    def get_messages(self) -> List[Dict[str, str]]:
        """获取当前消息列表"""
        return list(self._messages)

    def clear(self):
        """清空上下文"""
        self._messages = []

    def deduplicate(self) -> List[Dict[str, str]]:
        """去重：移除连续重复的用户消息

        场景：用户重复提交相同问题
        """
        if not self._messages:
            return []

        result = [self._messages[0]]
        for i in range(1, len(self._messages)):
            curr = self._messages[i]
            prev = result[-1]
            # 如果连续两条都是 user 消息且内容相同，跳过
            if curr["role"] == "user" and prev["role"] == "user" and curr["content"] == prev["content"]:
                continue
            result.append(curr)

        return result

    def detect_pollution(self) -> Optional[str]:
        """检测上下文污染

        污染类型：
        1. 注入攻击：检测到"忽略之前指令"等关键词
        2. 角色混淆：用户消息中包含"你是 XXX"试图改写 Agent 人格

        Returns:
            污染类型描述，无污染返回 None
        """
        injection_patterns = [
            "忽略之前的指令",
            "ignore previous instructions",
            "忘记上面的规则",
            "system:",
            "你现在是",
        ]

        for msg in self._messages[-10:]:  # 只检查最近 10 条
            if msg["role"] == "user":
                content = msg["content"].lower()
                for pattern in injection_patterns:
                    if pattern.lower() in content:
                        return f"检测到潜在的提示词注入：{pattern}"

        return None

    def to_langchain_messages(self) -> List[Any]:
        """转换为 LangChain BaseMessage 列表

        供 LangGraph/LangChain 使用
        """
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

        result = []
        for msg in self._messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                result.append(SystemMessage(content=content))
            elif role == "assistant":
                result.append(AIMessage(content=content))
            else:
                result.append(HumanMessage(content=content))
        return result

    def summarize(self, llm=None) -> str:
        """生成上下文摘要

        Args:
            llm: 可选的 LLM 实例，用于生成摘要

        Returns:
            摘要字符串
        """
        if not self._messages:
            return ""

        # 简单实现：取最近 3 轮对话的关键信息
        recent = self._messages[-6:]  # 最近 3 轮
        user_msgs = [m["content"] for m in recent if m["role"] == "user"]
        assistant_msgs = [m["content"] for m in recent if m["role"] == "assistant"]

        if llm:
            # 使用 LLM 生成摘要
            try:
                summary_prompt = f"""请总结以下对话的关键信息：

用户问题：{"；".join(user_msgs[-3:])}
助手回答：{"；".join(assistant_msgs[-3:])}

请用一句话总结核心内容："""
                response = llm.invoke(summary_prompt)
                return str(response.content)
            except Exception as e:
                logger.warning(f"LLM 摘要失败，降级为简单拼接：{e}")

        # 降级：简单拼接
        return f"用户询问：{user_msgs[-1] if user_msgs else '无'}"
