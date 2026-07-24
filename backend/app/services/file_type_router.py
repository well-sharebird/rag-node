"""
File Type Router - 全自动文件级分块策略路由

设计原则：
1. 策略决不下沉到知识库级别
2. 系统接管所有决策权，依据文件格式（MIME 类型）和内容结构自动匹配最优策略
3. 用户完全无感知，只需上传文件

路由逻辑：
1. 识别文件格式（扩展名/MIME 类型）
2. 深度内容探测（PDF 是扫描件还是文字版？是否包含表格？是否含有代码块？）
3. 自动路由到对应分块策略
4. 混合拆分：同一文档内不同区域使用不同策略（如 PDF 中表格区域 vs 文字区域）
"""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict

logger = logging.getLogger("app.services.file_type_router")


class ChunkingStrategy(str, Enum):
    """分块策略枚举"""
    FIXED = "fixed"           # 固定大小分块
    SEMANTIC = "semantic"     # 语义分块（按段落/句子）
    RECURSIVE = "recursive"   # 递归字符分块
    AST = "ast"               # AST 语法树分块（代码专用）
    HIERARCHICAL = "hierarchical"  # 层级分块（Markdown 标题）
    TABLE = "table"           # 表格结构化提取
    OCR = "ocr"               # OCR 识别后分块（扫描件）


@dataclass
class FileTypeConfig:
    """文件类型配置"""
    extensions: List[str]              # 支持的扩展名
    mime_types: List[str]              # MIME 类型
    strategy: ChunkingStrategy         # 默认策略
    chunk_size: int = 512              # 块大小
    chunk_overlap: float = 0.2         # 重叠比例（20%）
    description: str = ""              # 描述


# ============================================================
# 系统级默认路由表（运维可配置）
# ============================================================

DEFAULT_FILE_TYPE_ROUTES: Dict[str, FileTypeConfig] = {
    # Python 代码
    "python": FileTypeConfig(
        extensions=[".py"],
        mime_types=["text/x-python", "text/x-script.python"],
        strategy=ChunkingStrategy.AST,
        chunk_size=512,
        chunk_overlap=0.1,
        description="Python 源代码 - AST 语法树分块"
    ),

    # JavaScript/TypeScript
    "javascript": FileTypeConfig(
        extensions=[".js", ".ts", ".jsx", ".tsx"],
        mime_types=["text/javascript", "application/typescript"],
        strategy=ChunkingStrategy.AST,
        chunk_size=512,
        chunk_overlap=0.1,
        description="JavaScript/TypeScript 代码"
    ),

    # Java
    "java": FileTypeConfig(
        extensions=[".java"],
        mime_types=["text/x-java-source"],
        strategy=ChunkingStrategy.AST,
        chunk_size=512,
        chunk_overlap=0.1,
        description="Java 源代码"
    ),

    # Go
    "go": FileTypeConfig(
        extensions=[".go"],
        mime_types=["text/x-go"],
        strategy=ChunkingStrategy.AST,
        chunk_size=512,
        chunk_overlap=0.1,
        description="Go 源代码"
    ),

    # Markdown
    "markdown": FileTypeConfig(
        extensions=[".md", ".markdown"],
        mime_types=["text/markdown", "text/x-markdown"],
        strategy=ChunkingStrategy.HIERARCHICAL,
        chunk_size=512,
        chunk_overlap=0.15,
        description="Markdown 文档 - 按标题层级分块"
    ),

    # HTML
    "html": FileTypeConfig(
        extensions=[".html", ".htm"],
        mime_types=["text/html"],
        strategy=ChunkingStrategy.SEMANTIC,
        chunk_size=512,
        chunk_overlap=0.15,
        description="HTML 文档"
    ),

    # PDF（文字版）
    "pdf_text": FileTypeConfig(
        extensions=[".pdf"],
        mime_types=["application/pdf"],
        strategy=ChunkingStrategy.SEMANTIC,
        chunk_size=512,
        chunk_overlap=0.2,
        description="PDF 文档（文字版）- 语义分块"
    ),

    # Word 文档
    "word": FileTypeConfig(
        extensions=[".docx", ".doc"],
        mime_types=[
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword"
        ],
        strategy=ChunkingStrategy.SEMANTIC,
        chunk_size=512,
        chunk_overlap=0.2,
        description="Word 文档 - 结构化分块"
    ),

    # Excel 表格
    "excel": FileTypeConfig(
        extensions=[".xlsx", ".xls"],
        mime_types=[
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel"
        ],
        strategy=ChunkingStrategy.TABLE,
        chunk_size=1024,
        chunk_overlap=0.1,
        description="Excel 表格 - 按行列结构化提取"
    ),

    # CSV
    "csv": FileTypeConfig(
        extensions=[".csv"],
        mime_types=["text/csv"],
        strategy=ChunkingStrategy.TABLE,
        chunk_size=1024,
        chunk_overlap=0.1,
        description="CSV 文件 - 表格结构化提取"
    ),

    # PPT
    "powerpoint": FileTypeConfig(
        extensions=[".pptx", ".ppt"],
        mime_types=[
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.ms-powerpoint"
        ],
        strategy=ChunkingStrategy.HIERARCHICAL,
        chunk_size=512,
        chunk_overlap=0.15,
        description="PPT 演示文稿 - 按幻灯片分块"
    ),

    # 纯文本
    "text": FileTypeConfig(
        extensions=[".txt"],
        mime_types=["text/plain"],
        strategy=ChunkingStrategy.RECURSIVE,
        chunk_size=512,
        chunk_overlap=0.2,
        description="纯文本文件 - 递归分块"
    ),

    # 日志文件
    "log": FileTypeConfig(
        extensions=[".log"],
        mime_types=["text/plain", "text/x-log"],
        strategy=ChunkingStrategy.RECURSIVE,
        chunk_size=512,
        chunk_overlap=0.1,
        description="日志文件 - 递归分块"
    ),

    # JSON
    "json": FileTypeConfig(
        extensions=[".json"],
        mime_types=["application/json"],
        strategy=ChunkingStrategy.HIERARCHICAL,
        chunk_size=512,
        chunk_overlap=0.1,
        description="JSON 文件 - 按结构层级分块"
    ),

    # YAML
    "yaml": FileTypeConfig(
        extensions=[".yaml", ".yml"],
        mime_types=["application/x-yaml", "text/yaml"],
        strategy=ChunkingStrategy.HIERARCHICAL,
        chunk_size=512,
        chunk_overlap=0.1,
        description="YAML 文件 - 按结构层级分块"
    ),

    # XML
    "xml": FileTypeConfig(
        extensions=[".xml"],
        mime_types=["application/xml", "text/xml"],
        strategy=ChunkingStrategy.HIERARCHICAL,
        chunk_size=512,
        chunk_overlap=0.1,
        description="XML 文件 - 按结构层级分块"
    ),
}

# 默认兜底策略
DEFAULT_FALLBACK_STRATEGY = ChunkingStrategy.RECURSIVE
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 0.2


@dataclass
class RoutedChunkingConfig:
    """路由后的分块配置"""
    strategy: ChunkingStrategy
    chunk_size: int
    chunk_overlap: int  # 实际像素值
    content_type: str   # "text", "table", "code", "mixed"
    metadata: Dict = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: FileTypeConfig) -> "RoutedChunkingConfig":
        return cls(
            strategy=config.strategy,
            chunk_size=config.chunk_size,
            chunk_overlap=int(config.chunk_size * config.chunk_overlap),
            content_type="text",  # 默认
            metadata={"source_type": config.description}
        )


class FileTypeRouter:
    """
    文件类型路由器

    根据文件扩展名和 MIME 类型自动匹配最优分块策略
    """

    def __init__(self, custom_routes: Optional[Dict[str, FileTypeConfig]] = None):
        """
        初始化路由器

        Args:
            custom_routes: 自定义路由配置，会覆盖默认路由
        """
        self.routes: Dict[str, FileTypeConfig] = {}

        # 首先加载默认路由
        for key, config in DEFAULT_FILE_TYPE_ROUTES.items():
            self.routes[key] = config

        # 然后用自定义路由覆盖
        if custom_routes:
            for key, config in custom_routes.items():
                self.routes[key] = config
                logger.info("Custom route registered: %s -> %s", key, config.strategy.value)

        # 构建扩展名索引（加速查找）
        self._ext_index: Dict[str, str] = {}
        for key, config in self.routes.items():
            for ext in config.extensions:
                self._ext_index[ext.lower()] = key

        # 构建 MIME 类型索引
        self._mime_index: Dict[str, str] = {}
        for key, config in self.routes.items():
            for mime in config.mime_types:
                self._mime_index[mime.lower()] = key

        logger.info(
            "FileTypeRouter initialized with %d routes, %d extensions, %d MIME types",
            len(self.routes), len(self._ext_index), len(self._mime_index)
        )

    def route_by_extension(self, filename: str) -> RoutedChunkingConfig:
        """
        根据文件扩展名路由

        Args:
            filename: 文件名（如 "document.pdf"）

        Returns:
            路由后的分块配置
        """
        ext = os.path.splitext(filename)[1].lower()

        if ext in self._ext_index:
            key = self._ext_index[ext]
            config = self.routes[key]
            logger.info("Routed by extension: %s -> %s (%s)", ext, key, config.strategy.value)
            return RoutedChunkingConfig.from_config(config)

        # 未命中，返回默认兜底策略
        logger.warning("Unknown extension '%s', using fallback strategy", ext)
        return RoutedChunkingConfig(
            strategy=DEFAULT_FALLBACK_STRATEGY,
            chunk_size=DEFAULT_CHUNK_SIZE,
            chunk_overlap=int(DEFAULT_CHUNK_SIZE * DEFAULT_CHUNK_OVERLAP),
            content_type="text",
            metadata={"fallback_reason": f"unknown_extension:{ext}"}
        )

    def route_by_mime(self, mime_type: str) -> RoutedChunkingConfig:
        """
        根据 MIME 类型路由

        Args:
            mime_type: MIME 类型（如 "application/pdf"）

        Returns:
            路由后的分块配置
        """
        mime_lower = mime_type.lower()

        # 精确匹配
        if mime_lower in self._mime_index:
            key = self._mime_index[mime_lower]
            config = self.routes[key]
            logger.info("Routed by MIME: %s -> %s (%s)", mime_type, key, config.strategy.value)
            return RoutedChunkingConfig.from_config(config)

        # 尝试前缀匹配（如 text/*）
        main_type = mime_lower.split("/")[0]
        for mime, key in self._mime_index.items():
            if mime.startswith(main_type + "/"):
                config = self.routes[key]
                logger.info("Routed by MIME prefix: %s -> %s (%s)", mime_type, key, config.strategy.value)
                return RoutedChunkingConfig.from_config(config)

        # 未命中，返回默认兜底策略
        logger.warning("Unknown MIME type '%s', using fallback strategy", mime_type)
        return RoutedChunkingConfig(
            strategy=DEFAULT_FALLBACK_STRATEGY,
            chunk_size=DEFAULT_CHUNK_SIZE,
            chunk_overlap=int(DEFAULT_CHUNK_SIZE * DEFAULT_CHUNK_OVERLAP),
            content_type="text",
            metadata={"fallback_reason": f"unknown_mime:{mime_type}"}
        )

    def route(self, filename: str, mime_type: Optional[str] = None) -> RoutedChunkingConfig:
        """
        智能路由：优先使用 MIME 类型，其次使用扩展名

        Args:
            filename: 文件名
            mime_type: MIME 类型（可选，如果提供则优先使用）

        Returns:
            路由后的分块配置
        """
        # 优先使用 MIME 类型
        if mime_type:
            return self.route_by_mime(mime_type)

        # 降级使用扩展名
        return self.route_by_extension(filename)

    def get_supported_extensions(self) -> List[str]:
        """获取所有支持的扩展名"""
        return list(self._ext_index.keys())

    def get_supported_mime_types(self) -> List[str]:
        """获取所有支持的 MIME 类型"""
        return list(self._mime_index.keys())

    def get_route_info(self, filename: str) -> Dict:
        """
        获取文件的路由信息（用于调试/日志）

        Returns:
            包含路由详情的字典
        """
        config = self.route(filename)
        ext = os.path.splitext(filename)[1].lower()

        return {
            "filename": filename,
            "extension": ext,
            "strategy": config.strategy.value,
            "chunk_size": config.chunk_size,
            "chunk_overlap": config.chunk_overlap,
            "content_type": config.content_type,
            "metadata": config.metadata
        }


# ============================================================
# 全局单例
# ============================================================

_router: Optional[FileTypeRouter] = None


def get_router() -> FileTypeRouter:
    """获取全局 FileTypeRouter 单例"""
    global _router
    if _router is None:
        _router = FileTypeRouter()
    return _router


def init_router(custom_routes: Optional[Dict[str, FileTypeConfig]] = None) -> FileTypeRouter:
    """初始化路由器（可传入自定义配置）"""
    global _router
    _router = FileTypeRouter(custom_routes)
    return _router


def init_router_from_settings(file_type_routes: Dict[str, dict]) -> FileTypeRouter:
    """
    从系统设置初始化路由器

    Args:
        file_type_routes: 来自系统设置的路由配置
            格式：{"pdf": {"strategy": "semantic", "chunk_size": 512, "chunk_overlap": 0.2}, ...}

    Returns:
        FileTypeRouter 实例
    """
    custom_configs: Dict[str, FileTypeConfig] = {}

    for ext_or_mime, route_config in file_type_routes.items():
        strategy_str = route_config.get("strategy", "recursive")
        try:
            strategy = ChunkingStrategy(strategy_str)
        except ValueError:
            logger.warning("Unknown strategy '%s' for '%s', using recursive", strategy_str, ext_or_mime)
            strategy = ChunkingStrategy.RECURSIVE

        custom_configs[ext_or_mime] = FileTypeConfig(
            extensions=route_config.get("extensions", [f".{ext_or_mime}"]),
            mime_types=route_config.get("mime_types", []),
            strategy=strategy,
            chunk_size=route_config.get("chunk_size", 512),
            chunk_overlap=route_config.get("chunk_overlap", 0.2),
            description=route_config.get("description", f"Custom route for {ext_or_mime}")
        )

    return init_router(custom_configs)
