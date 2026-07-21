#!/usr/bin/env python
"""
Direct SQL initialization of admin user using asyncpg
"""
import asyncio
import sys
sys.path.insert(0, '.')
import asyncpg
from app.core.security import hash_password

async def main():
    print("Connecting to database...")
    conn = await asyncpg.connect(
        host='100.4.14.19',
        port=5432,
        user='postgres',
        password='postgres123',
        database='rag_db'
    )

    try:
        # Create permissions
        permissions = [
            ('knowledge_base.create', 'Permission to create knowledge_base', 'knowledge_base', 'create'),
            ('knowledge_base.read', 'Permission to read knowledge_base', 'knowledge_base', 'read'),
            ('knowledge_base.update', 'Permission to update knowledge_base', 'knowledge_base', 'update'),
            ('knowledge_base.delete', 'Permission to delete knowledge_base', 'knowledge_base', 'delete'),
            ('document.create', 'Permission to create document', 'document', 'create'),
            ('document.read', 'Permission to read document', 'document', 'read'),
            ('document.update', 'Permission to update document', 'document', 'update'),
            ('document.delete', 'Permission to delete document', 'document', 'delete'),
            ('retrieval.search', 'Permission to search retrieval', 'retrieval', 'search'),
            ('retrieval.chat', 'Permission to chat retrieval', 'retrieval', 'chat'),
            ('settings.read', 'Permission to read settings', 'settings', 'read'),
            ('settings.update', 'Permission to update settings', 'settings', 'update'),
            ('admin.manage_users', 'Permission to manage_users admin', 'admin', 'manage_users'),
            ('admin.view_audit_logs', 'Permission to view_audit_logs admin', 'admin', 'view_audit_logs'),
            ('api_key.create', 'Permission to create api_key', 'api_key', 'create'),
            ('api_key.read', 'Permission to read api_key', 'api_key', 'read'),
            ('api_key.update', 'Permission to update api_key', 'api_key', 'update'),
            ('api_key.delete', 'Permission to delete api_key', 'api_key', 'delete'),
        ]

        for name, desc, resource, action in permissions:
            await conn.execute("""
                INSERT INTO permissions (name, description, resource, action)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (name) DO NOTHING
            """, name, desc, resource, action)
        print(f"Created {len(permissions)} permissions")

        # Create roles
        roles = [
            ('Admin', '平台全量控制：用户管理、角色分配、系统配置、审计日志查看、告警管理', True),
            ('Editor', '知识库内容运营：上传文档、管理连接器、审查分块质量、运行评估测试', True),
            ('Viewer', '纯查询权限：在授权知识库范围内提问、查看引用来源、反馈答案质量', True),
            ('Developer', '程序化集成：通过 API 构建自定义应用、集成聊天机器人、管理 API Keys', True),
        ]

        for name, desc, is_system in roles:
            await conn.execute("""
                INSERT INTO roles (name, description, is_system)
                VALUES ($1, $2, $3)
                ON CONFLICT (name) DO NOTHING
            """, name, desc, is_system)
        print(f"Created {len(roles)} roles")

        # Create admin user
        from datetime import datetime
        now = datetime.utcnow()
        password_hash = hash_password("admin123")
        await conn.execute("""
            INSERT INTO users (email, username, hashed_password, full_name, is_active, is_superuser, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (username) DO UPDATE SET
                email = EXCLUDED.email,
                full_name = EXCLUDED.full_name,
                hashed_password = EXCLUDED.hashed_password,
                is_active = EXCLUDED.is_active
        """, "admin@example.com", "admin", password_hash, "System Administrator", True, True, now, now)
        print("Created admin user (password: admin123)")

        # Assign Admin role to admin user
        await conn.execute("""
            INSERT INTO user_roles (user_id, role_id)
            SELECT u.id, r.id FROM users u, roles r
            WHERE u.username = 'admin' AND r.name = 'Admin'
            ON CONFLICT (user_id, role_id) DO NOTHING
        """)
        print("Assigned Admin role to admin user")

        # Assign permissions to roles
        admin_perms = [p[0] for p in permissions]
        editor_perms = [
            'knowledge_base.create', 'knowledge_base.read', 'knowledge_base.update',
            'document.create', 'document.read', 'document.update', 'document.delete',
            'retrieval.search', 'retrieval.chat', 'settings.read'
        ]
        viewer_perms = [
            'knowledge_base.read', 'document.read',
            'retrieval.search', 'retrieval.chat', 'settings.read'
        ]
        developer_perms = viewer_perms + [
            'api_key.create', 'api_key.read', 'api_key.update', 'api_key.delete'
        ]

        role_perms = {
            'Admin': admin_perms,
            'Editor': editor_perms,
            'Viewer': viewer_perms,
            'Developer': developer_perms,
        }

        for role_name, perm_list in role_perms.items():
            for perm_name in perm_list:
                await conn.execute("""
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT r.id, p.id FROM roles r, permissions p
                    WHERE r.name = $1 AND p.name = $2
                    ON CONFLICT (role_id, permission_id) DO NOTHING
                """, role_name, perm_name)
        print("Assigned permissions to roles")

        print("\n✓ Initialization complete!")
        print("\nLogin credentials:")
        print("  Username: admin")
        print("  Password: admin123")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
