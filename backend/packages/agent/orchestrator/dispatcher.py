"""Task Dispatcher - 负责子任务的执行和调度。

职责:
- 执行单个子 Agent 任务
- 运行子 Agent 图
- 加载子工具
- 管理子 Agent 配置和沙箱
"""

import logging
from typing import Any, Dict, List, Optional

from packages.agent.orchestrator.state import SubAgentResult

logger = logging.getLogger(__name__)


class TaskDispatcher:
    """任务调度器。
    
    职责:
    - 执行单个子 Agent 任务
    - 运行子 Agent 图
    - 加载子工具
    - 管理子 Agent 配置和沙箱
    """
    
    def __init__(self, orchestrator):
        """初始化 TaskDispatcher。
        
        Args:
            orchestrator: Orchestrator 实例（用于委托调用）
        """
        self.orchestrator = orchestrator
    
    async def exec_sub_task(
        self,
        llm: Any,
        sub_task: Any,  # SubTask
        main_prompt: str,
        state: Optional[Dict[str, Any]] = None,
        history: Optional[List[Any]] = None
    ) -> SubAgentResult:
        """执行单个子 Agent 任务。
        
        Args:
            llm: LLM 实例
            sub_task: 子任务对象
            main_prompt: 主提示词
            state: Orchestrator 状态（可选）
            history: 会话历史（可选）
            
        Returns:
            SubAgentResult: 子 Agent 执行结果
        """
        # 子 Agent 独立 LLM（避免污染主 LLM），按白名单绑定工具
        cfg = await self.orchestrator.loader.load_sub_agent(sub_task.sub_agent_id)
        
        # 统一 State：子图进入填 temp_sub_config
        if state is not None:
            state["temp_sub_config"] = {
                "agent_id": cfg.agent_id,
                "name": cfg.name,
                "system_prompt": cfg.system_prompt,
                "tools_whitelist": list(cfg.tools_whitelist),
                "max_step": cfg.max_step,
            }

        try:
            sub_llm = await self.orchestrator._create_llm()
            tools = self._load_sub_tools(cfg.tools_whitelist)
            
            if tools:
                try:
                    sub_llm = sub_llm.bind_tools(tools)
                    logger.info("[TaskDispatcher] 子 Agent=%s 绑定工具 %d 个", cfg.name, len(tools))
                except Exception as e:
                    logger.warning(
                        "[TaskDispatcher] 子 Agent=%s 工具绑定失败，走纯 LLM: %s",
                        cfg.name, e
                    )

            # 主上下文继承 + 记忆回灌
            task_prompt = sub_task.task_prompt
            if cfg.inherit_main_context and main_prompt:
                hist_text = ""
                if history:
                    hist_text = "\n".join(
                        f"{getattr(m, 'type', 'message')}: {getattr(m, 'content', '')}"
                        for m in history
                    )
                    hist_text = f"\n[会话历史]\n{hist_text}\n"
                task_prompt = f"{main_prompt}{hist_text}\n\n[子任务]\n{task_prompt}"

            sub_system = cfg.system_prompt or "你是专业子 Agent，请用工具（如需要）完成任务。"
            sub_security = self._security_policy_for(cfg)

            # 按 sandbox_policy 初始化独立沙箱生命周期
            if cfg.sandbox_policy:
                from packages.agent.core.harness.sandbox.runtime import SandboxScope
                async with SandboxScope(
                    db=self.orchestrator.db,
                    user_id=self.orchestrator.user_id,
                    session_id=getattr(self.orchestrator, "session_id", None),
                    policy=cfg.sandbox_policy,
                ) as scope:
                    return await self._run_sub_agent_graph(
                        sub_llm, tools, sub_system, sub_security, cfg, task_prompt,
                        sandbox_workdir=scope.workdir,
                    )
            
            return await self._run_sub_agent_graph(
                sub_llm, tools, sub_system, sub_security, cfg, task_prompt,
                sandbox_workdir=None,
            )
        finally:
            # 统一 State：子图退出清空 temp_sub_config
            if state is not None:
                state["temp_sub_config"] = None
    
    async def _run_sub_agent_graph(
        self,
        sub_llm: Any,
        tools: List[Any],
        sub_system: str,
        sub_security: Any,
        cfg: Any,
        task_prompt: str,
        sandbox_workdir: Optional[str] = None
    ) -> SubAgentResult:
        """运行子 Agent 图。
        
        Args:
            sub_llm: 子 Agent LLM
            tools: 工具列表
            sub_system: 系统提示词
            sub_security: 安全策略
            cfg: 子 Agent 配置
            task_prompt: 任务提示词
            sandbox_workdir: 沙箱工作目录
            
        Returns:
            SubAgentResult: 执行结果
        """
        # 构建子 Agent 图
        graph = await self.orchestrator._build_agent_graph(
            sub_llm,
            tools=tools,
            system_prompt=sub_system,
            security_policy=sub_security,
            sandbox_workdir=sandbox_workdir
        )
        
        # 执行图
        try:
            thread_id = f"{self.orchestrator.user_id}:sub:{cfg.agent_id}:{int(__import__('time').time() * 1000)}"
            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": getattr(self.orchestrator.config, "recursion_limit", None) or 25
            }
            
            state = {
                "messages": [{"role": "user", "content": task_prompt}],
                "session_id": None,
                "trace_id": f"trace_{int(__import__('time').time() * 1000)}",
            }
            
            final_state = await graph.ainvoke(state, config=config)
            
            # 提取结果
            messages = final_state.get("messages", [])
            content = messages[-1].content if messages else ""
            
            return SubAgentResult(
                sub_agent_id=cfg.agent_id,
                success=True,
                content=content
            )
        except Exception as e:
            logger.error("[TaskDispatcher] 子 Agent 执行失败：%s", e)
            return SubAgentResult(
                sub_agent_id=cfg.agent_id,
                success=False,
                error=f"执行失败：{e}"
            )
    
    def _load_sub_tools(self, whitelist: List[str]) -> List[Any]:
        """加载子工具（从数据库/注册表）。
        
        Args:
            whitelist: 工具白名单
            
        Returns:
            List[Any]: 工具实例列表
        """
        from packages.agent.tools.registry import get_tool_registry
        
        tool_registry = get_tool_registry()
        tools = []
        
        # 1. 如果有白名单，只加载白名单中的工具
        if whitelist:
            for tool_name in whitelist:
                try:
                    tool = tool_registry.get(tool_name)
                    if tool:
                        tools.append(tool)
                    else:
                        logger.warning("[Dispatcher] 工具不存在：%s", tool_name)
                except Exception as e:
                    logger.error("[Dispatcher] 加载工具失败：%s: %s", tool_name, e)
        else:
            # 2. 无白名单：从数据库加载 Agent 配置的工具
            # 注意：这里需要数据库会话，由调用方传入
            if hasattr(self, 'db') and self.db:
                try:
                    # 从数据库查询 Agent 的工具配置
                    # TODO: 实现数据库查询逻辑
                    # SELECT tools FROM agent_configs WHERE agent_id = :agent_id
                    pass
                except Exception as e:
                    logger.error("[Dispatcher] 从数据库加载工具失败：%s", e)
            
            # 3. 降级：使用工具注册表的全部工具
            # 注意：生产环境应该限制工具范围
            tools = list(tool_registry._tools.values())
        
        logger.info("[Dispatcher] 加载了 %d 个工具", len(tools))
        return tools
    
    def _security_policy_for(self, cfg: Any) -> Any:
        """为子 Agent 构建安全策略（根据上下文）。
        
        Args:
            cfg: 子 Agent 配置
            
        Returns:
            安全策略对象（dict）
        """
        # 安全策略结构：
        # {
        #     "tool_whitelist": ["tool1", "tool2"],  # 工具白名单
        #     "max_iterations": 10,                   # 最大迭代次数
        #     "require_approval": ["dangerous_tool"], # 需要审批的工具
        #     "blocked_tools": ["blocked_tool"],      # 禁止的工具
        #     "user_level": "normal",                 # 用户级别
        # }
        
        security_policy = {
            "tool_whitelist": [],
            "max_iterations": 10,
            "require_approval": [],
            "blocked_tools": [],
            "user_level": "normal",
        }
        
        # 1. 从配置中读取安全策略
        if cfg and hasattr(cfg, 'security_policy'):
            cfg_policy = cfg.security_policy
            if isinstance(cfg_policy, dict):
                security_policy.update(cfg_policy)
        
        # 2. 根据用户级别调整策略
        if hasattr(self, 'user_id') and self.user_id:
            # TODO: 从数据库查询用户级别
            # SELECT user_level FROM users WHERE id = :user_id
            # 这里简单实现：假设 user_id=1 是管理员
            if self.user_id == 1:
                security_policy["user_level"] = "admin"
                security_policy["max_iterations"] = 20
            else:
                security_policy["user_level"] = "normal"
                security_policy["max_iterations"] = 10
        
        # 3. 根据 Agent 类型调整策略
        if cfg and hasattr(cfg, 'agent_type'):
            agent_type = cfg.agent_type
            if agent_type == "analyst":
                # 分析型 Agent：允许更多工具
                security_policy["max_iterations"] = 15
            elif agent_type == "executor":
                # 执行型 Agent：需要更严格的审批
                security_policy["require_approval"] = ["file_write", "code_execute"]
        
        logger.debug("[Dispatcher] 为 Agent 构建安全策略：%s", security_policy)
        return security_policy
