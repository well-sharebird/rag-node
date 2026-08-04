"""提示词渲染引擎 - 带沙箱防护的模板渲染"""

import re
from typing import Dict, Any, List, Tuple
from jinja2.sandbox import SandboxedEnvironment, SecurityError
from jinja2 import UndefinedError, TemplateError, DebugUndefined


class PromptRenderer:
    """提示词渲染引擎

    使用 Jinja2 沙箱环境，防止模板注入攻击
    支持 {{variable}} 语法进行变量填充
    """

    # 沙箱环境配置
    _env: SandboxedEnvironment = None  # lazy init

    @classmethod
    def _get_env(cls) -> SandboxedEnvironment:
        if cls._env is None:
            cls._env = SandboxedEnvironment(
                autoescape=False,  # 输出为纯文本，非 HTML
                undefined=DebugUndefined,  # 缺失变量返回空串
            )
        return cls._env

    @staticmethod
    def render(
        content: str, variables: Dict[str, Any], schema: List[Dict[str, Any]] = None
    ) -> Tuple[str, List[str]]:
        """渲染提示词模板

        Args:
            content: 原始模板内容（含 {{var}}）
            variables: 变量字典
            schema: 变量 schema 定义 [{name, type, required, default}]

        Returns:
            (rendered_text, warnings)

        Raises:
            SecurityError: 检测到模板注入尝试
        """
        warnings = []

        # 1. 变量校验与默认值填充
        validated_vars = PromptRenderer._validate_variables(
            variables, schema or [], warnings
        )

        # 2. 沙箱渲染
        try:
            template = PromptRenderer._get_env().from_string(content)
            rendered = template.render(**validated_vars)
        except SecurityError as e:
            raise SecurityError(f"模板注入检测：{str(e)}")
        except (UndefinedError, TemplateError) as e:
            warnings.append(f"模板渲染警告：{str(e)}")
            rendered = content  # 返回原始内容

        return rendered, warnings

    @staticmethod
    def _validate_variables(
        variables: Dict[str, Any], schema: List[Dict[str, Any]], warnings: List[str]
    ) -> Dict[str, Any]:
        """校验变量并填充默认值

        Args:
            variables: 用户传入的变量
            schema: 变量定义 schema
            warnings: 警告信息列表

        Returns:
            校验后的变量字典
        """
        result = {}
        schema_map = {s["name"]: s for s in schema}

        for var_def in schema:
            name = var_def["name"]
            required = var_def.get("required", False)
            default = var_def.get("default")
            expected_type = var_def.get("type", "string")

            if name in variables:
                value = variables[name]
                # 类型校验
                if not PromptRenderer._check_type(value, expected_type):
                    warnings.append(
                        f"变量 '{name}' 类型不符，期望 {expected_type}，实际 {type(value).__name__}"
                    )
                result[name] = value
            elif required:
                warnings.append(f"必需变量缺失：{name}")
                result[name] = f"__MISSING:{name}__"
            else:
                result[name] = default if default is not None else ""

        # 添加额外的用户变量（不在 schema 中）
        for key, value in variables.items():
            if key not in result:
                result[key] = value

        return result

    @staticmethod
    def _check_type(value: Any, expected_type: str) -> bool:
        """简单的类型检查

        Args:
            value: 变量值
            expected_type: 期望类型

        Returns:
            是否匹配
        """
        type_map = {
            "string": str,
            "str": str,
            "number": (int, float),
            "int": int,
            "float": float,
            "boolean": bool,
            "bool": bool,
            "array": (list, tuple),
            "list": list,
            "object": dict,
            "dict": dict,
        }
        expected = type_map.get(expected_type.lower())
        if expected is None:
            return True  # 未知类型，跳过检查
        return isinstance(value, expected)

    @staticmethod
    def extract_variables(content: str) -> List[str]:
        """从模板内容中提取变量名

        Args:
            content: 模板内容

        Returns:
            变量名列表
        """
        pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\|[^}]*)?\}\}"
        matches = re.findall(pattern, content)
        return list(set(matches))

    @staticmethod
    def validate_template(content: str) -> Tuple[bool, List[str]]:
        """验证模板语法

        Args:
            content: 模板内容

        Returns:
            (is_valid, errors)
        """
        errors = []

        # 检查未闭合的 {{
        open_count = content.count("{{")
        close_count = content.count("}}")
        if open_count != close_count:
            errors.append(f"模板语法错误：{{{{ 和 }}}} 数量不匹配")

        # 检查危险语法（在沙箱中也会被拦截，但提前检查更好）
        dangerous_patterns = [
            r"\{%\s*import\s+",
            r"\{%\s*from\s+",
            r"\{%\s*include\s+",
            r"\{\{.*__.*\}\}",  # 双下划线属性访问
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                errors.append(f"检测到危险语法：{pattern}")

        return len(errors) == 0, errors
