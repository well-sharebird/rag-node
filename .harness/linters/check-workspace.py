#!/usr/bin/env python3
"""
工作区边界检查 Linter

检查文件操作是否越权访问工作区边界
"""
import os
import sys
from pathlib import Path


def check_workspace_boundary(requested_path: str, workspace_root: str) -> bool:
    """
    检查请求路径是否在工作区边界内

    Returns:
        True = 合法，False = 越权
    """
    # 规范化路径
    requested = os.path.normpath(requested_path)
    root = os.path.normpath(workspace_root)

    # 检查是否以工作区根目录开头
    if not requested.startswith(root):
        return False

    # 检查符号链接
    if os.path.islink(requested):
        real_path = os.path.realpath(requested)
        if not real_path.startswith(root):
            return False

    return True


def main():
    """命令行检查入口"""
    if len(sys.argv) < 3:
        print("Usage: check-workspace.py <workspace_root> <requested_path>")
        sys.exit(1)

    workspace_root = sys.argv[1]
    requested_path = sys.argv[2]

    if check_workspace_boundary(requested_path, workspace_root):
        print(f"✓ Path OK: {requested_path}")
        sys.exit(0)
    else:
        print(f"✗ Boundary violation: {requested_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
