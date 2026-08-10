"""系统提示词模块化构建器

四模块架构:
  模块 1 Core Identity    (priority=100, 不可缓存) — Agent 身份 + 安全红线
  模块 2 Capabilities     (priority=50,  可缓存)   — 工具指南 + 思维框架
  模块 3 Domain Knowledge (priority=40,  可缓存)   — 领域知识 + 编码规范
  ---- prefix caching 边界 ----
  模块 4 Context-Specific (priority=30, 不可缓存)  — 当前任务 + 用户背景
"""
from typing import Optional
from dataclasses import dataclass, field
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class PromptModule:
    """提示词模块"""
    name: str
    content: str
    priority: int          # 数字越大越靠前
    cacheable: bool        # 是否可缓存（prefix caching）


@dataclass
class PromptBuildContext:
    """提示词构建上下文"""
    agent_id: str
    agent_type: str
    agent_name: str
    tools: list = field(default_factory=list)          # 工具列表
    security_policy: dict = field(default_factory=dict)  # 安全策略摘要
    user_input: str = ""                                 # 当前用户输入
    user_id: str = ""                                    # 用户 ID
    session_id: str = ""                                 # 会话 ID
    conversation_summary: str = ""                       # 对话摘要
    extra_context: dict = field(default_factory=dict)   # 额外上下文


class PromptBuilder:
    """模块化系统提示词构建器"""

    def __init__(self, templates_dir: Path = TEMPLATES_DIR):
        self.templates_dir = templates_dir
        self._template_cache: dict[str, str] = {}

    def build(self, ctx: PromptBuildContext) -> str:
        """构建完整的系统提示词"""
        modules = []

        # 模块 1: Core Identity (不可缓存)
        modules.append(self._build_core_identity(ctx))

        # 模块 2: Capabilities (可缓存)
        modules.append(self._build_capabilities(ctx))

        # 模块 3: Domain Knowledge (可缓存)
        modules.append(self._build_domain_knowledge(ctx))

        # ---- prefix caching 边界 ----
        # 模块 4: Context-Specific (不可缓存)
        modules.append(self._build_context_specific(ctx))

        # 按 priority 降序排列
        modules.sort(key=lambda m: m.priority, reverse=True)

        # 组装
        sections = []
        for mod in modules:
            if mod.content.strip():
                sections.append(mod.content.strip())

        return "\n\n---\n\n".join(sections)

    def _build_core_identity(self, ctx: PromptBuildContext) -> PromptModule:
        """模块 1: Core Identity — Agent 身份 + 安全红线"""
        # 1. 先尝试加载 agent_prompt.md
        content = self._load_agent_prompt(ctx.agent_id, "identity")

        if not content:
            # 2. 回退到模板
            template = self._load_template("core_identity.md")
            content = template.format(
                agent_name=ctx.agent_name,
                agent_type=ctx.agent_type,
            )

        # 3. 追加安全策略摘要
        if ctx.security_policy:
            content += "\n\n## 安全红线\n"
            content += self._format_security_policy(ctx.security_policy)

        return PromptModule(
            name="core_identity",
            content=content,
            priority=100,
            cacheable=False,
        )

    def _build_capabilities(self, ctx: PromptBuildContext) -> PromptModule:
        """模块 2: Capabilities — 工具指南 + 思维框架"""
        content = self._load_agent_prompt(ctx.agent_id, "capabilities")

        if not content:
            template = self._load_template("capabilities.md")
            content = template

        # 自动生成工具使用指南
        if ctx.tools:
            content += "\n\n## 可用工具\n"
            for tool in ctx.tools:
                name = getattr(tool, "name", str(tool))
                desc = getattr(tool, "description", "")
                content += f"- **{name}**: {desc}\n"

        # 思维框架：Think-Act-Observe
        content += "\n\n## 工作方式\n"
        content += ("遵循 Think → Act → Observe 循环:\n"
                    "1. **Think**: 分析用户需求，决定是否需要使用工具\n"
                    "2. **Act**: 调用工具执行操作\n"
                    "3. **Observe**: 观察工具返回结果，继续推理或给出最终回答\n")

        return PromptModule(
            name="capabilities",
            content=content,
            priority=50,
            cacheable=True,
        )

    def _build_domain_knowledge(self, ctx: PromptBuildContext) -> PromptModule:
        """模块 3: Domain Knowledge — 领域知识 + 编码规范"""
        content = self._load_agent_prompt(ctx.agent_id, "domain")

        if not content:
            template = self._load_template("domain_knowledge.md")
            content = template

        return PromptModule(
            name="domain_knowledge",
            content=content,
            priority=40,
            cacheable=True,
        )

    def _build_context_specific(self, ctx: PromptBuildContext) -> PromptModule:
        """模块 4: Context-Specific — 当前任务 + 用户背景（每次重新生成）"""
        sections = []

        sections.append(f"## 当前会话\n用户 ID: {ctx.user_id}\n会话 ID: {ctx.session_id}")

        if ctx.conversation_summary:
            sections.append(f"## 对话历史摘要\n{ctx.conversation_summary}")

        if ctx.extra_context:
            sections.append("## 额外上下文")
            for k, v in ctx.extra_context.items():
                sections.append(f"- {k}: {v}")

        return PromptModule(
            name="context_specific",
            content="\n\n".join(sections),
            priority=30,
            cacheable=False,
        )

    def _load_template(self, filename: str) -> str:
        """加载模板文件"""
        if filename in self._template_cache:
            return self._template_cache[filename]

        path = self.templates_dir / filename
        if path.exists():
            content = path.read_text(encoding="utf-8")
            self._template_cache[filename] = content
            return content

        logger.warning(f"Template not found: {path}")
        return ""

    def _load_agent_prompt(self, agent_id: str, section: str) -> str:
        """从 agent_prompt.md 加载指定章节"""
        from .agent_prompt_loader import load_agent_prompt_section
        return load_agent_prompt_section(agent_id, section)

    def _format_security_policy(self, policy: dict) -> str:
        """格式化安全策略摘要"""
        lines = []

        # 工具白名单
        allowed = policy.get("allowed_tools", [])
        if allowed:
            lines.append(f"- 允许使用的工具：{', '.join(allowed)}")

        # 工具黑名单
        blocked = policy.get("blocked_tools", [])
        if blocked:
            lines.append(f"- 禁止使用的工具：{', '.join(blocked)}")

        # 命令黑名单
        blocked_cmds = policy.get("blocked_commands", [])
        if blocked_cmds:
            lines.append(f"- 禁止执行的命令：{', '.join(blocked_cmds)}")

        # 速率限制
        rate_limit = policy.get("rate_limit")
        if rate_limit:
            lines.append(f"- 速率限制：{rate_limit} 次/分钟")

        return "\n".join(lines) if lines else "- 无特殊限制"
