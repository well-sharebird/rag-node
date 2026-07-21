"""
Prompt Template 管理服务
支持版本管理、场景分类、变量替换
"""
from __future__ import annotations
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json

logger = logging.getLogger("app.services.prompt_template")


class PromptCategory(Enum):
    """Prompt 场景分类"""
    QA = "qa"                      # 问答
    RAG = "rag"                    # RAG 检索增强生成
    SUMMARIZATION = "summary"      # 摘要
    REWRITE = "rewrite"            # 改写/扩写
    CLASSIFICATION = "classify"    # 分类
    EXTRACTION = "extract"         # 实体抽取
    EVALUATION = "eval"            # 评估
    CHITCHAT = "chat"              # 闲聊


@dataclass
class PromptTemplate:
    """Prompt 模板"""
    id: str
    name: str
    category: PromptCategory
    template: str
    version: int
    variables: List[str]
    description: str = ""
    system_prompt: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def render(self, **kwargs) -> str:
        """
        渲染模板，替换变量

        Usage:
            prompt.render(context="...", history="...")
        """
        result = self.template
        for key, value in kwargs.items():
            placeholder = "{" + key + "}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))
        return result

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "template": self.template,
            "version": self.version,
            "variables": self.variables,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptTemplate":
        """从字典创建"""
        return cls(
            id=data["id"],
            name=data["name"],
            category=PromptCategory(data["category"]),
            template=data["template"],
            version=data["version"],
            variables=data.get("variables", []),
            description=data.get("description", ""),
            system_prompt=data.get("system_prompt", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            created_by=data.get("created_by"),
            is_active=data.get("is_active", True),
            metadata=data.get("metadata", {}),
        )


class PromptTemplateManager:
    """
    Prompt 模板管理器
    支持版本控制、场景分类、热切换
    """

    def __init__(self):
        # 存储格式：{name: [PromptTemplate, ...]}
        self._templates: Dict[str, List[PromptTemplate]] = {}
        # 激活的版本：{name: version}
        self._active_versions: Dict[str, int] = {}
        self._load_builtin_templates()

    def _load_builtin_templates(self):
        """加载内置模板"""
        builtin_templates = [
            # RAG 问答模板
            PromptTemplate(
                id="rag_qa_v1",
                name="rag_qa",
                category=PromptCategory.RAG,
                version=1,
                variables=["context", "question", "history"],
                description="RAG 检索增强问答模板",
                system_prompt="你是一个专业的问答助手。请根据提供的上下文信息回答问题。如果上下文中没有相关信息，请如实告知。",
                template="""上下文信息：
{context}

对话历史：
{history}

问题：{question}

请根据上下文信息回答问题。回答要求：
1. 只基于提供的上下文回答
2. 如果上下文中没有答案，说明你不知道
3. 引用相关段落的编号
4. 回答简洁明了

回答：""",
                is_active=True,
            ),
            # 简单问答模板
            PromptTemplate(
                id="simple_qa_v1",
                name="simple_qa",
                category=PromptCategory.QA,
                version=1,
                variables=["question"],
                description="简单问答模板",
                system_prompt="你是一个有用的助手。",
                template="请回答以下问题：\n\n问题：{question}\n\n回答：",
                is_active=True,
            ),
            # 复杂分析模板
            PromptTemplate(
                id="complex_analysis_v1",
                name="complex_analysis",
                category=PromptCategory.QA,
                version=1,
                variables=["context", "question"],
                description="复杂分析问题模板",
                system_prompt="你是一个专业的分析助手。请进行深入的分析和推理。",
                template="""上下文信息：
{context}

问题：{question}

请进行详细分析：
1. 首先理解问题的核心要点
2. 分析上下文中的相关信息
3. 进行逻辑推理
4. 给出结论和建议

分析：""",
                is_active=True,
            ),
            # 摘要模板
            PromptTemplate(
                id="summarization_v1",
                name="summarization",
                category=PromptCategory.SUMMARIZATION,
                version=1,
                variables=["text", "length"],
                description="文本摘要模板",
                system_prompt="你是一个专业的摘要助手。",
                template="请总结以下文本，控制在{length}字以内：\n\n{text}\n\n摘要：",
                is_active=True,
            ),
            # 查询改写模板
            PromptTemplate(
                id="query_rewrite_v1",
                name="query_rewrite",
                category=PromptCategory.REWRITE,
                version=1,
                variables=["query", "history"],
                description="查询改写模板（用于多轮对话）",
                system_prompt="你是一个查询改写助手。将用户的问题改写成更清晰、独立的版本。",
                template="""对话历史：
{history}

当前问题：{query}

请将当前问题改写成一个独立的、完整的问题（不依赖上下文也能理解）：
改写后的问题：""",
                is_active=True,
            ),
            # HyDE 模板
            PromptTemplate(
                id="hyde_v1",
                name="hyde",
                category=PromptCategory.REWRITE,
                version=1,
                variables=["question"],
                description="HyDE 假设文档生成模板",
                system_prompt="请生成一个假设性的文档来回答以下问题。",
                template="请生成一个详细的文档来回答以下问题。文档应该包含事实、数据和详细信息：\n\n问题：{question}\n\n假设性文档：",
                is_active=True,
            ),
            # 评估模板
            PromptTemplate(
                id="rag_eval_v1",
                name="rag_eval",
                category=PromptCategory.EVALUATION,
                version=1,
                variables=["question", "answer", "context"],
                description="RAG 答案质量评估模板",
                system_prompt="你是一个 RAG 系统评估专家。请评估答案的质量。",
                template="""请评估以下 RAG 系统生成的答案质量：

问题：{question}

上下文：{context}

答案：{answer}

评估维度：
1. 准确性（0-5 分）：答案是否准确
2. 相关性（0-5 分）：答案是否与问题相关
3. 完整性（0-5 分）：答案是否完整
4. 引用质量（0-5 分）：是否正确引用上下文

评估结果（JSON 格式）：
{{"accuracy": 0, "relevance": 0, "completeness": 0, "citation": 0, "comments": ""}}""",
                is_active=True,
            ),
            # 实体抽取模板
            PromptTemplate(
                id="entity_extraction_v1",
                name="entity_extraction",
                category=PromptCategory.EXTRACTION,
                version=1,
                variables=["text", "entity_types"],
                description="实体抽取模板",
                system_prompt="你是一个实体抽取专家。",
                template="请从以下文本中抽取以下类型的实体：{entity_types}\n\n文本：{text}\n\n实体列表（JSON 格式）：",
                is_active=True,
            ),
        ]

        for template in builtin_templates:
            self.register(template)

    def register(self, template: PromptTemplate) -> bool:
        """
        注册新模板或新版本

        Args:
            template: PromptTemplate 实例

        Returns:
            是否注册成功
        """
        name = template.name

        if name not in self._templates:
            self._templates[name] = []

        # 检查版本是否重复
        existing_versions = [t.version for t in self._templates[name]]
        if template.version in existing_versions:
            # 版本号重复，自动递增
            template.version = max(existing_versions) + 1
            logger.warning("Version %d already exists, auto-incremented to %d",
                          existing_versions[-1], template.version)

        self._templates[name].append(template)

        # 如果是第一个版本或显式标记为 active，设为激活
        if len(self._templates[name]) == 1 or template.is_active:
            self._active_versions[name] = template.version

        logger.info("Registered template | name=%s version=%d", name, template.version)
        return True

    def get(
        self,
        name: str,
        version: Optional[int] = None,
    ) -> Optional[PromptTemplate]:
        """
        获取模板

        Args:
            name: 模板名称
            version: 版本号（None 表示获取激活版本）

        Returns:
            PromptTemplate 或 None
        """
        if name not in self._templates:
            logger.warning("Template not found: %s", name)
            return None

        if version is None:
            version = self._active_versions.get(name, 1)

        for template in self._templates[name]:
            if template.version == version:
                return template

        logger.warning("Template version not found: %s v%d", name, version)
        return None

    def get_active(self, name: str) -> Optional[PromptTemplate]:
        """获取激活的模板"""
        return self.get(name, version=None)

    def list_templates(
        self,
        category: Optional[PromptCategory] = None,
    ) -> List[PromptTemplate]:
        """列出所有模板"""
        all_templates = []
        for templates in self._templates.values():
            all_templates.extend(templates)

        if category:
            all_templates = [t for t in all_templates if t.category == category]

        return all_templates

    def list_versions(self, name: str) -> List[PromptTemplate]:
        """列出模板的所有版本"""
        return self._templates.get(name, [])

    def set_active_version(self, name: str, version: int) -> bool:
        """
        设置激活版本

        Args:
            name: 模板名称
            version: 版本号

        Returns:
            是否设置成功
        """
        if name not in self._templates:
            return False

        # 检查版本是否存在
        for template in self._templates[name]:
            if template.version == version:
                self._active_versions[name] = version
                logger.info("Set active version | name=%s version=%d", name, version)
                return True

        return False

    def delete_version(self, name: str, version: int) -> bool:
        """删除指定版本"""
        if name not in self._templates:
            return False

        templates = self._templates[name]
        for i, template in enumerate(templates):
            if template.version == version:
                templates.pop(i)
                logger.info("Deleted template version | name=%s version=%d", name, version)

                # 如果删除的是激活版本，切换到最新版本
                if self._active_versions.get(name) == version:
                    if templates:
                        self._active_versions[name] = max(t.version for t in templates)
                    else:
                        del self._active_versions[name]
                        del self._templates[name]

                return True

        return False

    def export_templates(self) -> str:
        """导出所有模板为 JSON"""
        data = {
            name: [t.to_dict() for t in templates]
            for name, templates in self._templates.items()
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def import_templates(self, json_str: str) -> int:
        """从 JSON 导入模板"""
        data = json.loads(json_str)
        count = 0

        for name, templates in data.items():
            for template_data in templates:
                template = PromptTemplate.from_dict(template_data)
                self.register(template)
                count += 1

        logger.info("Imported %d templates", count)
        return count


# Global instance
_template_manager: Optional[PromptTemplateManager] = None


def get_prompt_template_manager() -> PromptTemplateManager:
    """Get or create prompt template manager"""
    global _template_manager
    if _template_manager is None:
        _template_manager = PromptTemplateManager()
    return _template_manager


def reset_prompt_template_manager():
    """Reset the global manager"""
    global _template_manager
    _template_manager = None
