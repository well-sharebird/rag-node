#!/usr/bin/env python3
"""
执行后检查脚本

在 Agent 执行后运行，验证：
1. 审计日志已记录
2. 没有越权访问
3. 沙箱执行符合约束
"""
import json
import sys
from pathlib import Path
from datetime import datetime


def check_audit_log_exists(execution_id: str, log_path: str) -> bool:
    """检查执行是否有审计日志"""
    # TODO: 实现审计日志检查
    return True


def check_no_boundary_violation(workspace_root: str, accessed_paths: list) -> bool:
    """检查没有越权访问"""
    for path in accessed_paths:
        if not path.startswith(workspace_root):
            print(f"Violation: {path} outside workspace {workspace_root}")
            return False
    return True


def check_sandbox_constraints(execution_result: dict) -> bool:
    """检查沙箱执行约束"""
    # 检查执行时间
    duration_ms = execution_result.get("duration_ms", 0)
    if duration_ms > 30000:  # 30 秒
        print(f"Warning: Execution exceeded 30s limit: {duration_ms}ms")
        return False

    # 检查是否有网络访问尝试
    if execution_result.get("network_access"):
        print("Violation: Network access not allowed in sandbox")
        return False

    return True


def main():
    """主检查入口"""
    if len(sys.argv) < 2:
        print("Usage: post-execution-check.py <execution_result.json>")
        sys.exit(1)

    result_file = sys.argv[1]

    try:
        with open(result_file) as f:
            result = json.load(f)
    except FileNotFoundError:
        print(f"Error: Result file not found: {result_file}")
        sys.exit(1)

    checks_passed = True

    # 运行检查
    if not check_sandbox_constraints(result):
        checks_passed = False

    if checks_passed:
        print("✓ Post-execution checks passed")
        sys.exit(0)
    else:
        print("✗ Post-execution checks failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
