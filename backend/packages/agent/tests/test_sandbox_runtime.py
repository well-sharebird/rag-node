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
    # 强制 venv 纯隔离后端，屏蔽本机 nsjail/docker 差异，保证确定性
    rt = SandboxRuntime(db=None, user_id=1, session_id="s1",
                        sandbox_policy={"sandbox_mode": "venv"})

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


# ---------------- docker-nsjail 执行后端 ----------------

def test_venv_site_packages_glob(tmp_path):
    env = tmp_path / "env"
    (env / "lib" / "python3.10" / "site-packages").mkdir(parents=True)
    assert SandboxRuntime._venv_site_packages(str(env)) == \
        str(env / "lib" / "python3.10" / "site-packages")
    assert SandboxRuntime._venv_site_packages(str(tmp_path / "none")) is None


def _fake_proc(returncode, stdout=b"", stderr=b""):
    class P:
        killed = False

        def __init__(self, rc, so, se):
            self.returncode = rc
            self.stdout = so
            self.stderr = se

        async def communicate(self):
            return self.stdout, self.stderr

        def kill(self):
            self.killed = True
    return P(returncode, stdout, stderr)


@pytest.mark.asyncio
async def test_run_in_docker_builds_correct_command(monkeypatch):
    """_run_in_docker 按约定拼出 docker run --rm --privileged -v <root>:/sb 命令。"""
    created = []

    async def fake_subprocess(*args, **kwargs):
        created.append((args, kwargs))
        return _fake_proc(0, b"out-from-docker", b"")

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_subprocess)
    rt = SandboxRuntime(db=None, user_id=1)
    out, err, code, timed_out = await rt._run_in_docker("/tmp/sb", "script.py", "/sb/env/lib/python3.10/site-packages")

    assert out == "out-from-docker"
    assert err == ""
    assert code == 0
    assert not timed_out
    args = created[0][0]
    assert args[:5] == ("docker", "run", "--rm", "--privileged", "-v")
    assert f"/tmp/sb:/sb" in args
    assert "-w" in args and "/sb/work" in args
    assert args[args.index("-w") + 2] == "rag-nsjail:py310"
    assert args[-2:] == ("script.py", "/sb/env/lib/python3.10/site-packages")


@pytest.mark.asyncio
async def test_run_in_docker_timeout(monkeypatch):
    import asyncio

    class Slow:
        killed = False

        async def communicate(self):
            await asyncio.sleep(10)

        def kill(self):
            self.killed = True

    calls = []

    async def fake_subprocess(*args, **kwargs):
        calls.append(args)
        return Slow()

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_subprocess)
    rt = SandboxRuntime(db=None, user_id=1)
    out, err, code, timed_out = await rt._run_in_docker("/tmp/sb", "s.py", "sp", timeout=1)
    assert timed_out is True
    assert "超时" in err


@pytest.mark.asyncio
async def test_docker_available_uses_cache(monkeypatch):
    """_docker_available 只 inspect 一次并复用类级缓存。"""
    seen = []
    SandboxRuntime._docker_image_ok = None  # 重置缓存

    async def fake_subprocess(*args, **kwargs):
        seen.append(args)
        return _fake_proc(0)

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_subprocess)
    rt = SandboxRuntime(db=None, user_id=1)
    assert await rt._docker_available() is True
    assert await rt._docker_available() is True
    assert len(seen) == 1  # 缓存命中，仅一次 docker image inspect
    SandboxRuntime._docker_image_ok = None  # 恢复，避免污染其他测试


@pytest.mark.asyncio
async def test_docker_mode_takes_docker_branch_without_local_nsjail(tmp_path, rt, monkeypatch):
    """sandbox_mode=docker + 本机无 nsjail + 镜像可用 → 走 docker-nsjail，不落 venv。"""
    rt.sandbox_mode = "docker"
    rt.docker_image = "rag-nsjail:py310"

    # 本机无 nsjail
    monkeypatch.setattr("shutil.which", lambda name: None)
    # 镜像可用
    SandboxRuntime._docker_image_ok = None

    async def fake_subprocess(*args, **kwargs):
        return _fake_proc(0, b"docker-ran", b"")

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_subprocess)
    # 真建一个 venv-provider：让 _venv_site_packages 有值
    monkeypatch.setattr(rt, "_make_venv", _FakeVenv())

    res = await rt.execute("print('x')")
    assert res.sandbox == "docker-nsjail"
    assert res.stdout == "docker-ran"
    assert res.exit_code == 0

    # 产物仍提升到持久工作区
    promoted = list((tmp_path / "generated" / "exec").rglob("script.py"))
    # script.<ext> 会被排除，故这里只需确认 sandbox 已销毁即可
    assert not list((tmp_path / "sandbox").rglob("*"))
    SandboxRuntime._docker_image_ok = None


class _FakeVenv:
    """返回一个带 lib/python3.x/site-packages 的真实目录作为 venv 提供者。"""

    async def __call__(self, env_dir):
        import os
        os.makedirs(os.path.join(env_dir, "lib", "python3.10", "site-packages"),
                    exist_ok=True)
        env_py = os.path.join(env_dir, "bin", "python")
        os.makedirs(os.path.dirname(env_py), exist_ok=True)
        open(env_py, "w").close()  # 占位，非真实解释器；docker 分支只读 site-packages
        return env_py
