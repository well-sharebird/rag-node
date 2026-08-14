"""沙箱依赖解析纯逻辑测试（deps.py）。

覆盖 resolve_imports / STDLIB 过滤 / plan_dependencies 合并声明与 import→发行名映射 /
sanitize_pkg 注入净化。不依赖 DB / 网络。
"""
from packages.agent.core.harness.sandbox.deps import (
    STDLIB,
    plan_dependencies,
    resolve_imports,
    sanitize_pkg,
)


# ---------------- resolve_imports ----------------
def test_import_simple_and_dotted():
    assert resolve_imports("import os") == ["os"]
    assert resolve_imports("import numpy as np") == ["numpy"]
    assert resolve_imports("import a.b.c") == ["a"]
    # 去重、保序
    assert resolve_imports("import os\nimport os") == ["os"]


def test_from_import():
    assert resolve_imports("from pandas import DataFrame") == ["pandas"]
    assert resolve_imports("from sklearn.linear_model import LinearRegression") == ["sklearn"]


def test_relative_imports_skipped():
    assert resolve_imports("from . import helper\nfrom ..pkg import x") == []


def test_strings_and_comments_not_misdetected():
    code = 's = "import fake_mod"\n# import os\nimport json'
    assert "fake_mod" not in resolve_imports(code)
    assert "os" not in resolve_imports(code)
    assert resolve_imports(code) == ["json"]


def test_invalid_syntax_returns_empty():
    assert resolve_imports("def broken(:" ) == []


# ---------------- STDLIB 过滤 ----------------
def test_stdlib_contains_common():
    for m in ("os", "sys", "json", "re", "ast", "pathlib", "dataclasses", "typing", "__future__"):
        assert m in STDLIB


def test_stdlib_not_contain_common_thirdparty():
    assert "pandas" not in STDLIB
    assert "numpy" not in STDLIB
    assert "requests" not in STDLIB


# ---------------- plan_dependencies ----------------
def test_plan_merges_import_and_declared():
    code = "import pandas\nimport os"
    # declared 也合并 / 去重
    assert plan_dependencies(code, ["os", "numpy"]) == ["pandas", "numpy"]


def test_plan_filters_stdlib():
    assert plan_dependencies("import os\nimport json") == []


def test_plan_maps_import_name_to_distribution():
    # PIL→pillow；sklearn→scikit-learn（发行名）
    assert plan_dependencies("from PIL import Image") == ["pillow"]
    assert plan_dependencies("from sklearn.linear_model import Ridge") == ["scikit-learn"]


def test_plan_drops_invalid_declared():
    # 非法声明被净化丢弃，不阻断
    assert plan_dependencies("import os", ["pandas", "requests; rm -rf /"]) == ["pandas"]


# ---------------- sanitize_pkg ----------------
def test_sanitize_allows_valid_specs():
    assert sanitize_pkg("pandas") == "pandas"
    assert sanitize_pkg("python-pptx") == "python-pptx"
    assert sanitize_pkg("numpy==1.26.0") == "numpy==1.26.0"
    # 比较约束单独出现是合法的 pip 需求串（a>1 与 a>=1 均允许）
    assert sanitize_pkg("pandas>1.0") == "pandas>1.0"
    assert sanitize_pkg("numpy>=1.21") == "numpy>=1.21"


def test_sanitize_rejects_injection():
    for bad in ("requests;rm -rf /", "a && b", "..", "/etc/passwd", "x|cat", "a b", "$(cmd)", "-rf"):
        assert sanitize_pkg(bad) is None, bad


def test_sanitize_empty():
    assert sanitize_pkg("") is None
    assert sanitize_pkg("   ") is None
