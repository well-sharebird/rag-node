"""
菜单初始化脚本 - 创建完整的菜单树
"""
from sqlalchemy import create_engine, select, text
from app.config import settings
from app.models.menu import Menu

# 菜单数据结构
MENUS_DATA = [
    # 根菜单
    {"id": 1, "name": "系统管理", "name_i18n": "menu.admin", "menu_type": "menu", "path": "/admin", "component": None, "icon": "Settings", "order": 100, "parent_id": None, "level": 1},
    {"id": 7, "name": "工作台", "name_i18n": "nav.workspace", "menu_type": "menu", "path": "/workspace", "component": None, "icon": "LayoutDashboard", "order": 1, "parent_id": None, "level": 1},
    {"id": 8, "name": "AI 对话", "name_i18n": "nav.ai-chat", "menu_type": "menu", "path": "/ai-chat", "component": None, "icon": "MessageSquare", "order": 2, "parent_id": None, "level": 1},
    {"id": 9, "name": "知识库", "name_i18n": "nav.knowledge", "menu_type": "menu", "path": "/knowledge", "component": None, "icon": "Database", "order": 3, "parent_id": None, "level": 1},
    {"id": 10, "name": "AI 资源治理", "name_i18n": "nav.governance", "menu_type": "menu", "path": "/governance", "component": None, "icon": "Shield", "order": 4, "parent_id": None, "level": 1},
    {"id": 11, "name": "运营分析", "name_i18n": "nav.analytics", "menu_type": "menu", "path": "/analytics", "component": None, "icon": "BarChart3", "order": 5, "parent_id": None, "level": 1},

    # 系统管理子菜单
    {"id": 2, "name": "用户管理", "name_i18n": "menu.users", "menu_type": "sub_menu", "path": "/admin/users", "component": "admin/UserManagement", "icon": "Users", "order": 1, "parent_id": 1, "level": 2},
    {"id": 3, "name": "角色管理", "name_i18n": "menu.roles", "menu_type": "sub_menu", "path": "/admin/roles", "component": "admin/RoleManagement", "icon": "Shield", "order": 2, "parent_id": 1, "level": 2},
    {"id": 4, "name": "部门管理", "name_i18n": "menu.departments", "menu_type": "sub_menu", "path": "/admin/departments", "component": "admin/DepartmentManagement", "icon": "Building", "order": 3, "parent_id": 1, "level": 2},
    {"id": 5, "name": "菜单管理", "name_i18n": "menu.menus", "menu_type": "sub_menu", "path": "/admin/menus", "component": "admin/MenuManagement", "icon": "Menu", "order": 4, "parent_id": 1, "level": 2},
    {"id": 6, "name": "数据看板", "name_i18n": "menu.dashboard", "menu_type": "sub_menu", "path": "/admin/dashboard", "component": "admin/Dashboard", "icon": "BarChart", "order": 5, "parent_id": 1, "level": 2},

    # 工作台子菜单
    {"id": 12, "name": "仪表盘", "name_i18n": "nav.dashboard", "menu_type": "sub_menu", "path": "/dashboard", "component": "Dashboard", "icon": "LayoutDashboard", "order": 1, "parent_id": 7, "level": 2},

    # AI 对话子菜单
    {"id": 13, "name": "AI 助手", "name_i18n": "nav.qa-chat", "menu_type": "sub_menu", "path": "/qa-chat", "component": "QAChat", "icon": "MessageSquare", "order": 1, "parent_id": 8, "level": 2},
    {"id": 14, "name": "智能体广场", "name_i18n": "nav.agent-plaza", "menu_type": "sub_menu", "path": "/agent-plaza", "component": "AgentPlaza", "icon": "Bot", "order": 2, "parent_id": 8, "level": 2},
    {"id": 15, "name": "智能体对话", "name_i18n": "nav.agent-chat", "menu_type": "sub_menu", "path": "/agent-chat", "component": "AgentChat", "icon": "Bot", "order": 3, "parent_id": 8, "level": 2},
    {"id": 16, "name": "会话历史", "name_i18n": "nav.conversation-history", "menu_type": "sub_menu", "path": "/conversation-history", "component": "ConversationHistory", "icon": "History", "order": 4, "parent_id": 8, "level": 2},

    # 知识库子菜单
    {"id": 17, "name": "知识库", "name_i18n": "nav.knowledge-bases", "menu_type": "sub_menu", "path": "/knowledge-bases", "component": "KnowledgeBaseManager", "icon": "Database", "order": 1, "parent_id": 9, "level": 2},
    {"id": 18, "name": "数据摄取", "name_i18n": "nav.data-ingestion", "menu_type": "sub_menu", "path": "/data-ingestion", "component": "DataIngestion", "icon": "Plug", "order": 2, "parent_id": 9, "level": 2},
    {"id": 19, "name": "检索测试", "name_i18n": "nav.retrieval-test", "menu_type": "sub_menu", "path": "/retrieval-test", "component": "RetrievalTest", "icon": "Search", "order": 3, "parent_id": 9, "level": 2},

    # AI 资源治理子菜单
    {"id": 20, "name": "模型管理", "name_i18n": "nav.model-management", "menu_type": "sub_menu", "path": "/model-management", "component": "ModelManagement", "icon": "Cpu", "order": 1, "parent_id": 10, "level": 2},
    {"id": 21, "name": "技能仓库", "name_i18n": "nav.skill-management", "menu_type": "sub_menu", "path": "/skill-management", "component": "SkillManagement", "icon": "Package", "order": 2, "parent_id": 10, "level": 2},
    {"id": 22, "name": "提示词工程", "name_i18n": "nav.prompt-templates", "menu_type": "sub_menu", "path": "/prompt-templates", "component": "PromptTemplates", "icon": "FileText", "order": 3, "parent_id": 10, "level": 2},
    {"id": 23, "name": "同义词管理", "name_i18n": "nav.synonym-management", "menu_type": "sub_menu", "path": "/synonym-management", "component": "SynonymManagement", "icon": "Languages", "order": 4, "parent_id": 10, "level": 2},
    {"id": 24, "name": "数据脱敏", "name_i18n": "nav.desensitization-management", "menu_type": "sub_menu", "path": "/desensitization-management", "component": "DesensitizationManagement", "icon": "Shield", "order": 5, "parent_id": 10, "level": 2},

    # 运营分析子菜单
    {"id": 25, "name": "系统监控", "name_i18n": "nav.monitoring", "menu_type": "sub_menu", "path": "/monitoring", "component": "Monitoring", "icon": "Activity", "order": 1, "parent_id": 11, "level": 2},
    {"id": 26, "name": "执行追踪", "name_i18n": "nav.execution-tracing", "menu_type": "sub_menu", "path": "/execution-tracing", "component": "ExecutionTracing", "icon": "ActivitySquare", "order": 2, "parent_id": 11, "level": 2},
    {"id": 27, "name": "Token 使用", "name_i18n": "nav.token-usage", "menu_type": "sub_menu", "path": "/token-usage", "component": "TokenUsage", "icon": "BarChart3", "order": 3, "parent_id": 11, "level": 2},
    {"id": 28, "name": "配额管理", "name_i18n": "nav.quota-management", "menu_type": "sub_menu", "path": "/quota-management", "component": "QuotaManagement", "icon": "Users", "order": 4, "parent_id": 11, "level": 2},
    {"id": 29, "name": "质量评估", "name_i18n": "nav.evaluation", "menu_type": "sub_menu", "path": "/evaluation", "component": "Evaluation", "icon": "Settings", "order": 5, "parent_id": 11, "level": 2},
    {"id": 30, "name": "API 接口", "name_i18n": "nav.api-explorer", "menu_type": "sub_menu", "path": "/api-explorer", "component": "ApiExplorer", "icon": "Blocks", "order": 6, "parent_id": 11, "level": 2},
    {"id": 31, "name": "系统设置", "name_i18n": "nav.settings", "menu_type": "sub_menu", "path": "/settings", "component": "SystemSettings", "icon": "Settings", "order": 7, "parent_id": 11, "level": 2},
]


def init_menus():
    """初始化菜单数据"""
    engine = create_engine(settings.database_url.replace('postgresql+asyncpg', 'postgresql'))

    with engine.connect() as conn:
        # 检查是否已有菜单数据
        result = conn.execute(text("SELECT COUNT(*) FROM menus"))
        count = result.scalar()

        if count > 10:
            print(f"已有 {count} 条菜单数据，跳过初始化")
            return

        print(f"当前有 {count} 条菜单数据，开始初始化...")

        # 插入菜单数据
        for menu_data in MENUS_DATA:
            # 检查是否已存在
            existing = conn.execute(
                text("SELECT id FROM menus WHERE id = :id"),
                {"id": menu_data["id"]}
            ).fetchone()

            if existing:
                # 更新现有菜单
                from datetime import datetime
                now = datetime.utcnow().isoformat()
                conn.execute(text("""
                    UPDATE menus SET
                        name = :name,
                        name_i18n = :name_i18n,
                        menu_type = :menu_type,
                        path = :path,
                        component = :component,
                        icon = :icon,
                        "order" = :order,
                        parent_id = :parent_id,
                        level = :level,
                        is_visible = :is_visible,
                        is_hidden = :is_hidden,
                        is_active = :is_active,
                        updated_at = :updated_at
                    WHERE id = :id
                """), {
                    **menu_data,
                    "component": menu_data.get("component"),
                    "is_visible": True,
                    "is_hidden": False,
                    "is_active": True,
                    "updated_at": now,
                })
                print(f"  更新菜单 ID={menu_data['id']}, name={menu_data['name']}")
            else:
                # 插入新菜单
                from datetime import datetime
                now = datetime.utcnow().isoformat()
                conn.execute(text("""
                    INSERT INTO menus (
                        id, name, name_i18n, menu_type, path, component, icon, "order",
                        parent_id, level, is_visible, is_hidden, is_active, is_external,
                        keep_alive, tree_path, created_at, updated_at
                    ) VALUES (
                        :id, :name, :name_i18n, :menu_type, :path, :component, :icon, :order,
                        :parent_id, :level, :is_visible, :is_hidden, :is_active, :is_external,
                        :keep_alive, :tree_path, :created_at, :updated_at
                    )
                """), {
                    **menu_data,
                    "component": menu_data.get("component"),
                    "is_visible": True,
                    "is_hidden": False,
                    "is_active": True,
                    "is_external": False,
                    "keep_alive": True,
                    "tree_path": f"/{menu_data['parent_id'] or ''}/{menu_data['id']}/" if menu_data['parent_id'] else f"/{menu_data['id']}/",
                    "created_at": now,
                    "updated_at": now,
                })
                print(f"  创建菜单 ID={menu_data['id']}, name={menu_data['name']}")

        conn.commit()
        print("菜单初始化完成!")


if __name__ == "__main__":
    init_menus()
