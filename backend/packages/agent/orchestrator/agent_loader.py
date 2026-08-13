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
    # SOUL 层：人格与底线
    soul: str = ""
    # CLAUDE 层：任务规则与工作流
    claude: str = ""
    # 沙箱策略（来自主 Agent 配置 agent.yaml，供沙箱初始化）
    sandbox_policy: Dict[str, Any] = field(default_factory=dict)
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
        """加载入口主 Agent（本地静态文件配置驱动）。

        来源：`config/default_main_agent/`（soul.md/claude.md/agent.yaml，经
        `AgentConfigLoader` 解析）。API 传入的 `system_prompt`（main_prompt）作为
        **覆盖/兜底**：显式提供时覆盖文件指令；文件缺省时回退到它，保持兼容。
        主 Agent 配置只读：仅注入图，不被任何节点改写。
        """
        from packages.agent.config.agent_config_loader import get_default_agent_config

        file_cfg = get_default_agent_config()
        soul = file_cfg.soul or ""
        claude = file_cfg.claude or ""
        file_prompt = "\n\n".join(filter(None, [soul, claude]))

        effective_prompt = system_prompt if system_prompt else file_prompt

        # 工具集：文件白名单(agent.yaml) ∪ 调用方必带工具(save_workspace_file 等)，去重保序
        config_tools = list(file_cfg.enabled_tools or [])
        effective_tools = list(dict.fromkeys([*config_tools, *(tools or [])]))

        return LoadedAgentConfig(
            agent_id=name,
            name=file_cfg.name or name,
            system_prompt=effective_prompt,
            soul=soul,
            claude=claude,
            sandbox_policy=dict(file_cfg.sandbox_policy or {}),
            tools_whitelist=effective_tools,
            max_step=file_cfg.max_steps or 15,
            raw={"token_budget": file_cfg.token_budget, "max_output_tokens": file_cfg.max_output_tokens},
        )

    # ---------------- 子 Agent 目录 ----------------
    async def list_sub_agents(self, user_id: Optional[int] = None) -> List[Dict[str, str]]:
        """列出可调用的子 Agent 目录（供主 Agent 结构化选择）。

        目录 = 系统级（tenant_id="system" 且 active）∪ 当前用户的 active Agent，
        使系统种子子 Agent 对任意用户都可被编排派发。
        返回 [{agent_id, name, description}]（按 id 去重）。
        """
        from packages.agent.services.agent_config_service import AgentConfigService

        service = AgentConfigService(self.db)
        candidates = []
        own_agents, _ = await service.list(
            user_id=user_id or 1, status="active", limit=50
        )
        candidates.extend(own_agents)

        # 系统级 active 子 Agent（供所有用户编排使用）
        try:
            from packages.agent.models.agent import AgentConfig
            from sqlalchemy import select

            result = await self.db.execute(
                select(AgentConfig).where(
                    AgentConfig.tenant_id == "system",
                    AgentConfig.status == "active",
                )
            )
            candidates.extend(result.scalars().all())
        except Exception as e:
            logger.warning("[AgentLoader] 加载系统子 Agent 失败: %s", e)

        seen = set()
        catalog = []
        for a in candidates:
            aid = str(a.id)
            if aid in seen:
                continue
            seen.add(aid)
            catalog.append({
                "agent_id": aid,
                "name": a.name,
                "description": a.description or "",
            })
        return catalog

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

        # Phase 3：补齐沙箱/记忆策略 + 主上下文继承（从 DB 读取，不再固定 False）
        ext = agent.extensions_config or {}
        inherit_main_context = bool(ext.get("inherit_main_context", False))

        cfg = LoadedAgentConfig(
            agent_id=str(agent.id),
            name=agent.name,
            system_prompt=agent.system_prompt or "",
            sandbox_policy=dict(agent.sandbox_policy or {}),
            tools_whitelist=whitelist,
            require_approval_tools=require_approval,
            max_step=10,
            inherit_main_context=inherit_main_context,
            raw={
                "memory_type": getattr(agent, "memory_type", None),
                "memory_strategy": dict(agent.memory_strategy or {}),
                "default_model_config": getattr(agent, "default_model_config", None),
            },
        )
        logger.info(
            "[AgentLoader] 加载子 Agent: %s (tools=%s, inherit_main=%s, sandbox=%s)",
            cfg.name, whitelist, inherit_main_context, bool(cfg.sandbox_policy),
        )
        return cfg
