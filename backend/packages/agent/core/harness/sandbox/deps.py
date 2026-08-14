"""沙箱自动安装依赖的解析逻辑（纯函数，可单测）。

给定一段待执行的 Python 代码，解析其 import 需求并转成待安装的发行包名列表，
供 SandboxRuntime 在运行前用隔离 venv + pip 安装缺失环境。
"""
import ast
import re
import sys
from typing import FrozenSet, List, Optional

# 顶层"import 名 → 发行包名"映射。仅覆盖无法从 import 名直推发行名的常见情况；
# 多数包名与 import 名一致（requests→requests），无需映射。
IMPORT_TO_PACKAGE = {
    "pil": "pillow",
    "yaml": "PyYAML",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "dateutil": "python-dateutil",
    "cryptography": "cryptography",  # import 名即发行名，保留作说明
    "PIL": "pillow",
}

# 标准库模块名（py3.10+）。__future__/future 走不了 pip，纳入排除集。
_STDLIB_NAMES: FrozenSet[str] = frozenset(getattr(sys, "stdlib_module_names", ()))
STDLIB: FrozenSet[str] = _STDLIB_NAMES | frozenset(
    {"__future__", "typing_extensions", "zoneinfo"}
)

# 包名/版本约束仅允许字母数字 `.` `_` `-`（如 pandas、numpy==1.26、scipy>=1.0）；
# 拒绝一切可能被 shell/pip 当参数或子命令解析的元字符。
_PKG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(==|>=|<=|>|<|~=|!=)?[A-Za-z0-9._-]*$")


def resolve_imports(code: str) -> List[str]:
    """解析 Python 代码中的顶层 import 依赖（小写、去重、保序）。

    仅收集绝对导入（相对导入 level>0 跳过——它是同项目内模块，非第三方包）；
    import a.b 取顶层 a；from x import y 取 x。注释/字符串内文本不会命中。
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    found: List[str] = []
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                root = root.lower()
                if root not in seen:
                    seen.add(root)
                    found.append(root)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            if node.module:
                root = node.module.split(".")[0].lower()
                if root not in seen:
                    seen.add(root)
                    found.append(root)
    return found


def sanitize_pkg(spec: str) -> Optional[str]:
    """净化/校验一个 pip 安装需求串。合法返回原串；非法返回 None（拒绝安装）。"""
    spec = (spec or "").strip()
    if not spec:
        return None
    if not _PKG_RE.fullmatch(spec):
        return None
    if ".." in spec or "/" in spec or "\\" in spec:
        return None
    return spec


def _pkg_name(import_name: str) -> str:
    return IMPORT_TO_PACKAGE.get(import_name, import_name)


def plan_dependencies(code: str, declared: Optional[List[str]] = None) -> List[str]:
    """综合（代码解析 ∪ LLM 声明）→ 待安装发行包名列表（去重、保序、净化）。

    跳过标准库/内置；非法声明项被静默丢弃（不阻断执行）。不联网预检可达性——
    缺失与否由运行期 pip 判断（venv 为空集，第三方 import 即视为待装）。
    """
    deps: List[str] = []

    def _push(name: str) -> None:
        if name in STDLIB or name in ("builtins",) or not name:
            return
        clean = sanitize_pkg(_pkg_name(name))
        if clean and clean not in deps:
            deps.append(clean)

    for imp in resolve_imports(code):
        _push(imp)

    # 声明依赖：每个元素视为一个原子 spec，整体校验（含内部空白/元字符即拒绝），
    # 不做二次切分——避免注入片段（如 "requests; rm -rf /"）被拆散后残留合法包名。
    for d in (declared or []):
        name = str(d).strip().lower()
        if name in STDLIB or name in ("builtins",):
            continue
        clean = sanitize_pkg(_pkg_name(name))
        if clean and clean not in deps:
            deps.append(clean)

    return deps
