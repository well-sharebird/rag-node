"""加载 agent_prompt.md 约束文件

类似 CLAUDE.md / AGENTS.md 的机制:
- 每个 Agent 可配置一个 agent_prompt.md 文件
- 文件分为三个章节：Identity & Red Lines / Tools & Workflow / Domain Knowledge
- 静态部分会话期间不变，可利用 prefix caching
"""
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# agent_prompt.md 文件搜索路径
SEARCH_PATHS = [
    Path("configs/agents/{agent_id}/agent_prompt.md"),  # 项目级配置
    Path("~/.knowrag/agents/{agent_id}/agent_prompt.md"),  # 用户级配置
]

_SECTION_MAP = {
    "identity": "## Identity & Red Lines",
    "capabilities": "## Tools & Workflow",
    "domain": "## Domain Knowledge",
}


def load_agent_prompt_section(agent_id: str, section: str) -> str:
    """加载 agent_prompt.md 的指定章节

    Args:
        agent_id: Agent ID
        section: 章节名 (identity / capabilities / domain)

    Returns:
        章节内容，找不到返回空字符串
    """
    section_header = _SECTION_MAP.get(section)
    if not section_header:
        logger.warning(f"Unknown section: {section}")
        return ""

    # 搜索 agent_prompt.md 文件
    for path_template in SEARCH_PATHS:
        path = Path(str(path_template).format(agent_id=agent_id))
        path = path.expanduser()

        if path.exists():
            content = path.read_text(encoding="utf-8")
            return _extract_section(content, section_header)

    return ""


def _extract_section(content: str, header: str) -> str:
    """从 Markdown 中提取指定章节内容"""
    lines = content.split("\n")
    in_section = False
    section_lines = []

    for line in lines:
        if line.startswith("## "):
            if in_section:
                break  # 遇到下一个 ## 章节，结束
            if line.strip() == header:
                in_section = True
                continue
        elif in_section:
            section_lines.append(line)

    return "\n".join(section_lines).strip()
