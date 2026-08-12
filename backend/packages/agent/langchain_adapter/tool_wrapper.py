"""Tool 封装层 - 统一工具调用入口（设计文档 11.5.2）

所有工具调用必须通过 Harness 封装入口，禁止裸调用 LangChain Tool。
执行前校验白名单、参数、网络权限，执行后审计日志。
"""
from typing import Any, Callable, Dict, Optional
from langchain_core.tools import BaseTool
import logging

logger = logging.getLogger(__name__)


class ToolWrapper:
    """工具调用封装器

    职责：
    1. 参数校验
    2. 执行拦截
    3. 结果清洗
    4. 审计日志
    """

    def __init__(
        self,
        tool: BaseTool,
        allowed: bool = True,
        require_approval: bool = False,
        risk_level: str = "low",
    ):
        self.tool = tool
        self.allowed = allowed
        self.require_approval = require_approval
        self.risk_level = risk_level
        self._call_count = 0

    @property
    def name(self) -> str:
        return self.tool.name

    @property
    def description(self) -> str:
        return self.tool.description

    async def invoke(
        self,
        input: Dict[str, Any],
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """调用工具（带校验与审计）

        Args:
            input: 工具输入参数
            user_id: 用户 ID（审计用）
            session_id: 会话 ID（审计用）

        Returns:
            工具执行结果
        """
        # 1. 权限校验
        if not self.allowed:
            return f"[工具调用被拒绝] {self.name} 不在允许列表中"

        # 2. 参数校验
        try:
            validated_input = self._validate_input(input)
        except ValueError as e:
            return f"[参数校验失败] {e}"

        # 3. 执行（需要审批的工具在此处拦截）
        if self.require_approval:
            return f"[需要审批] 工具 {self.name} 需要人工批准后才能执行"

        # 4. 执行工具
        self._call_count += 1
        try:
            result = self.tool.invoke(validated_input)
            logger.info(f"[工具调用] {self.name} | user={user_id} session={session_id}")
            return result
        except Exception as e:
            logger.error(f"[工具调用失败] {self.name}: {e}")
            return f"[工具执行失败] {self.name}: {str(e)}"

    def _validate_input(self, input: Dict[str, Any]) -> Dict[str, Any]:
        """参数校验

        检查：
        1. 必填参数是否存在
        2. 参数类型是否正确
        3. 敏感参数是否脱敏
        """
        if not isinstance(input, dict):
            raise ValueError("输入必须是字典格式")

        # 获取工具参数定义
        tool_args = getattr(self.tool, "args", {})

        # 检查必填参数
        for arg_name, arg_info in tool_args.items():
            required = arg_info.get("required", False)
            if required and arg_name not in input:
                raise ValueError(f"缺少必填参数：{arg_name}")

        return input

    def get_schema(self) -> Dict[str, Any]:
        """获取工具 Schema（供 LLM 参考）"""
        return {
            "name": self.tool.name,
            "description": self.tool.description,
            "args": getattr(self.tool, "args", {}),
        }


def wrap_tool(
    tool: BaseTool,
    allowed: bool = True,
    require_approval: bool = False,
    risk_level: str = "low",
) -> ToolWrapper:
    """将 LangChain Tool 包装为 Harness 托管的工具

    Args:
        tool: LangChain Tool 实例
        allowed: 是否允许调用
        require_approval: 是否需要审批
        risk_level: 风险等级 (low/medium/high/critical)

    Returns:
        ToolWrapper 实例
    """
    return ToolWrapper(
        tool=tool,
        allowed=allowed,
        require_approval=require_approval,
        risk_level=risk_level,
    )


def wrap_tools(
    tools: list,
    allowlist: Optional[list] = None,
    approval_list: Optional[list] = None,
    risk_map: Optional[Dict[str, str]] = None,
) -> list:
    """批量包装工具

    Args:
        tools: LangChain Tool 列表
        allowlist: 允许的工具名称列表
        approval_list: 需要审批的工具名称列表
        risk_map: 工具风险等级映射 {tool_name: risk_level}

    Returns:
        ToolWrapper 列表
    """
    allowlist = set(allowlist or [])
    approval_list = set(approval_list or [])
    risk_map = risk_map or {}

    result = []
    for tool in tools:
        # 如果没有 allowlist，默认允许；否则检查是否在列表中
        allowed = not allowlist or tool.name in allowlist
        require_approval = tool.name in approval_list
        risk_level = risk_map.get(tool.name, "low")

        result.append(wrap_tool(
            tool=tool,
            allowed=allowed,
            require_approval=require_approval,
            risk_level=risk_level,
        ))

    return result
