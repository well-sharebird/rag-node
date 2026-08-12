"""AgentLoader - 主/子 Agent 配置加载

- load_main_agent: 加载入口主 Agent（内置默认配置或默认 AgentConfig）
- load_sub_agent: 按 sub_agent_id 从 DB 懒加载子 Agent 配置
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class LoadedAgentConfig:
    """标准化 Agent 配置（主/子通用）"""
    agent_id: str
    name: str = ""
    # 指令边界（soul/claude）合并为一个 system_prompt
    system_prompt: str = ""
    # 工具白名单：allowed_tools（空 = 继承/不限制）
    tools_whitelist: List[str] = field(default_factory=list)
    # 需人工审批的工具（HITL）
    require_approval_tools: List[str] = field(default_factory=list)
    max_step: int = 10
    inherit_main_context: bool = False
    raw: Optional[Dict[str, Any]] = None


class AgentLoader:
    """加载主/子 Agent 配置。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------------- 主 Agent ----------------
    def load_main_agent(self, system_prompt: Optional[str] = None, tools: Optional[List[str]] = None,
                        name: str = "main_agent") -> LoadedAgentConfig:
        """加载入口主 Agent（内置配置，由调用方注入 system_prompt/工具）。"""
        tools = tools or []
        return LoadedAgentConfig(
            agent_id=name,
            name=name,
            system_prompt=system_prompt or "",
            tools_whitelist=tools,
            max_step=15,
        )

    # ---------------- 子 Agent 目录 ----------------
    async def list_sub_agents(self, user_id: Optional[int] = None) -> List[Dict[str, str]]:
        """列出可调用的子 Agent 目录（供主 Agent 结构化选择）。

        MVP：将所有 active 的 Agent 作为可调用子 Agent 候选。
        返回 [{agent_id, name, description}]。
        """
        from packages.agent.services.agent_config_service import AgentConfigService

        service = AgentConfigService(self.db)
        agents, _ = await service.list(
            user_id=user_id or 1, status="active", limit=50
        )
        return [
            {
                "agent_id": str(a.id),
                "name": a.name,
                "description": a.description or "",
            }
            for a in agents
        ]

    @staticmethod
    def resolve_sub_agent_id(raw_id: str, catalog: List[Dict[str, str]]) -> Optional[str]:
        """把主 Agent 的输出解析为目录中的真实 agent_id。

        支持精确匹配 id；若 LLM 输出的是名称/别名，则回退按 name 匹配。
        找不到返回 None（交由上层降级）。
        """
        raw = (raw_id or "").strip()
        if not raw:
            return None
        for entry in catalog:
            if raw == entry["agent_id"]:
                return entry["agent_id"]
        for entry in catalog:
            if raw == entry["name"]:
                return entry["agent_id"]
        return None

    # ---------------- 子 Agent ----------------
    async def load_sub_agent(self, sub_agent_id: str) -> LoadedAgentConfig:
        """按 sub_agent_id 从 DB 懒加载子 Agent 配置。

        复用 agent_configs 表（agent_type='sub' 标记）：
        - system_prompt 承载 soul/claude 指令
        - security_policy.allowed_tools 承载工具白名单
        """
        from packages.agent.models.agent import AgentConfig
        from packages.agent.services.agent_config_service import AgentConfigService

        service = AgentConfigService(self.db)
        agent = await service.get_by_id(sub_agent_id)
        if agent is None:
            raise ValueError(f"子 Agent 不存在: {sub_agent_id}")

        security = agent.security_policy or {}
        whitelist = list(security.get("allowed_tools") or []) if security else []
        require_approval = list(security.get("require_approval_tools") or []) if security else []

        cfg = LoadedAgentConfig(
            agent_id=str(agent.id),
            name=agent.name,
            system_prompt=agent.system_prompt or "",
            tools_whitelist=whitelist,
            require_approval_tools=require_approval,
            max_step=10,
            inherit_main_context=False,
            raw={
                "memory_type": getattr(agent, "memory_type", None),
                "default_model_config": getattr(agent, "default_model_config", None),
            },
        )
        logger.info("[AgentLoader] 加载子 Agent: %s (tools=%s)", cfg.name, whitelist)
        return cfg
