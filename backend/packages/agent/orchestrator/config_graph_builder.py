"""
配置驱动的图构建器

从 AgentConfig 配置动态构建执行图
"""
from packages.agent.llm.factory import create_llm
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
        """构建 Supervisor 多 Agent 编排图
        
        架构:
        ```
        Supervisor Graph
        ├── Supervisor Node (决策路由)
        ├── Sub-Agent Nodes (并行/串行执行)
        ├── Aggregator Node (结果聚合)
        └── Output Node (最终输出)
        ```
        
        Args:
            config: Agent 配置
            llm: 主 LLM 实例
            tools: 工具列表
            
        Returns:
            编译好的多 Agent 状态图
        """
        from langgraph.graph import StateGraph, START, END
        from packages.agent.runtime import AgentState
        
        logger.info("[ConfigGraphBuilder] 构建多 Agent 编排图 | sub_agents=%d", 
                   len(config.sub_agents or []))
        
        # 1. 创建状态图
        graph = StateGraph(AgentState)
        
        # 2. 添加 Supervisor 节点（决策路由）
        graph.add_node("supervisor", self._create_supervisor_node(llm, config))
        
        # 3. 添加子 Agent 节点
        sub_agent_ids = []
        if config.sub_agents:
            for sub_agent_config in config.sub_agents:
                sub_agent_id = sub_agent_config.agent_id
                sub_agent_ids.append(sub_agent_id)
                
                # 为每个子 Agent 创建执行图
                sub_graph = self._build_sub_agent_graph(sub_agent_config)
                graph.add_node(sub_agent_id, self._create_sub_agent_node(sub_graph))
        
        # 4. 添加聚合节点
        graph.add_node("aggregator", self._create_aggregator_node())
        
        # 5. 添加输出节点
        graph.add_node("output", self._create_output_node())
        
        # 6. 添加边
        # START → Supervisor
        graph.add_edge(START, "supervisor")
        
        # Supervisor → Sub-Agents (条件边)
        graph.add_conditional_edges(
            "supervisor",
            self._create_supervisor_router(sub_agent_ids),
            {sid: sid for sid in sub_agent_ids} | {"end": "output"}
        )
        
        # Sub-Agents → Aggregator
        for sub_agent_id in sub_agent_ids:
            graph.add_edge(sub_agent_id, "aggregator")
        
        # Aggregator → Supervisor (循环) 或 Output
        graph.add_conditional_edges(
            "aggregator",
            self._create_aggregator_router(),
            {"continue": "supervisor", "end": "output"}
        )
        
        # Output → END
        graph.add_edge("output", END)
        
        # 7. 编译图
        return graph.compile()
    
    def _create_supervisor_node(self, llm, config: AgentConfig):
        """创建 Supervisor 节点（决策路由）
        
        职责:
        1. 分析当前任务
        2. 决定是否需要子 Agent
        3. 选择哪个子 Agent 执行
        4. 分配任务给子 Agent
        
        Args:
            llm: LLM 实例
            config: Agent 配置
            
        Returns:
            Supervisor 节点函数
        """
        async def supervisor_node(state: TAOState) -> Dict[str, Any]:
            """Supervisor 节点 - 决策路由"""
            from langchain_core.messages import SystemMessage, HumanMessage
            import json
            
            messages = state.get("messages", [])
            iteration = state.get("iteration", 0)
            
            # 构建 Supervisor 提示词
            system_prompt = f"""你是一个任务调度助手。请分析当前任务，决定是否需要子 Agent 执行。

可用子 Agent:
{chr(10).join(f'- {sa.agent_id}: {sa.name} - {sa.description}' for sa in (config.sub_agents or []))}

如果不需要子 Agent，返回 {{"action": "end"}}。
如果需要子 Agent，返回 {{"action": "dispatch", "sub_agent_id": "agent_id", "task": "任务描述"}}。
"""
            
            prompt_msgs = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=messages[-1].content if messages else "")
            ]
            
            # 调用 LLM 决策
            resp = await llm.ainvoke(prompt_msgs)
            
            try:
                # 解析决策
                decision = json.loads(resp.content)
                action = decision.get("action", "end")
                
                if action == "dispatch" and decision.get("sub_agent_id"):
                    # 分发任务给子 Agent
                    sub_agent_id = decision["sub_agent_id"]
                    task = decision.get("task", messages[-1].content if messages else "")
                    
                    logger.info("[Supervisor] 分发任务给子 Agent: %s", sub_agent_id)
                    
                    return {
                        "messages": messages,
                        "iteration": iteration + 1,
                        "dispatch_to": sub_agent_id,
                        "dispatch_task": task,
                    }
                else:
                    # 无需子 Agent，直接结束
                    logger.info("[Supervisor] 无需子 Agent，直接结束")
                    return {
                        "messages": messages,
                        "iteration": iteration + 1,
                        "dispatch_to": None,
                    }
            except Exception as e:
                logger.error("[Supervisor] 决策失败：%s", e)
                # 降级：直接结束
                return {
                    "messages": messages,
                    "iteration": iteration + 1,
                    "dispatch_to": None,
                }
        
        return supervisor_node
    
    def _create_sub_agent_node(self, sub_graph):
        """创建子 Agent 节点（执行子图）
        
        Args:
            sub_graph: 子 Agent 执行图
            
        Returns:
            子 Agent 节点函数
        """
        async def sub_agent_node(state: TAOState) -> Dict[str, Any]:
            """子 Agent 节点 - 执行具体任务"""
            # 调用子图执行
            # 注意：这里需要获取当前 dispatch_to 信息
            dispatch_to = state.get("dispatch_to")
            dispatch_task = state.get("dispatch_task")
            
            if not dispatch_to:
                logger.warning("[SubAgent] 无目标子 Agent，跳过执行")
                return state
            
            logger.info("[SubAgent] 执行子 Agent: %s | task=%s", dispatch_to, dispatch_task)
            
            # 执行子图（简化实现：直接调用子图的 invoke）
            # 实际应该使用子图的异步流式执行
            try:
                result = await sub_graph.ainvoke(state)
                return result
            except Exception as e:
                logger.error("[SubAgent] 执行失败：%s", e)
                # 返回错误信息
                from langchain_core.messages import AIMessage
                return {
                    **state,
                    "messages": state.get("messages", []) + [
                        AIMessage(content=f"[子 Agent 执行失败] {dispatch_to}: {e}")
                    ],
                }
        
        return sub_agent_node
    
    def _create_aggregator_node(self):
        """创建聚合节点（合并子 Agent 结果）
        
        职责:
        1. 收集所有子 Agent 的执行结果
        2. 合并结果
        3. 判断是否需要继续执行
        
        Returns:
            聚合节点函数
        """
        async def aggregator_node(state: TAOState) -> Dict[str, Any]:
            """聚合节点 - 合并子 Agent 结果"""
            messages = state.get("messages", [])
            iteration = state.get("iteration", 0)
            tool_results = state.get("tool_results", [])
            
            # 聚合逻辑：简单追加结果到消息
            # 实际可以更复杂的合并策略
            logger.info("[Aggregator] 聚合子 Agent 结果 | messages=%d, tool_results=%d", 
                       len(messages), len(tool_results))
            
            # 判断是否需要继续执行
            # 简化规则：如果还有未处理的消息，继续执行
            should_continue = len(messages) > 0 and iteration < 10
            
            return {
                "messages": messages,
                "iteration": iteration + 1,
                "tool_results": tool_results,
                "should_continue": should_continue,
            }
        
        return aggregator_node
    
    def _create_output_node(self):
        """创建输出节点（最终输出）
        
        职责:
        1. 生成最终输出
        2. 清理临时状态
        
        Returns:
            输出节点函数
        """
        async def output_node(state: TAOState) -> Dict[str, Any]:
            """输出节点 - 生成最终输出"""
            messages = state.get("messages", [])
            
            logger.info("[Output] 生成最终输出 | messages=%d", len(messages))
            
            # 简单返回最后一条消息作为输出
            # 实际可以更复杂的生成逻辑
            return {
                "messages": messages,
                "final_output": messages[-1].content if messages else "",
            }
        
        return output_node
    
    def _create_supervisor_router(self, sub_agent_ids: List[str]):
        """创建 Supervisor 路由器（条件边决策）
        
        Args:
            sub_agent_ids: 子 Agent ID 列表
            
        Returns:
            路由函数
        """
        def supervisor_router(state: TAOState) -> str:
            """Supervisor 路由决策"""
            dispatch_to = state.get("dispatch_to")
            
            if dispatch_to and dispatch_to in sub_agent_ids:
                return dispatch_to
            else:
                return "end"
        
        return supervisor_router
    
    def _create_aggregator_router(self):
        """创建聚合路由器（条件边决策）
        
        Returns:
            路由函数
        """
        def aggregator_router(state: TAOState) -> str:
            """聚合器路由决策"""
            should_continue = state.get("should_continue", False)
            
            if should_continue:
                return "continue"
            else:
                return "end"
        
        return aggregator_router
    
    def _build_sub_agent_graph(self, sub_agent_config):
        """构建子 Agent 执行图
        
        Args:
            sub_agent_config: 子 Agent 配置
            
        Returns:
            子 Agent 执行图
        """
        #         简化实现：使用单 Agent 图
        # 实际应该根据子 Agent 配置构建专用图
        
        # TODO: 根据子 Agent 配置构建专用图
        # 这里使用简化实现
        
        # 返回一个简化图
        from langgraph.graph import StateGraph, START, END
        from packages.agent.runtime import AgentState
        
        graph = StateGraph(AgentState)
        graph.add_node("think", lambda state: state)  # 占位
        graph.add_edge(START, "think")
        graph.add_edge("think", END)
        
        return graph.compile()
    
    async def _create_llm(self, model_config):
        """使用统一工厂创建 LLM 实例"""
        from packages.agent.schemas.chat import ModelConfig as ChatModelConfig
        
        # 使用统一工厂
        return create_llm(
            provider=model_config.provider.lower(),
            model_name=model_config.model,
            temperature=model_config.temperature,
            max_tokens=model_config.max_tokens,  # None 表示不限制
            top_p=model_config.top_p if hasattr(model_config, 'top_p') else 0.9,
            api_key=model_config.api_key if hasattr(model_config, 'api_key') else None,
            base_url=model_config.base_url if hasattr(model_config, 'base_url') else None,
        )
    
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
