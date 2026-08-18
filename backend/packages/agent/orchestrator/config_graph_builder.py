"""
配置驱动的图构建器

从 AgentConfig 配置动态构建执行图
"""
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from packages.agent.config.agent_config import (
    AgentConfig,
    AgentType,
    RunMode,
    ToolConfig,
    SecurityPolicy,
)
from packages.agent.orchestrator.graph_builder import AgentGraphBuilder
from packages.agent.orchestrator.business_tools import ensure_business_tools
from packages.agent.core.harness.agent.loader import security_policy_for

logger = logging.getLogger(__name__)


class ConfigDrivenGraphBuilder:
    """
    配置驱动的图构建器
    
    从 AgentConfig 配置动态构建执行图
    替代硬编码的图构建逻辑
    """
    
    def __init__(self, db: AsyncSession, user_id: int):
        self.db = db
        self.user_id = user_id
        self._base_builder = AgentGraphBuilder(db, user_id)
        self._tools_cache: Dict[str, Any] = {}
    
    async def build_graph(self, config: AgentConfig):
        """
        从配置构建执行图
        
        Args:
            config: Agent 配置
            
        Returns:
            编译好的状态图
        """
        logger.info("[ConfigGraphBuilder] 构建 Agent 图 | type=%s, name=%s", 
                   config.agent_type, config.name)
        
        # 1. 创建 LLM
        llm = await self._create_llm(config.model)
        
        # 2. 加载工具
        tools = await self._load_tools(config.tools)
        
        # 3. 绑定工具到 LLM
        if tools:
            llm = llm.bind_tools(tools)
        
        # 4. 根据 Agent 类型构建图
        if config.agent_type == AgentType.SINGLE:
            return self._build_single_agent_graph(config, llm, tools)
        elif config.agent_type == AgentType.SUPERVISOR:
            return self._build_supervisor_graph(config, llm, tools)
        else:
            # 其他类型暂时回退到单 Agent
            logger.warning("不支持的 Agent 类型：%s，回退到单 Agent 模式", config.agent_type)
            return self._build_single_agent_graph(config, llm, tools)
    
    def _build_single_agent_graph(self, config: AgentConfig, llm, tools: List):
        """构建单 Agent 图"""
        security_policy = self._create_security_policy(config.security)
        
        return self._base_builder._build_agent_graph(
            llm=llm,
            tools=tools,
            system_prompt=config.system_prompt,
            max_iterations=config.tao_loop.max_iterations,
            security_policy=security_policy,
            use_checkpointer=config.runtime.enable_checkpointer,
            checkpointer=self._base_builder._get_checkpointer() if config.runtime.enable_checkpointer else None,
        )
    
    def _build_supervisor_graph(self, config: AgentConfig, llm, tools: List):
        """构建 Supervisor 多 Agent 图"""
        # TODO: 实现多 Agent 编排图
        # 目前先构建主 Agent 图，子 Agent 后续实现
        logger.warning("多 Agent 编排图暂未实现，使用单 Agent 图替代")
        return self._build_single_agent_graph(config, llm, tools)
    
    async def _create_llm(self, model_config):
        """创建 LLM 实例"""
        from packages.agent.schemas.chat import ModelConfig as ChatModelConfig
        from langchain_openai import ChatOpenAI
        from langchain_anthropic import ChatAnthropic
        
        # 根据 provider 创建不同的 LLM
        provider = model_config.provider.lower()
        
        common_kwargs = {
            "model": model_config.model,
            "temperature": model_config.temperature,
        }
        
        if model_config.max_tokens:
            common_kwargs["max_tokens"] = model_config.max_tokens
        
        if provider in ("openai", "deepseek"):
            # DeepSeek 使用 OpenAI 兼容接口
            if provider == "deepseek":
                common_kwargs["openai_api_base"] = "https://api.deepseek.com"
                common_kwargs["openai_api_key"] = "${DEEPSEEK_API_KEY}"
            
            llm = ChatOpenAI(**common_kwargs)
        
        elif provider == "anthropic":
            llm = ChatAnthropic(**common_kwargs)
        
        else:
            raise ValueError(f"不支持的模型提供商：{provider}")
        
        return llm
    
    async def _load_tools(self, tool_configs: List[ToolConfig]):
        """加载工具列表"""
        tools = []
        
        # 1. 加载业务工具
        business_tools = ensure_business_tools()
        tool_map = {t.name: t for t in business_tools}
        
        # 2. 根据配置筛选和配置工具
        for tool_config in tool_configs:
            if not tool_config.enabled:
                continue
            
            if tool_config.name in tool_map:
                tool = tool_map[tool_config.name]
                # 应用工具特定配置
                if tool_config.config:
                    tool = self._configure_tool(tool, tool_config.config)
                tools.append(tool)
            else:
                logger.warning("工具不存在：%s", tool_config.name)
        
        return tools
    
    def _configure_tool(self, tool, config: dict):
        """应用工具配置"""
        # TODO: 实现工具配置
        # 目前直接返回原工具
        return tool
    
    def _create_security_policy(self, security_config: SecurityPolicy):
        """创建安全策略"""
        # TODO: 实现安全策略对象
        # 目前返回 None，使用默认策略
        return None
