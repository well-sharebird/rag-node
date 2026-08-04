"""
角色菜单权限初始化脚本
为各角色分配默认的菜单权限
"""
from sqlalchemy import create_engine, text
from app.config import settings

# 各角色的默认菜单权限 (菜单 ID 列表)
ROLE_MENUS = {
    # 超级管理员 - 所有菜单
    'super_admin': list(range(1, 32)),  # 1-31 所有菜单

    # 系统管理员 - 所有菜单
    'admin': list(range(1, 32)),

    # 部门管理员 - 大部分菜单（不含系统管理）
    'dept_admin': [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31],

    # 普通用户 - 基础功能菜单
    'user': [7, 8, 9, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 25, 27],

    # 访客 - 只读菜单
    'guest': [7, 8, 9, 12, 13, 14, 15, 16, 17, 19, 25],
}


def init_role_menus():
    """初始化角色菜单权限"""
    engine = create_engine(settings.database_url.replace('postgresql+asyncpg', 'postgresql'))

    with engine.connect() as conn:
        # 获取所有角色
        result = conn.execute(text("SELECT id, name FROM roles ORDER BY id"))
        roles = {row[1]: row[0] for row in result.fetchall()}

        print("开始初始化角色菜单权限...")

        for role_name, menu_ids in ROLE_MENUS.items():
            if role_name not in roles:
                print(f"  跳过 '{role_name}': 角色不存在")
                continue

            role_id = roles[role_name]

            # 删除现有的菜单关联
            conn.execute(text("DELETE FROM role_menus WHERE role_id = :role_id"), {"role_id": role_id})

            # 插入新的菜单关联
            for menu_id in menu_ids:
                conn.execute(
                    text("INSERT INTO role_menus (role_id, menu_id) VALUES (:role_id, :menu_id)"),
                    {"role_id": role_id, "menu_id": menu_id}
                )

            print(f"  角色 '{role_name}': 分配 {len(menu_ids)} 个菜单")

        conn.commit()
        print("角色菜单权限初始化完成!")


if __name__ == "__main__":
    init_role_menus()
