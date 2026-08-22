"""
内置中间件（参考 DeerFlow 实现）

基础层中间件：
1. ThreadDataMiddleware - 线程数据路径初始化
2. SandboxMiddleware - 沙箱环境管理
3. ToolErrorHandlingMiddleware - 工具异常处理
4. DanglingToolCallMiddleware - 修补悬空工具调用

功能层中间件：
5. TitleMiddleware - 自动生成标题
6. MemoryMiddleware - 异步记忆更新
7. LoopDetectionMiddleware - 循环检测
8. ClarificationMiddleware - 澄清请求拦截
"""
import logging
from typing import Any, Dict, Optional, Callable

from .middleware import AgentMiddleware, RuntimeContext

logger = logging.getLogger(__name__)


# ============================================================================
# 基础层中间件
# ============================================================================

class ThreadDataMiddleware(AgentMiddleware):
    """
    线程数据中间件：初始化工作目录路径
    
    参考 DeerFlow ThreadDataMiddleware
    """
    
    def __init__(self, base_dir: str = "/mnt/user-data"):
        self.base_dir = base_dir
        self._lazy_init = True  # 懒加载：首次使用时再创建目录
    
    def before_agent(self, state: Dict[str, Any], runtime: RuntimeContext) -> Optional[Dict[str, Any]]:
        """注入线程数据路径（懒加载：只计算路径，不创建目录）"""
        thread_id = runtime.thread_id
        
        # 计算路径
        thread_base = f"{self.base_dir}/threads/{thread_id}"
        workspace_path = f"{thread_base}/user-data/workspace"
        uploads_path = f"{thread_base}/user-data/uploads"
        outputs_path = f"{thread_base}/user-data/outputs"
        
        # 注入到 runtime（而不是 state，避免污染状态）
        runtime.workspace_path = workspace_path
        runtime.set("uploads_path", uploads_path)
        runtime.set("outputs_path", outputs_path)
        
        logger.debug("[ThreadDataMiddleware] Initialized paths for thread=%s", thread_id)
        
        return {
            "thread_data": {
                "workspace_path": workspace_path,
                "uploads_path": uploads_path,
                "outputs_path": outputs_path,
            }
        }


class SandboxMiddleware(AgentMiddleware):
    """
    沙箱中间件：获取和释放沙箱环境
    
    参考 DeerFlow SandboxMiddleware
    """
    
    def __init__(self, lazy_init: bool = True):
        self._lazy_init = lazy_init
        self._acquired = False
    
    def before_agent(self, state: Dict[str, Any], runtime: RuntimeContext) -> Optional[Dict[str, Any]]:
        """获取沙箱（懒加载：首次工具调用时才获取）"""
        if self._lazy_init:
            logger.debug("[SandboxMiddleware] Lazy init enabled, skip sandbox acquisition")
            return None
        
        # 立即获取沙箱
        return self._acquire_sandbox(runtime)
    
    async def wrap_tool_call(
        self, 
        request: Dict[str, Any], 
        handler: Callable
    ) -> Any:
        """懒加载：首次工具调用时获取沙箱"""
        if self._lazy_init and not self._acquired:
            logger.debug("[SandboxMiddleware] Acquiring sandbox on first tool call")
            # 注意：这里不能直接调用 _acquire_sandbox，因为需要 runtime
            # 实际实现应该在 handler 中处理
        
        # 执行工具调用
        return await handler(request)
    
    def _acquire_sandbox(self, runtime: RuntimeContext) -> Optional[Dict[str, Any]]:
        """获取沙箱环境"""
        try:
            # TODO: 调用沙箱提供者获取沙箱
            # sandbox_id = provider.acquire(runtime.thread_id)
            sandbox_id = f"sandbox_{runtime.thread_id}"
            
            runtime.sandbox_id = sandbox_id
            self._acquired = True
            
            logger.debug("[SandboxMiddleware] Acquired sandbox=%s", sandbox_id)
            
            return {
                "sandbox": {
                    "sandbox_id": sandbox_id,
                }
            }
        except Exception as e:
            logger.error("[SandboxMiddleware] Failed to acquire sandbox: %s", e)
            return None
    
    def after_agent(self, state: Dict[str, Any], runtime: RuntimeContext) -> Optional[Dict[str, Any]]:
        """注意：不立即释放沙箱，沙箱在同一次线程内复用"""
        # 沙箱释放由上层管理（在整轮执行结束后）
        return None


class ToolErrorHandlingMiddleware(AgentMiddleware):
    """
    工具错误处理中间件：将工具异常转换为 ToolMessage
    
    参考 DeerFlow ToolErrorHandlingMiddleware
    """
    
    async def wrap_tool_call(
        self, 
        request: Dict[str, Any], 
        handler: Callable
    ) -> Any:
        """包装工具调用，捕获异常并转换为 ToolMessage"""
        from langchain_core.messages import ToolMessage
        
        tool_name = request.get("name", "unknown")
        tool_call_id = request.get("tool_call_id", "")
        
        try:
            # 执行工具调用
            result = await handler(request)
            return result
            
        except Exception as e:
            # 保留 LangGraph 控制流信号（不捕获 GraphBubbleUp 等）
            from langgraph.errors import GraphBubbleUp
            if isinstance(e, GraphBubbleUp):
                raise
            
            # 转换为错误 ToolMessage
            error_detail = f"Error: Tool '{tool_name}' failed: {str(e)}"
            logger.warning("[ToolErrorHandlingMiddleware] Tool %s failed: %s", tool_name, e)
            
            return ToolMessage(
                content=error_detail,
                tool_call_id=tool_call_id,
                status="error"
            )


class DanglingToolCallMiddleware(AgentMiddleware):
    """
    悬空工具调用修补中间件
    
    参考 DeerFlow DanglingToolCallMiddleware
    修复：模型返回了 tool_calls 但没有对应的 tool_call_id
    """
    
    def after_agent(self, state: Dict[str, Any], runtime: RuntimeContext) -> Optional[Dict[str, Any]]:
        """检查并修补悬空工具调用"""
        messages = state.get("messages", [])
        if not messages:
            return None
        
        # 检查最后一条消息
        last_msg = messages[-1]
        tool_calls = getattr(last_msg, "tool_calls", [])
        
        if not tool_calls:
            return None
        
        # 检查每个 tool_call 是否有 tool_call_id
        patched = False
        for tc in tool_calls:
            if isinstance(tc, dict):
                if "id" not in tc:
                    # 生成缺失的 ID
                    import uuid
                    tc["id"] = str(uuid.uuid4())
                    patched = True
                    logger.warning("[DanglingToolCallMiddleware] Patched missing tool_call_id")
        
        if patched:
            return {"messages": messages}
        
        return None


# ============================================================================
# 功能层中间件
# ============================================================================

class TitleMiddleware(AgentMiddleware):
    """
    标题生成中间件：自动生成对话标题
    
    参考 DeerFlow TitleMiddleware
    """
    
    def after_agent(self, state: Dict[str, Any], runtime: RuntimeContext) -> Optional[Dict[str, Any]]:
        """检查是否需要生成标题"""
        # 只在第一轮生成标题
        if state.get("title"):
            return None
        
        iteration = state.get("iteration", 0)
        if iteration != 0:
            return None
        
        # TODO: 调用 LLM 生成标题
        # 这里先标记需要生成，实际生成由上层处理
        return {"_needs_title": True}


class MemoryMiddleware(AgentMiddleware):
    """
    记忆中间件：异步记忆更新
    
    参考 DeerFlow MemoryMiddleware
    """
    
    def __init__(self, agent_name: Optional[str] = None):
        self.agent_name = agent_name
        self._pending_updates = []
    
    def after_agent(self, state: Dict[str, Any], runtime: RuntimeContext) -> Optional[Dict[str, Any]]:
        """队列对话用于记忆更新"""
        messages = state.get("messages", [])
        if not messages:
            return None
        
        # 将对话加入队列（异步更新）
        # TODO: 实际实现应该推送到记忆更新队列
        self._pending_updates.append({
            "thread_id": runtime.thread_id,
            "user_id": runtime.user_id,
            "messages": messages,
        })
        
        logger.debug("[MemoryMiddleware] Queued %d messages for memory update", len(messages))
        
        return None


class LoopDetectionMiddleware(AgentMiddleware):
    """
    循环检测中间件：检测并防止无限循环
    
    参考 DeerFlow LoopDetectionMiddleware
    """
    
    def __init__(self, max_iterations: int = 10):
        self.max_iterations = max_iterations
    
    def before_agent(self, state: Dict[str, Any], runtime: RuntimeContext) -> Optional[Dict[str, Any]]:
        """检查迭代次数，防止无限循环"""
        iteration = state.get("iteration", 0)
        
        if iteration >= self.max_iterations:
            logger.warning("[LoopDetectionMiddleware] Max iterations (%d) reached, forcing end", self.max_iterations)
            return {
                "_force_end": True,
                "_end_reason": "max_iterations_reached",
            }
        
        return None


class ClarificationMiddleware(AgentMiddleware):
    """
    澄清请求拦截中间件：拦截 ask_clarification 工具调用
    
    参考 DeerFlow ClarificationMiddleware
    必须是最后一个执行的中间件
    """
    
    def after_agent(self, state: Dict[str, Any], runtime: RuntimeContext) -> Optional[Dict[str, Any]]:
        """检查是否有澄清请求"""
        tool_calls = state.get("tool_calls", [])
        if not tool_calls:
            return None
        
        # 检查是否有 ask_clarification 调用
        for tc in tool_calls:
            tool_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
            if tool_name == "ask_clarification":
                logger.info("[ClarificationMiddleware] Clarification requested, interrupting")
                return {
                    "_interrupt": "clarification",
                    "_clarification_request": tc,
                }
        
        return None


# ============================================================================
# 中间件工厂
# ============================================================================

def build_default_middlewares(lazy_init: bool = True) -> list:
    """
    构建默认中间件链
    
    参考 DeerFlow build_lead_runtime_middlewares
    
    顺序很重要！基础层在前，功能层在后
    """
    # 基础层
    middlewares = [
        ThreadDataMiddleware(),
        SandboxMiddleware(lazy_init=lazy_init),
        ToolErrorHandlingMiddleware(),
        DanglingToolCallMiddleware(),
    ]
    
    # 功能层
    middlewares.extend([
        TitleMiddleware(),
        MemoryMiddleware(),
        LoopDetectionMiddleware(),
        ClarificationMiddleware(),  # 必须是最后一个
    ])
    
    return middlewares


# ============================================================================
# Phase 5: 迁移 Hooks 到中间件
# ============================================================================

class SecurityMiddleware(AgentMiddleware):
    """
    安全策略中间件：替代 pre-step hook 的安全检查
    
    职责：
    1. 检查工具调用权限
    2. 验证输入参数安全性
    3. 拒绝高危操作（可配置）
    """
    
    def __init__(self, permission_engine: Optional[Any] = None):
        self.permission_engine = permission_engine
    
    async def wrap_tool_call(
        self,
        request: Dict[str, Any],
        handler: Callable
    ) -> Any:
        """工具调用前进行安全检查"""
        tool_name = request.get("name", "")
        tool_args = request.get("args", {})
        
        # 权限检查
        if self.permission_engine:
            try:
                # 检查工具调用权限
                allowed = await self.permission_engine.check_tool(tool_name, tool_args)
                if not allowed:
                    logger.warning("[SecurityMiddleware] Tool call denied: %s", tool_name)
                    raise PermissionError(f"Tool '{tool_name}' is not allowed")
            except Exception as e:
                logger.error("[SecurityMiddleware] Permission check failed: %s", e)
                raise
        
        # 参数安全检查
        self._validate_tool_args(tool_name, tool_args)
        
        # 执行工具调用
        return await handler(request)
    
    def _validate_tool_args(self, tool_name: str, args: Dict[str, Any]) -> None:
        """验证工具参数安全性"""
        # 高危工具参数检查
        if tool_name in ("execute_code", "run_command", "write_file"):
            code = args.get("code", "") or args.get("command", "")
            if self._contains_dangerous_pattern(code):
                logger.warning("[SecurityMiddleware] Dangerous pattern detected in %s", tool_name)
                raise ValueError(f"Dangerous code pattern detected in {tool_name}")
    
    def _contains_dangerous_pattern(self, code: str) -> bool:
        """检查是否包含危险模式"""
        dangerous_patterns = [
            "rm -rf /",
            "chmod 777",
            "sudo rm",
            "drop table",
            "delete from",
            "import os; os.system",
        ]
        return any(pattern in code.lower() for pattern in dangerous_patterns)


class SessionLogMiddleware(AgentMiddleware):
    """
    会话日志中间件：替代 post-step hook 的日志记录
    
    职责：
    1. 记录 think 节点输出
    2. 记录 act 节点工具调用
    3. 记录工具执行结果
    """
    
    def __init__(self, session_log: Optional[Any] = None):
        self.session_log = session_log
        self._session_id: Optional[str] = None
    
    def before_agent(self, state: Dict[str, Any], runtime: RuntimeContext) -> Optional[Dict[str, Any]]:
        """提取 session_id"""
        self._session_id = runtime.session_id
        return None
    
    async def after_agent(
        self,
        state: Dict[str, Any],
        runtime: RuntimeContext,
        action: str
    ) -> Optional[Dict[str, Any]]:
        """记录 agent 执行日志"""
        if not self.session_log or not self._session_id:
            return None
        
        try:
            await self.session_log.append(
                self._session_id,
                f"agent/{action}",
                {"state": state},
            )
        except Exception as e:
            logger.error("[SessionLogMiddleware] Failed to log: %s", e)
        
        return None
    
    async def wrap_tool_call(
        self,
        request: Dict[str, Any],
        handler: Callable
    ) -> Any:
        """记录工具调用和结果"""
        if not self.session_log or not self._session_id:
            return await handler(request)
        
        # 记录工具调用
        await self.session_log.append(
            self._session_id,
            "tool/call",
            {"request": request},
        )
        
        # 执行工具
        try:
            result = await handler(request)
            
            # 记录工具结果
            await self.session_log.append(
                self._session_id,
                "tool/result",
                {"result": result},
            )
            
            return result
        except Exception as e:
            # 记录工具错误
            await self.session_log.append(
                self._session_id,
                "tool/error",
                {"error": str(e)},
            )
            raise


class CheckpointMiddleware(AgentMiddleware):
    """
    检查点中间件：替代检查点管理
    
    职责：
    1. 执行前恢复检查点
    2. 执行后保存检查点
    """
    
    def __init__(self, checkpoint: Optional[Any] = None):
        self.checkpoint = checkpoint
        self._restored = False
    
    async def before_agent(
        self,
        state: Dict[str, Any],
        runtime: RuntimeContext
    ) -> Optional[Dict[str, Any]]:
        """恢复检查点"""
        if not self.checkpoint or self._restored:
            return None
        
        try:
            if self.checkpoint.has_checkpoint():
                checkpoint_data = await self.checkpoint.restore()
                logger.info("[CheckpointMiddleware] Restored from checkpoint")
                self._restored = True
                return checkpoint_data
        except Exception as e:
            logger.error("[CheckpointMiddleware] Failed to restore: %s", e)
        
        return None
    
    async def after_agent(
        self,
        state: Dict[str, Any],
        runtime: RuntimeContext,
        action: str
    ) -> Optional[Dict[str, Any]]:
        """保存检查点"""
        if not self.checkpoint:
            return None
        
        try:
            await self.checkpoint.save(state)
            logger.debug("[CheckpointMiddleware] Checkpoint saved")
        except Exception as e:
            logger.error("[CheckpointMiddleware] Failed to save: %s", e)
        
        return None
