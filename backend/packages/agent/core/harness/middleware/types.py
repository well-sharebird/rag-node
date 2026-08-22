"""Middleware 类型定义 - 兼容不同 LangChain 版本

提供 AgentMiddleware 和 Runtime 的本地定义，避免依赖特定 LangChain 版本。
"""
from typing import Any, Dict, Optional
from dataclasses import dataclass


@dataclass
class Runtime:
    """中间件运行时上下文
    
    提供中间件执行所需的环境信息。
    """
    agent_name: Optional[str] = None
    run_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AgentMiddleware:
    """Agent 中间件基类
    
    中间件在 Agent 执行生命周期的关键点被调用，可以修改 state 或执行副作用。
    
    生命周期方法:
    - abefore_agent: 在 Agent 执行前调用
    - aafter_agent: 在 Agent 执行后调用
    - abefore_model: 在模型调用前调用
    - aafter_model: 在模型调用后调用
    """
    
    async def abefore_agent(self, state: Dict[str, Any], runtime: Runtime) -> Optional[Dict[str, Any]]:
        """在 Agent 执行前调用
        
        Args:
            state: 当前执行状态
            runtime: 运行时上下文
            
        Returns:
            可选的状态更新字典
        """
        return None
    
    async def aafter_agent(self, state: Dict[str, Any], runtime: Runtime) -> Optional[Dict[str, Any]]:
        """在 Agent 执行后调用
        
        Args:
            state: 当前执行状态
            runtime: 运行时上下文
            
        Returns:
            可选的状态更新字典
        """
        return None
    
    async def abefore_model(self, state: Dict[str, Any], runtime: Runtime) -> Optional[Dict[str, Any]]:
        """在模型调用前调用
        
        Args:
            state: 当前执行状态
            runtime: 运行时上下文
            
        Returns:
            可选的状态更新字典
        """
        return None
    
    async def aafter_model(self, state: Dict[str, Any], runtime: Runtime) -> Optional[Dict[str, Any]]:
        """在模型调用后调用
        
        Args:
            state: 当前执行状态
            runtime: 运行时上下文
            
        Returns:
            可选的状态更新字典
        """
        return None
