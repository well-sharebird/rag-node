"""
Phase 3: 沙箱生命周期 + 子 Agent 配置完整测试

验证：
    - SandboxScope 进入创建、退出销毁隔离工作区
    - SandboxRuntime 接受任务级 workdir
    - load_sub_agent 读取 sandbox_policy / memory_strategy / inherit_main_context
"""
import os

import pytest

from packages.agent.orchestrator.agent_loader import AgentLoader
from packages.agent.harness.sandbox.runtime import SandboxRuntime, SandboxScope, check_code_safety


class FakeWs:
    def __init__(self, root):
        self.root_path = root


class TestSandboxScope:

    @pytest.mark.asyncio
    async def test_create_and_destroy(self, tmp_path, monkeypatch):
        scope = SandboxScope(db=object(), user_id=1, session_id="s", policy={"timeout_seconds": 30})

        async def fake_get_workspace():
            return FakeWs(str(tmp_path))

        monkeypatch.setattr(scope, "get_workspace", fake_get_workspace)

        async with scope as entered:
            assert entered.workdir is not None
            assert os.path.isdir(entered.workdir)
            # 沙箱执行落于任务级工作目录
            os.makedirs(os.path.join(entered.workdir, "sub"), exist_ok=True)
            workdir = entered.workdir

        # 退出后销毁（防逃逸/残留）
        assert not os.path.exists(workdir)

    @pytest.mark.asyncio
    async def test_destroy_even_on_error(self, tmp_path, monkeypatch):
        scope = SandboxScope(db=object(), user_id=1, session_id="s")

        async def fake_get_workspace():
            return FakeWs(str(tmp_path))

        monkeypatch.setattr(scope, "get_workspace", fake_get_workspace)

        with pytest.raises(RuntimeError):
            async with scope:
                assert os.path.isdir(scope.workdir)
                raise RuntimeError("boom")

        assert not os.path.exists(scope.workdir)  # 异常路径同样销毁


class TestSandboxRuntimeWorkdir:

    def test_accepts_task_workdir(self):
        rt = SandboxRuntime(db=None, user_id=1, session_id="s", workdir="/tmp/x")
        assert rt.workdir == "/tmp/x"

    def test_code_safety_still_active(self):
        assert check_code_safety('os.system("rm -rf /")')  # 命中危险拦截
        assert check_code_safety("x = 1 + 1") is None


class TestSubAgentConfigCompleteness:

    @pytest.mark.asyncio
    async def test_load_sub_agent_reads_new_fields(self, monkeypatch):
        class FakeAgent:
            id = "11111111-1111-1111-1111-111111111111"
            name = "sub"
            system_prompt = "sys"
            security_policy = {"allowed_tools": ["search"], "require_approval_tools": ["kill"]}
            extensions_config = {"inherit_main_context": True}
            sandbox_policy = {"timeout_seconds": 30}
            memory_strategy = {"type": "vector"}
            memory_type = "conversation"
            default_model_config = {}

        class FakeService:
            def __init__(self, db):
                pass

            async def get_by_id(self, i):
                return FakeAgent()

        monkeypatch.setattr(
            "packages.agent.services.agent_config_service.AgentConfigService", FakeService
        )
        loader = AgentLoader(db=object())

        cfg = await loader.load_sub_agent("x")
        assert cfg.sandbox_policy == {"timeout_seconds": 30}
        assert cfg.raw["memory_strategy"] == {"type": "vector"}
        assert cfg.inherit_main_context is True
