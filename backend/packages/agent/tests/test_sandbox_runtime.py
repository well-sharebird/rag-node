"""SandboxRuntime 沙箱生命周期测试。

验证用户约定：python 只在隔离 venv 执行、自动安装缺失依赖、产物提升到持久工作区、
运行结束（含超时/失败）确定性销毁 sandbox_root。用 tmp_path 假工作区，DB 写操作
（register_file/log_action）以 mock 代替，产出文件走真实磁盘以便断言。
"""
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from packages.agent.core.harness.sandbox.runtime import SandboxRuntime
from packages.agent.services.workspace_service import WorkspaceService


@pytest.fixture
def rt(tmp_path, monkeypatch):
    rt = SandboxRuntime(db=None, user_id=1, session_id="s1")

    async def fake_get_workspace():
        return SimpleNamespace(root_path=str(tmp_path), id="ws1")

    monkeypatch.setattr(rt, "get_workspace", fake_get_workspace)
    # DB 写操作以 mock 代替（产物文件本身真实落盘，用于断言提升/销毁）
    monkeypatch.setattr(
        WorkspaceService, "register_file",
        AsyncMock(return_value=SimpleNamespace(id="f1")),
    )
    monkeypatch.setattr(WorkspaceService, "log_action", AsyncMock())
    return rt


@pytest.mark.asyncio
async def test_execute_promotes_product_and_destroys_sandbox(tmp_path, rt):
    code = 'import os\nwith open("out.txt", "w") as f: f.write("hi")\nprint("done")'
    res = await rt.execute(code)

    assert res.sandbox == "venv"
    assert res.exit_code == 0
    assert "done" in res.stdout

    # 产物被提升到持久工作区 generated/exec/<ts>/out.txt（真实磁盘）
    promoted = list((tmp_path / "generated" / "exec").rglob("out.txt"))
    assert len(promoted) == 1
    assert promoted[0].read_text() == "hi"

    # res.files 指向稳定相对路径（非临时 exec 目录）
    assert res.files and res.files[0]["filename"] == "out.txt"
    assert res.files[0]["relative_path"].startswith("generated/exec/")

    # 沙箱运行时（venv + 临时执行目录）已整体销毁，无残留内容
    assert not list((tmp_path / "sandbox").rglob("*"))


@pytest.mark.asyncio
async def test_auto_install_calls_pip_for_declared(tmp_path, rt, monkeypatch):
    calls = []

    async def fake_make_venv(env_dir):
        os.makedirs(env_dir, exist_ok=True)
        return sys.executable

    async def fake_install(env_py, deps):
        calls.append((env_py, list(deps)))

    monkeypatch.setattr(rt, "_make_venv", fake_make_venv)
    monkeypatch.setattr(rt, "_install_deps", fake_install)

    # 显式声明依赖 → 调用 _install_deps
    await rt.execute("pass", requirements=["pandas"])
    assert calls and calls[0][1] == ["pandas"]

    # 纯标准库代码 → 不触发安装
    calls.clear()
    await rt.execute("import os\npass")
    assert calls == []


@pytest.mark.asyncio
async def test_python_refuses_when_no_venv(tmp_path, rt, monkeypatch):
    async def fake_make_venv(env_dir):
        return None

    monkeypatch.setattr(rt, "_make_venv", fake_make_venv)
    res = await rt.execute("print('x')")
    assert res.sandbox == "error"
    assert res.exit_code == 1
    assert "拒绝" in res.stderr


@pytest.mark.asyncio
async def test_blocked_code_not_executed(tmp_path, rt):
    res = await rt.execute("import os\nos.system('ls')")
    assert res.blocked is not None
    assert res.exit_code == 0  # 未真正执行
