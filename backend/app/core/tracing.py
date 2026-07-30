"""
执行追踪装饰器和上下文管理

用法:
    @traceable(node_type='parsing', node_name='parse_document')
    async def parse_document(doc_id: str):
        ...

设计原则:
    1. 追踪失败不影响核心业务
    2. 静默失败，只记录警告日志
    3. 支持 async 和 sync 函数
    4. 追踪服务全局单例，业务代码无需初始化
"""
import functools
import time
import asyncio
import logging
from typing import Optional, Callable, Any, Dict
from contextvars import ContextVar
from contextlib import asynccontextmanager

from app.services.trace_service import TraceService, TraceContext

logger = logging.getLogger(__name__)

# 线程本地存储追踪上下文
_trace_context: ContextVar[Optional[TraceContext]] = ContextVar('trace_context', default=None)
_trace_service: ContextVar[Optional[TraceService]] = ContextVar('trace_service', default=None)

# 全局追踪服务单例（由 main.py 在启动时初始化）
_global_trace_service: Optional[TraceService] = None


def get_trace_context() -> Optional[TraceContext]:
    """获取当前追踪上下文"""
    return _trace_context.get()


def set_trace_context(ctx: Optional[TraceContext]):
    """设置追踪上下文"""
    _trace_context.set(ctx)


def get_trace_service() -> Optional[TraceService]:
    """获取追踪服务实例（优先返回全局单例）"""
    local = _trace_service.get()
    if local:
        return local
    return _global_trace_service


def set_trace_service(service: Optional[TraceService]):
    """设置追踪服务实例"""
    _trace_service.set(service)


def init_global_trace_service(es_client):
    """初始化全局追踪服务单例（在 main.py 启动时调用）"""
    global _global_trace_service
    _global_trace_service = TraceService(es_client)
    logger.info("Global trace service initialized")


async def ensure_trace_index():
    """确保追踪索引存在（在 main.py 启动时调用）"""
    if _global_trace_service:
        await _global_trace_service.ensure_index()
        logger.info("Trace indices ensured")


def traceable(
    node_type: str,
    node_name: Optional[str] = None,
    capture_input: bool = True,
    capture_output: bool = True,
    capture_error: bool = True,
):
    """
    追踪装饰器 - 用于自动记录函数执行

    注意：追踪失败不会影响核心业务逻辑

    Args:
        node_type: 节点类型 (e.g., 'parsing', 'chunking', 'agent_node', 'tool_call')
        node_name: 节点名称 (默认使用函数名)
        capture_input: 是否捕获输入参数
        capture_output: 是否捕获输出结果
        capture_error: 是否捕获错误信息

    Example:
        @traceable(node_type='parsing', node_name='parse_pdf')
        async def parse_pdf(file_path: str) -> str:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            ctx = get_trace_context()
            service = get_trace_service()

            if not ctx or not service:
                # 没有追踪上下文，直接执行
                return await func(*args, **kwargs)

            actual_node_name = node_name or func.__name__

            # 准备输入数据
            input_data = None
            if capture_input:
                try:
                    input_data = _safe_capture_args(args, kwargs)
                except Exception as e:
                    logger.debug("Failed to capture input for %s: %s", actual_node_name, e)
                    input_data = {'error': 'Failed to capture input'}

            span_id = None
            try:
                # 开始追踪
                span_id = await service.start_span(
                    ctx=ctx,
                    node_type=node_type,
                    node_name=actual_node_name,
                    input_data=input_data,
                )
            except Exception as e:
                # 追踪失败不影响核心业务
                logger.debug("Failed to start span for %s: %s", actual_node_name, e)

            start_time = time.time()
            try:
                result = await func(*args, **kwargs)

                # 准备输出数据
                output_data = None
                if capture_output:
                    try:
                        output_data = _safe_capture_result(result)
                    except Exception as e:
                        logger.debug("Failed to capture output for %s: %s", actual_node_name, e)
                        output_data = {'error': 'Failed to capture output'}

                # 结束追踪
                if span_id:
                    try:
                        await service.end_span(
                            ctx=ctx,
                            span_id=span_id,
                            output_data=output_data,
                        )
                    except Exception as e:
                        logger.debug("Failed to end span for %s: %s", actual_node_name, e)

                return result

            except Exception as e:
                if span_id:
                    try:
                        await service.end_span(
                            ctx=ctx,
                            span_id=span_id,
                            error=e,
                        )
                    except Exception as span_error:
                        logger.debug("Failed to end span for %s: %s", actual_node_name, span_error)
                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            ctx = get_trace_context()
            service = get_trace_service()

            if not ctx or not service:
                # 没有追踪上下文，直接执行
                return func(*args, **kwargs)

            actual_node_name = node_name or func.__name__

            input_data = None
            if capture_input:
                try:
                    input_data = _safe_capture_args(args, kwargs)
                except Exception as e:
                    logger.debug("Failed to capture input for %s: %s", actual_node_name, e)
                    input_data = {'error': 'Failed to capture input'}

            span_id = None
            try:
                # 检测是否有运行的事件循环
                try:
                    asyncio.get_running_loop()
                    # 有运行的事件循环，使用 run_coroutine_threadsafe
                    loop = asyncio.get_event_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        service.start_span(
                            ctx=ctx,
                            node_type=node_type,
                            node_name=actual_node_name,
                            input_data=input_data,
                        ),
                        loop
                    )
                    span_id = future.result(timeout=60)
                except RuntimeError:
                    # 没有运行的事件循环，使用 asyncio.run
                    span_id = asyncio.run(service.start_span(
                        ctx=ctx,
                        node_type=node_type,
                        node_name=actual_node_name,
                        input_data=input_data,
                    ))
            except Exception as e:
                # 追踪失败不影响核心业务
                logger.warning("Failed to start span for %s: %s", actual_node_name, e)

            start_time = time.time()
            try:
                result = func(*args, **kwargs)

                # 准备输出数据
                output_data = None
                if capture_output:
                    try:
                        output_data = _safe_capture_result(result)
                    except Exception as e:
                        logger.debug("Failed to capture output for %s: %s", actual_node_name, e)
                        output_data = {'error': 'Failed to capture output'}

                # 结束追踪
                if span_id:
                    try:
                        # 检测是否有运行的事件循环
                        try:
                            asyncio.get_running_loop()
                            # 有运行的事件循环，使用 run_coroutine_threadsafe
                            loop = asyncio.get_event_loop()
                            future = asyncio.run_coroutine_threadsafe(
                                service.end_span(
                                    ctx=ctx,
                                    span_id=span_id,
                                    output_data=output_data,
                                ),
                                loop
                            )
                            future.result(timeout=60)
                        except RuntimeError:
                            # 没有运行的事件循环，使用 asyncio.run
                            asyncio.run(service.end_span(
                                ctx=ctx,
                                span_id=span_id,
                                output_data=output_data,
                            ))
                    except Exception as e:
                        logger.debug("Failed to end span for %s: %s", actual_node_name, e)

                return result

            except Exception as e:
                if span_id:
                    try:
                        # 检测是否有运行的事件循环
                        try:
                            asyncio.get_running_loop()
                            # 有运行的事件循环，使用 run_coroutine_threadsafe
                            loop = asyncio.get_event_loop()
                            future = asyncio.run_coroutine_threadsafe(
                                service.end_span(
                                    ctx=ctx,
                                    span_id=span_id,
                                    error=e,
                                ),
                                loop
                            )
                            future.result(timeout=60)
                        except RuntimeError:
                            # 没有运行的事件循环，使用 asyncio.run
                            asyncio.run(service.end_span(
                                ctx=ctx,
                                span_id=span_id,
                                error=e,
                            ))
                    except Exception as span_error:
                        logger.debug("Failed to end span for %s: %s", actual_node_name, span_error)
                raise

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


def _safe_capture_args(args: tuple, kwargs: dict, max_len: int = 500) -> dict:
    """安全捕获函数参数"""
    captured = {
        'args_count': len(args),
        'kwargs_count': len(kwargs),
    }

    if args:
        captured['args'] = [_truncate(str(arg), max_len) for arg in args[:5]]

    if kwargs:
        captured['kwargs'] = {
            k: _truncate(str(v), max_len)
            for k, v in list(kwargs.items())[:10]
        }

    return captured


def _safe_capture_result(result: Any, max_len: int = 2000) -> dict:
    """安全捕获函数返回值"""
    if result is None:
        return {'result': None}

    if isinstance(result, (str, int, float, bool)):
        return {'result': _truncate(str(result), max_len)}

    if isinstance(result, (list, tuple)):
        return {
            'type': type(result).__name__,
            'length': len(result),
            'preview': [_truncate(str(item), 100) for item in result[:5]],
        }

    if isinstance(result, dict):
        return {
            'type': 'dict',
            'keys': list(result.keys())[:10],
            'preview': {k: _truncate(str(v), 200) for k, v in list(result.items())[:5]},
        }

    return {
        'type': type(result).__name__,
        'str': _truncate(str(result), max_len),
    }


def _truncate(s: str, max_len: int) -> str:
    """截断字符串"""
    if len(s) <= max_len:
        return s
    return s[:max_len] + '...'


@asynccontextmanager
async def trace_execution(
    execution_type: str,
    execution_id: str,
    user_id: Optional[int] = None,
    trace_service: Optional[TraceService] = None,
):
    """
    上下文管理器 - 用于手动控制追踪范围

    设计原则:
        1. 追踪失败不影响核心业务
        2. 静默失败，只记录警告日志
        3. 优先使用全局追踪服务，业务代码无需初始化

    Args:
        execution_type: 执行类型 ('document_pipeline' | 'agent_execution')
        execution_id: 执行 ID (文档 ID 或 Agent ID)
        user_id: 用户 ID
        trace_service: 追踪服务实例（可选，默认使用全局单例）

    Example:
        async with trace_execution('document_pipeline', doc_id) as ctx:
            await process_document(doc_id)
    """
    ctx = TraceContext(
        execution_type=execution_type,
        execution_id=execution_id,
        user_id=user_id,
    )

    # 优先使用传入的 service，其次使用全局单例
    service = trace_service or get_trace_service()

    # 设置上下文
    set_trace_context(ctx)
    if service:
        set_trace_service(service)

    try:
        yield ctx
    except Exception as e:
        # 异常时尝试完成追踪
        try:
            await service.finalize(ctx)
        except Exception as finalize_error:
            logger.debug("Failed to finalize trace on error: %s", finalize_error)
        raise
    else:
        # 正常完成追踪
        try:
            await service.finalize(ctx)
        except Exception as finalize_error:
            logger.debug("Failed to finalize trace: %s", finalize_error)
    finally:
        # 清理上下文
        set_trace_context(None)
        set_trace_service(None)
