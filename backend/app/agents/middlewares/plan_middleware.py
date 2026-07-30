"""
计划模式中间件

用于管理复杂多步骤任务的 TodoList 跟踪。
"""
import logging
import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


class PlanMiddleware(AgentMiddleware):
    """
    计划模式中间件

    功能：
    1. 初始化 TodoList 状态
    2. 从消息中提取任务标记
    3. 跟踪任务状态 (pending/in_progress/completed)
    """

    def before_agent(self, state: dict, runtime: Runtime) -> dict | None:
        """
        模型调用前处理

        初始化 TodoList 如果不存在
        """
        updates = {}

        # 初始化 TodoList
        if "todo_list" not in state:
            updates["todo_list"] = []

        if "completed_tasks" not in state:
            updates["completed_tasks"] = []

        if "plan" not in state:
            updates["plan"] = []

        return updates if updates else None

    def after_agent(self, state: dict, runtime: Runtime) -> dict | None:
        """
        模型调用后处理

        从消息中提取任务标记 [TASK]...[/TASK]
        """
        messages = state.get("messages", [])
        if not messages:
            return None

        # 获取最后一条消息
        last_msg = messages[-1]
        content = str(getattr(last_msg, "content", ""))

        updates = {}

        # 提取任务
        if "[TASK]" in content:
            tasks = re.findall(r"\[TASK\](.*?)\[/TASK\]", content, re.DOTALL)
            todo_list = state.get("todo_list", [])

            for task in tasks:
                task_item = {
                    "description": task.strip(),
                    "status": "pending",
                }
                # 避免重复
                if task_item not in todo_list:
                    todo_list.append(task_item)

            updates["todo_list"] = todo_list
            logger.info("[PlanMiddleware] Extracted %d tasks", len(tasks))

        return updates if updates else None
