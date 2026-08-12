"""人工审批（HITL）确定性集成测试

用 mock 驱动，不依赖模型/真实 DB，验证审批核心链路：
1. require_approval 工具 → PermissionEngine 产生审批请求（(False, request)）
2. tao 图 __interrupt__ → _extract_approvals 提取 pending 事件数据
3. ASK_FIRST 持久化批准 → 放行（has_approval）
"""
import pytest


class _FakeDB:
    """最小 AsyncSession mock：记录 add，其余安全返回"""
    def __init__(self):
        self.added = []

    async def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def execute(self, *a, **k):
        class _Rows:
            def all(self):
                return []
            def fetchall(self):
                return []
        class _Result:
            def scalar_one_or_none(self):
                return None
            def scalar(self):
                return None
            def scalars(self):
                return _Rows()
            def fetchall(self):
                return []
            def all(self):
                return []
        return _Result()

    async def get(self, *a, **k):
        return None


@pytest.mark.asyncio
async def test_require_approval_creates_request():
    from packages.agent.runtime_engine.permission import PermissionEngine

    db = _FakeDB()
    eng = PermissionEngine(
        db, user_id=1,
        policy={"require_approval_tools": ["list_knowledge_bases"]},
    )

    ok, request = await eng.check_permission("list_knowledge_bases", "execute", {"kb": 1})
    # require_approval → 不允许直接执行，返回审批请求
    assert ok is False
    assert request is not None
    assert request.status.value == "pending"
    assert request.risk_level in ("low", "medium", "high", "critical")


@pytest.mark.asyncio
async def test_interrupt_extraction():
    from packages.agent.orchestrator.graph import OrchestratorRuntime

    # tao_graph permission_check 节点在 require_approval 时产出的 __interrupt__ 结构
    state = {
        "__interrupt__": {
            "type": "approval_required",
            "pending": [
                {"tool": "list_knowledge_bases", "args": {}, "risk_level": "high", "request_id": "abc123"},
            ],
        }
    }
    approvals = OrchestratorRuntime._extract_approvals(state)
    assert len(approvals) == 1
    assert approvals[0]["tool"] == "list_knowledge_bases"
    assert approvals[0]["request_id"] == "abc123"


@pytest.mark.asyncio
async def test_ask_first_fallback_and_has_approval():
    from packages.agent.runtime_engine.permission import PermissionEngine

    db = _FakeDB()  # execute 返回空 → 无持久化批准记录
    eng = PermissionEngine(db, user_id=1, policy={})

    # ASK_FIRST 工具（无缓存、无 DB 批准）→ 需审批
    ok, request = await eng.check_permission("file_write", "execute", {})
    assert ok is False
    assert request is not None

    # has_approval（无 DB 记录）→ False
    assert await eng.has_approval(1, "file_write") is False
