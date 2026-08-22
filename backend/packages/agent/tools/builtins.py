"""
内置工具模块

提供 Agent 的基础工具：
- present_files: 展示输出文件
- ask_clarification: 请求澄清
- view_image: 查看图像
- subagent_spawn: 调用子 Agent（编排专用）
"""
import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def present_files(file_paths: list[str]) -> str:
    """
    Make output files visible to the user.

    Use this tool when:
    - You have created files in /mnt/user-data/outputs/
    - You want to show the user the final deliverables
    - You need to present file paths for user to download

    Args:
        file_paths: List of file paths to present (must be under /mnt/user-data/outputs/)

    Returns:
        Confirmation message with the presented file paths
    """
    # Validate paths - only allow outputs directory
    validated_paths = []
    for path in file_paths:
        if path.startswith("/mnt/user-data/outputs/"):
            validated_paths.append(path)
        else:
            logger.warning("Invalid file path: %s (must be under /mnt/user-data/outputs/)", path)

    if not validated_paths:
        return "No valid output files to present."

    return f"Output files ready: {', '.join(validated_paths)}"


@tool
def ask_clarification(
    question: str,
    options: list[str] | None = None,
) -> str:
    """
    Ask the user for clarification when the request is ambiguous.

    Use this tool when:
    - The user's request is unclear or ambiguous
    - You need more information to proceed
    - Multiple interpretations are possible
    - User preferences would affect the approach

    Args:
        question: The clarification question to ask the user
        options: Optional list of suggested options for the user to choose from

    Returns:
        A message indicating that clarification is awaited
    """
    if options:
        options_text = "\nOptions:\n" + "\n".join(f"  - {opt}" for opt in options)
        return f"Clarification requested: {question}{options_text}"

    return f"Clarification requested: {question}"


@tool
def view_image(image_path: str) -> str:
    """
    View an image and return its base64 encoded content.

    Use this tool when:
    - You need to analyze an image
    - You need to describe image content
    - User has uploaded an image for analysis

    Args:
        image_path: Path to the image file (must be under /mnt/user-data/)

    Returns:
        Base64 encoded image content with metadata
    """
    import base64
    from pathlib import Path

    # Validate path
    if not image_path.startswith("/mnt/user-data/"):
        return f"Error: Invalid image path. Must be under /mnt/user-data/"

    try:
        # Convert virtual path to physical path
        physical_path = image_path.replace("/mnt/user-data/", "/path/to/user-data/")
        path = Path(physical_path)

        if not path.exists():
            return f"Error: Image not found at {image_path}"

        # Read and encode
        with open(path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        # Determine MIME type
        mime_type = _get_mime_type(path.suffix)

        return f"data:{mime_type};base64,{image_data}"

    except Exception as e:
        logger.exception("Error reading image: %s", e)
        return f"Error reading image: {str(e)}"


@tool
async def subagent_spawn(agent_id: str, task_prompt: str) -> str:
    """
    调用子 Agent 执行特定任务（主编排器专用工具）。

    Use this tool when:
    - 需要将任务委派给专业子 Agent
    - 需要多 Agent 协作完成复杂任务
    - 需要并行/串行执行多个子任务

    Args:
        agent_id: 子 Agent 的唯一标识符（必须从可用子 Agent 列表中选择）
        task_prompt: 给子 Agent 的具体任务描述

    Returns:
        子 Agent 执行结果（由编排器拦截并实际执行）
    """
    # 这个工具实际由编排器拦截处理，不会真正执行
    # 返回占位符，实际结果由 orchestrator 执行子 Agent 后填充
    return f"[子 Agent {agent_id} 执行中...]"


def _get_mime_type(suffix: str) -> str:
    """Get MIME type for image file extension"""
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }
    return mime_types.get(suffix.lower(), "image/png")


async def get_basic_tools() -> list:
    """
    获取基础工具列表

    Returns:
        基础工具列表
    """
    return [
        present_files,
        ask_clarification,
        view_image,
        subagent_spawn,
    ]
