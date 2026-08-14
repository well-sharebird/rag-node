"""skill_registry 核心路径测试（重点 DependencyResolver 纯 semver 逻辑）。

- _satisfies：semver 约束匹配（^ / ~ / >= / 精确 / * / 非法约束）
- publish 非法版本：在触碰 DB 前即抛 ValueError
- resolve 无声明依赖：直接返回 {}
"""
import semver
import pytest

from packages.agent.services.skill_registry import DependencyResolver, RegistryService


def _satisfies(constraint: str, version: str) -> bool:
    return DependencyResolver._satisfies(None, semver.Version.parse(version), constraint)


# ---------------- 纯 semver 约束匹配 ----------------
# 注：环境使用 python-semver 3.0.4，其 match/Version.match 仅支持运算符形式
# （< > == <= >= != 与精确版本）。npm 风格 ^ / ~ / * 将抛 ValueError 被 _satisfies
# 吞成 False——即这些约束从未匹配成功（见 test_satisfies_npm_style_unsupported）。
def test_satisfies_comparators():
    assert _satisfies(">=1.2.0", "1.2.0") is True
    assert _satisfies(">=1.2.0", "1.1.0") is False
    assert _satisfies(">1.2.0", "1.2.1") is True
    assert _satisfies(">1.2.0", "1.2.0") is False
    assert _satisfies("<=1.2.3", "1.2.3") is True
    assert _satisfies("<=1.2.3", "1.2.4") is False
    assert _satisfies("<2.0.0", "1.9.9") is True
    assert _satisfies("<2.0.0", "2.0.0") is False
    assert _satisfies("!=9.9.9", "1.0.0") is True
    assert _satisfies("!=9.9.9", "9.9.9") is False


def test_satisfies_exact():
    assert _satisfies("1.2.3", "1.2.3") is True
    assert _satisfies("1.2.3", "1.2.4") is False
    assert _satisfies("==1.2.3", "1.2.3") is True


def test_satisfies_npm_style_unsupported():
    # 记录真实行为：^ / ~ / * 不被库支持 → ValueError → False（潜在 bug，见报告）
    assert _satisfies("^1.0.0", "1.2.3") is False
    assert _satisfies("~1.0.0", "1.0.5") is False
    assert _satisfies("*", "9.9.9") is False


def test_satisfies_invalid_constraint_returns_false():
    # 非法约束不应抛异常，而应判定不满足（加入候选失败时走 except 分支）
    assert _satisfies("not-a-constraint!!!", "1.0.0") is False


# ---------------- publish 非法版本（DB 前拦截） ----------------
def test_publish_rejects_invalid_semver_before_db():
    db = None  # 非法版本在 _get_or_create_skill 前就抛，绝不触达 DB
    svc = RegistryService(db)
    with pytest.raises(ValueError, match="Invalid semver"):
        # 不能直接 await——用 asyncio 包装
        import asyncio
        asyncio.run(svc.publish("demo", "not-a-version", {"name": "demo"}, "hash"))


# ---------------- resolve 空依赖 ----------------
@pytest.mark.asyncio
async def test_resolve_no_declared_deps_returns_empty():
    class _EmptyScalars:
        def all(self):
            return []

    class _Result:
        def scalars(self):
            return _EmptyScalars()

    class _DB:
        def __init__(self):
            self.flushed = False

        async def execute(self, stmt):
            return _Result()

        async def flush(self):
            self.flushed = True

    db = _DB()
    # 无声明依赖时不进入依赖图，也不会 flush
    result = await DependencyResolver(db).resolve(version_id=1)
    assert result == {}
