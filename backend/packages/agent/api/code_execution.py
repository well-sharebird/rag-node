"""
代码执行 API

提供安全的沙箱代码执行能力
"""
import logging
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from packages.core.database import get_db
from packages.core.auth import get_current_user
from packages.core.system.models.user import User

from packages.agent.models.runtime import AgentRuntime
from packages.agent.models.session import AgentSession
from packages.agent.models.workspace import Workspace, WorkspaceFile
from packages.agent.sandbox.nsjail import execute_code_in_sandbox, ExecutionResult
from packages.agent.services.workspace_service import WorkspaceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/code-execution", tags=["code-execution"])


class CodeExecutionRequest(BaseModel):
    """代码执行请求"""
    code: str = Field(..., description="要执行的代码", min_length=1, max_length=50000)
    language: Literal["python", "node", "bash"] = Field(default="python", description="编程语言")
    session_id: Optional[str] = Field(None, description="关联的 Session ID")
    timeout_seconds: int = Field(default=30, ge=1, le=300, description="超时时间（秒）")


class CodeExecutionResponse(BaseModel):
    """代码执行响应"""
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    timed_out: bool = False
    error_message: Optional[str] = None


@router.post("/execute", response_model=CodeExecutionResponse)
async def execute_code(
    request: CodeExecutionRequest,
    runtime_id: str = Body(..., description="Runtime ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    在沙箱中执行代码

    使用 nsjail 提供轻量级隔离，确保：
    1. 文件系统隔离 - 只能访问用户工作区
    2. 系统调用限制 - seccomp 过滤危险调用
    3. 资源限制 - CPU、内存、时间限制
    4. 网络隔离 - 默认禁止网络访问
    """
    # 验证 Runtime
    result = await db.execute(
        select(AgentRuntime).where(AgentRuntime.id == runtime_id)
    )
    runtime = result.scalar_one_or_none()

    if not runtime:
        raise HTTPException(status_code=404, detail="Runtime not found")

    # 权限检查
    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace(runtime.workspace_id)

    if not workspace or workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No permission")

    # 检查 Runtime 状态
    if runtime.status not in ["running", "sleeping"]:
        raise HTTPException(
            status_code=400,
            detail=f"Runtime not ready. Status: {runtime.status}"
        )

    # 如果需要，唤醒 Runtime
    if runtime.status == "sleeping":
        from packages.agent.services.runtime_service import RuntimeService
        runtime_svc = RuntimeService(db)
        await runtime_svc.wake_runtime(runtime_id)

    # 验证代码安全（基本检查）
    security_check = _check_code_security(request.code, request.language)
    if not security_check["safe"]:
        raise HTTPException(
            status_code=400,
            detail=f"Code security check failed: {security_check['reason']}"
        )

    # 获取工作区路径
    workspace_path = workspace.root_path
    if request.session_id:
        # 如果有 session_id，限定在 session 目录
        import os
        workspace_path = os.path.join(workspace_path, "sessions", request.session_id)

    try:
        # 在沙箱中执行代码
        result: ExecutionResult = await execute_code_in_sandbox(
            code=request.code,
            language=request.language,
            workspace_path=workspace_path,
            timeout_seconds=request.timeout_seconds,
        )

        # 记录审计日志
        await workspace_service.log_action(
            workspace=workspace,
            action="execute",
            file_path=f"sandbox:{request.language}",
            user_id=current_user.id,
            runtime_id=runtime_id,
            session_id=request.session_id,
            success=(result.exit_code == 0),
        )

        # 如果有输出文件，注册到文件索引
        if result.stdout and len(result.stdout) > 1000:
            # 大输出保存到文件
            await _save_large_output(
                db, workspace, result.stdout, runtime_id, request.session_id
            )

        return CodeExecutionResponse(
            success=(result.exit_code == 0),
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            timed_out=result.timed_out,
        )

    except Exception as e:
        logger.error(f"Code execution failed: {e}")

        # 记录错误
        await workspace_service.log_action(
            workspace=workspace,
            action="execute",
            file_path=f"sandbox:{request.language}",
            user_id=current_user.id,
            runtime_id=runtime_id,
            session_id=request.session_id,
            success=False,
            error_message=str(e),
        )

        raise HTTPException(
            status_code=500,
            detail=f"Code execution failed: {str(e)}"
        )


class SecurityCheckResult(BaseModel):
    safe: bool
    reason: Optional[str] = None


def _check_code_security(code: str, language: str) -> SecurityCheckResult:
    """
    代码安全检查

    检查潜在的危险模式：
    1. 文件系统访问
    2. 网络访问
    3. 子进程执行
    4. 反序列化
    """
    dangerous_patterns = {
        "python": [
            ("__import__('os')", "Direct os module import"),
            ("__import__('subprocess')", "Direct subprocess module import"),
            ("os.system(", "os.system call"),
            ("os.popen(", "os.popen call"),
            ("subprocess.", "subprocess module"),
            ("eval(", "eval function"),
            ("exec(", "exec function"),
            ("compile(", "compile function"),
            ("__import__(", "__import__ function"),
            ("open('/etc/", "Access to /etc"),
            ("open('/proc/", "Access to /proc"),
            ("socket.", "socket module"),
            ("requests.", "requests module"),
            ("urllib.", "urllib module"),
            ("pickle.", "pickle module (deserialization)"),
            ("yaml.load(", "yaml.load (unsafe)"),
            ("marshal.", "marshal module"),
        ],
        "node": [
            ("require('child_process')", "child_process module"),
            ("require('fs')", "fs module"),
            ("require('net')", "net module"),
            ("require('http')", "http module"),
            ("require('https')", "https module"),
            ("eval(", "eval function"),
            ("Function(", "Function constructor"),
        ],
        "bash": [
            ("curl ", "curl command"),
            ("wget ", "wget command"),
            ("nc ", "netcat command"),
            ("netcat ", "netcat command"),
            ("/dev/tcp", "TCP redirect"),
            ("/dev/udp", "UDP redirect"),
        ],
    }

    patterns = dangerous_patterns.get(language, [])

    for pattern, reason in patterns:
        if pattern in code:
            # 某些模式可能是合法的（如 print 语句中的 eval 字符串）
            # 这里只做基本检查，更复杂的需要 AST 分析
            return SecurityCheckResult(
                safe=False,
                reason=f"Dangerous pattern detected: {reason}"
            )

    return SecurityCheckResult(safe=True)


async def _save_large_output(
    db: AsyncSession,
    workspace: Workspace,
    output: str,
    runtime_id: str,
    session_id: Optional[str],
):
    """保存大输出到文件"""
    import os
    import hashlib

    # 生成文件名
    file_hash = hashlib.sha256(output.encode()).hexdigest()[:8]
    filename = f"output_{file_hash}.txt"

    # 确定保存路径
    if session_id:
        rel_path = f"sessions/{session_id}/outputs/{filename}"
    else:
        rel_path = f"outputs/{filename}"

    abs_path = os.path.join(workspace.root_path, rel_path)

    # 确保目录存在
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    # 写入文件
    with open(abs_path, "w") as f:
        f.write(output)

    # 注册文件
    workspace_service = WorkspaceService(db)
    await workspace_service.register_file(
        workspace=workspace,
        filename=filename,
        relative_path=rel_path,
        file_size=len(output.encode()),
        mime_type="text/plain",
        runtime_id=runtime_id,
        session_id=session_id,
        source_type="generated",
        is_sandbox_generated=True,
    )
