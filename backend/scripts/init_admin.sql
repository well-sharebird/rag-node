-- ============================================================
-- Initialize Admin User for RAG Platform
-- Run this on your PostgreSQL database to create default admin
-- ============================================================
-- Usage: psql -h 100.4.14.19 -U rag -d rag -f init_admin.sql
-- ============================================================

-- Create permissions (if not exists)
INSERT INTO permissions (name, description, resource, action)
VALUES
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
    ('api_key.delete', 'Permission to delete api_key', 'api_key', 'delete')
ON CONFLICT (name) DO NOTHING;

-- Create roles (if not exists)
INSERT INTO roles (name, description, is_system)
VALUES
    ('Admin', '平台全量控制：用户管理、角色分配、系统配置、审计日志查看、告警管理', true),
    ('Editor', '知识库内容运营：上传文档、管理连接器、审查分块质量、运行评估测试', true),
    ('Viewer', '纯查询权限：在授权知识库范围内提问、查看引用来源、反馈答案质量', true),
    ('Developer', '程序化集成：通过 API 构建自定义应用、集成聊天机器人、管理 API Keys', true)
ON CONFLICT (name) DO NOTHING;

-- Assign permissions to Admin role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'Admin'
AND p.name IN (
    'knowledge_base.create', 'knowledge_base.read', 'knowledge_base.update', 'knowledge_base.delete',
    'document.create', 'document.read', 'document.update', 'document.delete',
    'retrieval.search', 'retrieval.chat',
    'settings.read', 'settings.update',
    'admin.manage_users', 'admin.view_audit_logs'
)
ON CONFLICT DO NOTHING;

-- Assign permissions to Editor role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'Editor'
AND p.name IN (
    'knowledge_base.create', 'knowledge_base.read', 'knowledge_base.update',
    'document.create', 'document.read', 'document.update', 'document.delete',
    'retrieval.search', 'retrieval.chat',
    'settings.read'
)
ON CONFLICT DO NOTHING;

-- Assign permissions to Viewer role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'Viewer'
AND p.name IN (
    'knowledge_base.read',
    'document.read',
    'retrieval.search', 'retrieval.chat',
    'settings.read'
)
ON CONFLICT DO NOTHING;

-- Assign permissions to Developer role
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles r, permissions p
WHERE r.name = 'Developer'
AND p.name IN (
    'knowledge_base.read',
    'document.read',
    'retrieval.search', 'retrieval.chat',
    'settings.read',
    'api_key.create', 'api_key.read', 'api_key.update', 'api_key.delete'
)
ON CONFLICT DO NOTHING;

-- Create admin user (password: admin123, hashed with bcrypt)
-- You may need to regenerate the hash using your application's hash_password function
INSERT INTO users (email, username, hashed_password, full_name, is_active, is_superuser)
VALUES (
    'admin@example.com',
    'admin',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYzS3MebAJu',  -- admin123
    'System Administrator',
    true,
    true
)
ON CONFLICT (username) DO UPDATE SET
    email = EXCLUDED.email,
    full_name = EXCLUDED.full_name,
    is_active = EXCLUDED.is_active;

-- Assign Admin role to admin user
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.username = 'admin' AND r.name = 'Admin'
ON CONFLICT DO NOTHING;

-- ============================================================
-- Verify the setup
-- ============================================================
SELECT 'Roles created:' as info, COUNT(*) FROM roles;
SELECT 'Permissions created:' as info, COUNT(*) FROM permissions;
SELECT 'Admin user:' as info, username, email, is_active FROM users WHERE username = 'admin';
SELECT 'Admin roles:' as info, r.name FROM roles r
JOIN user_roles ur ON r.id = ur.role_id
JOIN users u ON u.id = ur.user_id
WHERE u.username = 'admin';
