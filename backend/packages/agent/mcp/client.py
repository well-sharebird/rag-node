"""MCP Client - 用于在应用内部调用 MCP Server 的工具。

这个 Client 不是通过网络调用，而是直接调用本地 MCP Server 的 handler 函数，
这样可以在同一个进程中集成 MCP 工具到 LangChain Agent 中。
"""
import logging
import json
from typing import Any, Dict, List, Optional
from langchain_core.tools import tool as langchain_tool

logger = logging.getLogger("app.mcp.client")


class MCPClient:
    """MCP Client - 用于在应用内部调用 MCP Server 的工具。

    使用方式：
    ```python
    async with MCPClient(db) as client:
        tools = await client.list_tools()
        result = await client.call_tool("kb_list", {})
    ```
    """

    def __init__(self, db: Any):
        self.db = db
        self._tools: List[Dict] = []
        self._initialized = False

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def initialize(self):
        """初始化 - 加载所有 MCP 工具定义"""
        if self._initialized:
            return

        # 从 MCP Server 的工具定义中加载
        from packages.agent.mcp.tools.kb_tools import KB_TOOLS
        from packages.agent.mcp.tools.model_tools import MODEL_TOOLS
        from packages.agent.mcp.tools.prompt_tools import PROMPT_TOOLS
        from packages.agent.mcp.tools.agent_tools import AGENT_TOOLS

        self._tools = KB_TOOLS + MODEL_TOOLS + PROMPT_TOOLS + AGENT_TOOLS
        self._initialized = True

        logger.info("MCP Client initialized with %d tools", len(self._tools))

    async def list_tools(self) -> List[Dict]:
        """获取所有可用工具的定义"""
        await self.initialize()
        return self._tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """调用指定的 MCP 工具"""
        await self.initialize()

        # 导入所有 handler
        from packages.agent.mcp.tools.kb_tools import handle_kb_tool
        from packages.agent.mcp.tools.model_tools import handle_model_tool
        from packages.agent.mcp.tools.prompt_tools import handle_prompt_tool
        from packages.agent.mcp.tools.agent_tools import handle_agent_tool

        # 路由到对应的 handler（根据工具名判断）
        kb_prefixes = ["list_", "get_", "create_", "update_", "delete_"]
        kb_keywords = ["knowledge_base", "kb"]
        model_keywords = ["model", "models"]
        prompt_keywords = ["prompt", "prompts"]
        agent_keywords = ["agent", "agents"]

        tool_name_lower = name.lower()

        # 判断工具类型
        is_kb = any(kw in tool_name_lower for kw in kb_keywords)
        is_model = any(kw in tool_name_lower for kw in model_keywords)
        is_prompt = any(kw in tool_name_lower for kw in prompt_keywords)
        is_agent = any(kw in tool_name_lower for kw in agent_keywords)

        if is_kb:
            result = await handle_kb_tool(name, arguments, self.db)
        elif is_model:
            result = await handle_model_tool(name, arguments, self.db)
        elif is_prompt:
            result = await handle_prompt_tool(name, arguments, self.db)
        elif is_agent:
            result = await handle_agent_tool(name, arguments, self.db)
        else:
            raise ValueError(f"Unknown tool: {name}")

        return result

    async def create_langchain_tool(self, tool_def: Dict) -> Any:
        """将 MCP 工具定义转换为 LangChain 工具"""
        from mcp.types import TextContent
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, create_model

        name = tool_def.get("name")
        description = tool_def.get("description", "")

        if not name:
            return None

        # Get input schema to build Pydantic model
        input_schema = tool_def.get("inputSchema", {})
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        # Build Pydantic model for tool arguments
        field_definitions = {}
        for param_name, param_schema in properties.items():
            param_type = param_schema.get("type", "string")
            param_desc = param_schema.get("description", "")
            default_value = param_schema.get("default", ...)

            # Map JSON Schema types to Python types
            type_map = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
                "array": list,
                "object": dict,
            }
            python_type = type_map.get(param_type, str)

            # Handle optional fields - use default from schema if available
            if param_name not in required:
                from typing import Optional
                python_type = Optional[python_type]
                if default_value is ... or default_value is None:
                    default_value = None

            field_definitions[param_name] = (python_type, default_value)

        ArgsModel = create_model(f"{name.title()}Args", **field_definitions)

        async def mcp_tool_handler(**kwargs) -> str:
            result = await self.call_tool(name, kwargs)
            # Handle TextContent return type
            if isinstance(result, list) and len(result) > 0:
                if isinstance(result[0], TextContent):
                    return result[0].text
            return json.dumps(result, ensure_ascii=False)

        return StructuredTool(
            name=name,
            description=description,
            args_schema=ArgsModel,
            coroutine=mcp_tool_handler,
        )

    async def get_all_langchain_tools(self) -> List[Any]:
        """获取所有 LangChain 格式的工具"""
        await self.initialize()
        tools = []
        for tool_def in self._tools:
            langchain_tool_obj = await self.create_langchain_tool(tool_def)
            if langchain_tool_obj:
                tools.append(langchain_tool_obj)
        return tools
