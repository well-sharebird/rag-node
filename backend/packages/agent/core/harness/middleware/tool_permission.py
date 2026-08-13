"""工具权限护栏纯函数 - Harness 中间件（设计文档 2.5）

把 `SecurityGuardMiddleware` 的安全策略判定拆成可独立调用的纯函数，
供工具执行唯一门面（ToolExecutionManager）在节点内强制调用。
符合"节点强制 / 中间件观测"分层：此处的返回用于拦截，中间件仅负责观测记录。

Policy 结构（与 SecurityGuardMiddleware/agent_config.security_policy 对齐）：
    {
        "blocked_tools": [..],   # 阻断名单：命中即拒绝
        "allowed_tools": [..],   # 白名单：非空时仅名单内工具放行
    }
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# 简单敏感字段名，参数清洗时脱敏
_SENSITIVE_KEYS = {"password", "secret", "token", "api_key", "apikey", "authorization", "bearer"}


def run_tool_permission_check(
    tool_name: str,
    tool_params: Optional[dict] = None,
    policy: Optional[dict] = None,
) -> Optional[str]:
    """白名单/阻断校验。放行返回 None，拦截返回拒绝原因字符串。

    与 `SecurityGuardMiddleware._scan` 逻辑一致，但作用对象为单次工具调用、
    直接返回可拦截的判断结果（而非仅观测事件）。
    """
    policy = policy or {}
    blocked = set(policy.get("blocked_tools") or [])
    allowed = set(policy.get("allowed_tools") or [])

    if tool_name in blocked:
        return f"工具 {tool_name} 在阻断名单中"
    if allowed and tool_name not in allowed:
        return f"工具 {tool_name} 不在授权白名单中"
    return None


def clean_tool_params(tool_name: str, tool_params: Optional[dict] = None) -> dict:
    """工具参数清洗：仅做敏感字段脱敏，返回新 dict（不修改入参）。

    注意：**不截断超长值**——此处入参会原样用于真实工具执行（如长脚本 code、
    长文件 content 均需完整透传）。截断属审计/日志展示职责，不得用于执行输入，
    否则会破坏写文件/代码执行类工具。
    """
    if not tool_params:
        return {}
    cleaned: Dict[str, Any] = {}
    for key, val in tool_params.items():
        if any(s in key.lower() for s in _SENSITIVE_KEYS):
            cleaned[key] = "***"
            continue
        cleaned[key] = val
    return cleaned
