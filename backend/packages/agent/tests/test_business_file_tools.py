"""文件生成：save_workspace_file 参数校验 + 编排目录可见性 测试"""
import pytest

from packages.agent.orchestrator.business_tools import (
    _validate_workspace_target,
    ALLOWED_FILE_EXTENSIONS,
)


# ============================================================
# _validate_workspace_target
# ============================================================

class TestValidateWorkspaceTarget:
    def test_valid_filename_no_folder(self):
        assert _validate_workspace_target("report.md", "") is None
        assert _validate_workspace_target("script.py", "") is None

    def test_valid_filename_with_folder(self):
        assert _validate_workspace_target("config.json", "docs") is None
        assert _validate_workspace_target("a.yaml", "nested/dir") is None

    def test_empty_filename(self):
        assert _validate_workspace_target("", "") is not None

    def test_path_traversal_rejected(self):
        assert _validate_workspace_target("../evil.py", "") is not None
        assert _validate_workspace_target("a/../../evil.py", "") is not None

    def test_absolute_path_rejected(self):
        assert _validate_workspace_target("/etc/passwd", "") is not None

    def test_separator_in_filename_rejected(self):
        assert _validate_workspace_target("dir/x.py", "") is not None
        assert _validate_workspace_target("x\\y.py", "") is not None

    def test_unsupported_extension_rejected(self):
        assert _validate_workspace_target("virus.exe", "") is not None
        assert _validate_workspace_target("image.png", "") is not None
        assert _validate_workspace_target("noext", "") is not None

    @pytest.mark.parametrize("ext", ALLOWED_FILE_EXTENSIONS)
    def test_allowed_extensions(self, ext):
        assert _validate_workspace_target(f"file{ext}", "") is None

    def test_bad_folder(self):
        assert _validate_workspace_target("a.md", "../escape") is not None
        assert _validate_workspace_target("a.md", "/abs") is not None


# ============================================================
# 编排目录可见性：系统 active 子 Agent 对所有用户可派发
# ============================================================

class _FakeAgent:
    def __init__(self, aid, name, desc=""):
        self.id = aid
        self.name = name
        self.description = desc


class _FakeScalars:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _FakeScalars(self._items)


class _FakeDB:
    def __init__(self, system_agents):
        self.system_agents = system_agents

    async def execute(self, query):
        return _FakeResult(self.system_agents)


class TestListSubAgentsCatalog:
    @pytest.mark.asyncio
    async def test_merge_system_and_own_active(self):
        from unittest.mock import patch
        from packages.agent.orchestrator.agent_loader import AgentLoader
        from packages.agent.services.agent_config_service import AgentConfigService

        async def fake_list(self, **kwargs):
            return [user_agent], 1

        user_agent = _FakeAgent("own-1", "我的助手")

        system = _FakeAgent("sys-file-1", "系统技能助手", "生成文件")
        # 与系统 agent 同 id，验证去重
        dup_of_system = _FakeAgent("sys-file-1", "系统技能助手(重复)", "")

        db = _FakeDB([system, dup_of_system])
        loader = AgentLoader(db)

        with patch.object(AgentConfigService, "list", new=fake_list):
            catalog = await loader.list_sub_agents(user_id=2)

        ids = [e["agent_id"] for e in catalog]
        assert "sys-file-1" in ids
        assert "own-1" in ids
        assert len(ids) == len(set(ids))  # 去重


# ============================================================
# #2 WRITE 沙箱化：写原语落沙箱 workdir + 受控提交工作区
# ============================================================

class _FakeAsyncDB:
    """最小 AsyncSession mock：get 返用户、execute 无已存在文件、记录提交。"""
    def __init__(self):
        self.rollbacked = 0

    async def get(self, model, pk):
        from types import SimpleNamespace
        return SimpleNamespace(id=1)

    async def execute(self, *a, **k):
        class _Result:
            def scalar_one_or_none(self):
                return None
        return _Result()

    async def rollback(self):
        self.rollbacked += 1

    async def commit(self):
        pass


class _FakeWorkspaceService:
    """替换 WorkspaceService：get_or_create 返回临时工作区，登记/审计可断言。"""
    def __init__(self, db, ws_root):
        from types import SimpleNamespace
        self.ws = SimpleNamespace(id="ws1", root_path=str(ws_root))
        self.registered = None
        self.logged = None

    async def get_or_create_workspace(self, user):
        return self.ws

    async def register_file(self, workspace=None, **kw):
        from types import SimpleNamespace
        self.registered = dict(kw)
        return SimpleNamespace(id="f1")

    async def log_action(self, **kw):
        self.logged = dict(kw)


class TestSandboxSaveWorkspaceFile:

    @pytest.fixture(autouse=True)
    def _clear(self):
        from packages.agent.core.harness.tools import ToolExecutionManager
        ToolExecutionManager._sandbox_executors.clear()
        yield
        ToolExecutionManager._sandbox_executors.clear()

    @pytest.mark.asyncio
    async def test_write_lands_in_sandbox_then_workspace(self, tmp_path, monkeypatch):
        import os
        from types import SimpleNamespace

        from packages.agent.core.harness.tools import ToolExecutionManager
        from packages.agent.orchestrator.business_tools import ensure_business_tools

        sandbox_dir = tmp_path / "sandbox"
        ws_root = tmp_path / "ws"

        fake_db = _FakeAsyncDB()
        ws_svc = _FakeWorkspaceService(fake_db, ws_root)

        monkeypatch.setattr(
            "packages.agent.services.workspace_service.WorkspaceService",
            lambda db: ws_svc,
        )

        # ensure_business_tools 注册沙箱执行器（save_workspace_file）
        await ensure_business_tools(fake_db, user_id=1)

        sandbox = SimpleNamespace(workdir=str(sandbox_dir), db=fake_db, user_id=1)
        executor = ToolExecutionManager._sandbox_executors["save_workspace_file"]

        res = await executor(
            sandbox,
            {"filename": "report.md", "content": "hello world", "folder": "docs",
             "session_id": "s1"},
        )

        assert "文件已保存" in res
        # 1) 写原语真落在沙箱隔离 workdir
        sandbox_file = sandbox_dir / "generated" / "docs" / "report.md"
        assert sandbox_file.read_text(encoding="utf-8") == "hello world"
        # 2) 受控提交到用户工作区
        ws_file = ws_root / "generated" / "docs" / "report.md"
        assert ws_file.read_text(encoding="utf-8") == "hello world"
        # 3) 登记 + 审计
        assert ws_svc.registered["relative_path"].endswith("generated/docs/report.md")
        assert ws_svc.logged["action"] == "generate_file"
