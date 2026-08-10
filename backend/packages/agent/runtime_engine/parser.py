"""
Output Parser - 输出结构化解析器

从 LLM 的文本输出中结构化地提取：
- 工具调用 (tool calls)
- 参数 (arguments)
- 推理步骤 (reasoning steps)
- 最终答案 (final answer)

核心职责：
- 解析 LLM 输出的工具调用格式
- 验证输出格式是否符合预期
- 提取结构化数据供引擎执行
"""
import json
import logging
import re
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel, Field, ValidationError
from enum import Enum

logger = logging.getLogger(__name__)


class ToolCall(BaseModel):
    """工具调用"""
    id: str
    name: str
    arguments: Dict[str, Any]
    reasoning: Optional[str] = None  # 调用原因/推理


class ParsedOutput(BaseModel):
    """解析后的输出"""
    tool_calls: List[ToolCall] = Field(default_factory=list)
    final_answer: Optional[str] = None
    reasoning_steps: List[str] = Field(default_factory=list)
    has_error: bool = False
    error_message: Optional[str] = None


class OutputFormat(str, Enum):
    """输出格式类型"""
    JSON = "json"
    MARKDOWN = "markdown"
    NATURAL_LANGUAGE = "natural_language"
    STRUCTURED = "structured"  # 自定义结构


class OutputParser:
    """
    输出解析器

    从 LLM 输出中提取结构化信息
    """

    def __init__(self):
        # 工具调用的标记模式
        self.tool_call_patterns = [
            # JSON 格式：{"tool": "name", "arguments": {...}}
            r'\{["\']tool["\']:\s*["\']([^"\']+)["\'],\s*["\']arguments["\']:\s*(\{[^}]+\})\}',
            # 函数格式：tool_name(arg1=val1, arg2=val2)
            r'(\w+)\s*\(([^)]*)\)',
            # XML 格式：<tool name="xxx"><arg>val</arg></tool>
            r'<tool\s+name=["\']([^"\']+)["\']>(.*?)</tool>',
        ]

        # 推理步骤的标记
        self.reasoning_markers = [
            r'思考：(.+?)(?:\n|$)',
            r'分析：(.+?)(?:\n|$)',
            r'Reasoning:\s*(.+?)(?:\n|$)',
            r'Thinking:\s*(.+?)(?:\n|$)',
        ]

        # 最终答案的标记
        self.answer_markers = [
            r'答案：(.+?)(?:\n\n|$)',
            r'结论：(.+?)(?:\n\n|$)',
            r'Final Answer:\s*(.+?)(?:\n\n|$)',
            r'输出：(.+?)(?:\n\n|$)',
        ]

    def parse(self, output: str, expected_format: OutputFormat = OutputFormat.NATURAL_LANGUAGE) -> ParsedOutput:
        """
        解析 LLM 输出

        Args:
            output: LLM 的原始输出文本
            expected_format: 期望的输出格式

        Returns:
            ParsedOutput: 解析后的结构化输出
        """
        try:
            # 1. 尝试解析 JSON 格式
            if expected_format == OutputFormat.JSON:
                return self._parse_json(output)

            # 2. 尝试提取工具调用
            tool_calls = self._extract_tool_calls(output)

            # 3. 提取推理步骤
            reasoning_steps = self._extract_reasoning(output)

            # 4. 提取最终答案
            final_answer = self._extract_final_answer(output)

            # 5. 如果没有工具调用也没有答案，可能是错误
            if not tool_calls and not final_answer:
                # 检查是否是错误信息
                if self._looks_like_error(output):
                    return ParsedOutput(
                        has_error=True,
                        error_message=output.strip(),
                    )

            return ParsedOutput(
                tool_calls=tool_calls,
                final_answer=final_answer,
                reasoning_steps=reasoning_steps,
            )

        except Exception as e:
            logger.error(f"Failed to parse output: {e}")
            return ParsedOutput(
                has_error=True,
                error_message=f"解析失败：{str(e)}",
            )

    def _parse_json(self, output: str) -> ParsedOutput:
        """解析 JSON 格式输出"""
        try:
            # 尝试直接解析
            data = json.loads(output.strip())
            return self._convert_json_to_parsed(data)
        except json.JSONDecodeError:
            # 尝试从文本中提取 JSON
            json_match = re.search(r'\{[^}]*\}', output, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                    return self._convert_json_to_parsed(data)
                except json.JSONDecodeError:
                    pass

            raise ValueError("无法解析 JSON 格式")

    def _convert_json_to_parsed(self, data: Dict[str, Any]) -> ParsedOutput:
        """将 JSON 数据转换为 ParsedOutput"""
        tool_calls = []

        # 处理工具调用
        if "tool_calls" in data:
            for i, tc in enumerate(data["tool_calls"]):
                tool_calls.append(ToolCall(
                    id=tc.get("id", f"call_{i}"),
                    name=tc.get("name", tc.get("tool", "")),
                    arguments=tc.get("arguments", tc.get("parameters", {})),
                    reasoning=tc.get("reasoning"),
                ))
        elif "tool" in data:
            # 单个工具调用
            tool_calls.append(ToolCall(
                id="call_0",
                name=data["tool"],
                arguments=data.get("arguments", {}),
                reasoning=data.get("reasoning"),
            ))

        return ParsedOutput(
            tool_calls=tool_calls,
            final_answer=data.get("answer", data.get("final_answer")),
            reasoning_steps=data.get("reasoning_steps", data.get("steps", [])),
        )

    def _extract_tool_calls(self, output: str) -> List[ToolCall]:
        """从输出中提取工具调用"""
        tool_calls = []

        # 尝试 JSON 格式
        json_calls = self._extract_json_tool_calls(output)
        tool_calls.extend(json_calls)

        # 尝试函数格式
        if not tool_calls:
            func_calls = self._extract_function_tool_calls(output)
            tool_calls.extend(func_calls)

        # 尝试 XML 格式
        if not tool_calls:
            xml_calls = self._extract_xml_tool_calls(output)
            tool_calls.extend(xml_calls)

        return tool_calls

    def _extract_json_tool_calls(self, output: str) -> List[ToolCall]:
        """提取 JSON 格式的工具调用"""
        tool_calls = []

        # 查找所有 JSON 对象
        json_pattern = r'\{[^{}]*"tool"[^{}]*\}'
        matches = re.finditer(json_pattern, output, re.DOTALL)

        for match in matches:
            try:
                data = json.loads(match.group())
                tool_calls.append(ToolCall(
                    id=data.get("id", f"call_{len(tool_calls)}"),
                    name=data.get("tool", data.get("name", "")),
                    arguments=data.get("arguments", data.get("parameters", {})),
                    reasoning=data.get("reasoning"),
                ))
            except json.JSONDecodeError:
                continue

        return tool_calls

    def _extract_function_tool_calls(self, output: str) -> List[ToolCall]:
        """提取函数格式的工具调用"""
        tool_calls = []

        # 模式：tool_name(arg1=val1, arg2="val2")
        pattern = r'(\w+)\s*\(([^)]*)\)'
        matches = re.finditer(pattern, output)

        for match in matches:
            name = match.group(1)
            args_str = match.group(2)

            # 解析参数
            arguments = {}
            if args_str.strip():
                # 简单参数解析
                arg_pairs = re.findall(r'(\w+)=(?:"([^"]*)"|(\d+)|(\w+))', args_str)
                for arg_name, str_val, num_val, word_val in arg_pairs:
                    value = str_val or num_val or word_val
                    if value:
                        arguments[arg_name] = value

            if arguments or name.lower() not in ['think', 'reasoning', 'analysis']:
                tool_calls.append(ToolCall(
                    id=f"call_{len(tool_calls)}",
                    name=name,
                    arguments=arguments,
                ))

        return tool_calls

    def _extract_xml_tool_calls(self, output: str) -> List[ToolCall]:
        """提取 XML 格式的工具调用"""
        tool_calls = []

        pattern = r'<tool\s+name=["\']([^"\']+)["\']>(.*?)</tool>'
        matches = re.finditer(pattern, output, re.DOTALL)

        for match in matches:
            name = match.group(1)
            content = match.group(2)

            # 从内容中提取参数
            arguments = {}
            arg_matches = re.finditer(r'<(\w+)>([^<]+)</\1>', content)
            for arg_match in arg_matches:
                arguments[arg_match.group(1)] = arg_match.group(2).strip()

            tool_calls.append(ToolCall(
                id=f"call_{len(tool_calls)}",
                name=name,
                arguments=arguments,
            ))

        return tool_calls

    def _extract_reasoning(self, output: str) -> List[str]:
        """提取推理步骤"""
        reasoning = []

        for pattern in self.reasoning_markers:
            matches = re.finditer(pattern, output, re.IGNORECASE | re.DOTALL)
            for match in matches:
                step = match.group(1).strip()
                if step and step not in reasoning:
                    reasoning.append(step)

        return reasoning

    def _extract_final_answer(self, output: str) -> Optional[str]:
        """提取最终答案"""
        # 尝试答案标记
        for pattern in self.answer_markers:
            match = re.search(pattern, output, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()

        # 如果没有标记，返回最后一段非空文本
        paragraphs = output.split('\n\n')
        for para in reversed(paragraphs):
            para = para.strip()
            if para and not any(marker in para.lower() for marker in ['tool', 'function', 'thinking', 'reasoning']):
                return para

        return None

    def _looks_like_error(self, text: str) -> bool:
        """检查文本是否像错误信息"""
        error_indicators = [
            'error', 'exception', 'failed', 'failure',
            '错误', '失败', '异常',
            '无法', '不能', '不支持',
        ]
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in error_indicators)

    def validate_tool_call(self, tool_call: ToolCall, tool_schema: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        验证工具调用是否符合 Schema

        Args:
            tool_call: 工具调用
            tool_schema: 工具的 JSON Schema 定义

        Returns:
            (is_valid, error_message)
        """
        # 检查工具名称
        if tool_call.name not in tool_schema.get('allowed_tools', []):
            return False, f"工具 '{tool_call.name}' 不在允许列表中"

        # 检查必需参数
        required = tool_schema.get('required', [])
        for param in required:
            if param not in tool_call.arguments:
                return False, f"缺少必需参数：{param}"

        # 检查参数类型
        properties = tool_schema.get('properties', {})
        for param_name, param_value in tool_call.arguments.items():
            if param_name in properties:
                expected_type = properties[param_name].get('type')
                if expected_type == 'integer' and not isinstance(param_value, int):
                    try:
                        int(param_value)
                    except (ValueError, TypeError):
                        return False, f"参数 '{param_name}' 应该是整数类型"
                elif expected_type == 'boolean' and not isinstance(param_value, bool):
                    return False, f"参数 '{param_name}' 应该是布尔类型"

        return True, None
