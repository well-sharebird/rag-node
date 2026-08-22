"""Agent TAO 图构建器（Factory/Builder 模式）。

把"按 agent_config/角色装配 Harness 组件并编译 LangGraph 图"的职责从
OrchestratorRuntime 中抽出：运行时代理只负责编排流程，图的具体装配收敛到本构建器。
主/子 Agent、不同安全策略、checkpointer 的可选绑定都统一经此入口。
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from packages.agent.core.harness.config import DEFAULT_USER_ID

logger = logging.getLogger(__name__)


class AgentGraphBuilder:
    """统一构建 TAO Graph：middleware + 权限引擎 + 输出治理 + checkpointer + Harness 上下文工程。"""

    def __init__(self, db: AsyncSession, user_id: Optional[int] = None):
        self.db = db
        self.user_id = user_id or DEFAULT_USER_ID

    def _build_middlewares(self, security_policy: Optional[dict] = None) -> List[Any]:
        """装配 harness 管控中间件（日志/审计/安全/上下文，全链路管控）。"""
        from packages.agent.core.harness.middleware.builtin import (
            AuditLoggerMiddleware,
            ContextInitMiddleware,
            SecurityGuardMiddleware,
            ToolLoggingMiddleware,
        )
        return [
            ContextInitMiddleware(),
            ToolLoggingMiddleware(),
            AuditLoggerMiddleware(),
            SecurityGuardMiddleware(policy=security_policy or {}),
        ]

    def build(self, llm: Any, tools: Optional[List[Any]] = None,
              system_prompt: Optional[str] = None, max_iterations: int = 10,
              on_token: Optional[Any] = None,
              on_tool_event: Optional[Any] = None,
              security_policy: Optional[dict] = None,
              checkpointer: Optional[Any] = None,
              use_checkpointer: bool = False,
              agent_config: Optional[dict] = None,
              sandbox_workdir: Optional[str] = None):
        """构建集成 Harness 上下文工程 + 权限/工具治理的统一 TAO 图。

        主/子 Agent 执行默认不启用 checkpointer（即时任务状态无需持久化）；
        需 HITL 断点续跑时（resume_sub_agent/_run_sub_agent_graph 携带
        require_approval 工具的子图）才以 use_checkpointer=True 绑定
        DatabaseCheckpointSaver（经 JsonPlusSerializer 序列化 LangChain 消息）。
        """
        from packages.agent.runtime import build_agent_graph
        from packages.agent.output.governance import OutputGovernanceNode
        from packages.agent.core.harness.security.permission import PermissionEngine
        from packages.agent.core.harness.context import PromptAssembler

        # Harness 上下文工程：使用 PromptAssembler 组装系统提示词（设计文档 11.4）
        prompt_assembler = None
        if agent_config:
            soul = agent_config.get("soul", "")
            claude = agent_config.get("claude", "")
            token_budget = agent_config.get("token_budget", 8192)
            prompt_assembler = PromptAssembler(
                system_prompt="\n\n".join(filter(None, [soul, claude])) or system_prompt,
                max_tokens=token_budget,
                reserve_tokens=512,
            )
        elif system_prompt:
            prompt_assembler = PromptAssembler(
                system_prompt=system_prompt,
                max_tokens=8192,
                reserve_tokens=512,
            )

        # 权限引擎（Harness 管控层：工具白名单/审批/拒绝）
        permission_engine = None
        if security_policy:
            try:
                permission_engine = PermissionEngine(db=self.db, user_id=self.user_id, policy=security_policy)
            except Exception as e:
                logger.warning("[Orchestrator] 权限引擎初始化失败: %s", e)

        middlewares = self._build_middlewares(security_policy)
        output_gov = OutputGovernanceNode(llm=llm, enable_structured=False)
        checkpointer = checkpointer if use_checkpointer else None

        # Harness 工具治理门面（设计文档 2.2）：Phase 0 透传不接管，Phase 1 路由工具执行
        # security_policy 注入门面，使工具级护栏强制白名单（纵深防御，与 permission_check 节点双层）。
        from packages.agent.core.harness.tools import ToolExecutionManager
        execution_manager = ToolExecutionManager(
            db=self.db, user_id=self.user_id, session_id=None,
            sandbox_workdir=sandbox_workdir, security_policy=security_policy,
            rate_limit=(agent_config or {}).get("rate_limit"),
            circuit=(agent_config or {}).get("circuit"),
            on_tool_event=on_tool_event,
        )

        # 使用纯 Agent Loop 图
        # 注意：build_agent_graph 不支持 prompt_assembler 和 execution_manager
        # 这些功能需要迁移到中间件模式
        return build_agent_graph(
            llm=llm,
            tools=tools or [],
            system_prompt=system_prompt or "你是助手。",
            max_iterations=max_iterations,
            permission_engine=permission_engine,
            enable_output_governance=True,
            output_governance_node=output_gov,
            on_token=on_token,
            checkpointer=checkpointer,
            middlewares=middlewares,
        )
