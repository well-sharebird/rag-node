import { ReactNode, useMemo, useState } from 'react';
import { Database, FileUp, Search, Settings, LayoutDashboard, MessageSquare, Plug, Users, BarChart3, Activity, Blocks, Cpu, LogOut, Package, FileText, GitBranch, Bot, Shield, Languages, ActivitySquare, History, BarChart2 } from 'lucide-react';
import { useI18n } from '@/src/lib/i18n';
import { MenuData } from '@/lib/api-client';

interface User {
  id: number;
  email: string;
  username: string;
  fullName?: string;
  roles?: Array<{ id: number; name: string }>;
}

interface LayoutProps {
  children: ReactNode;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  currentUser?: User | null;
  menus?: MenuData[] | null;
  onLogout?: () => void;
}

interface NavItem {
  id: string;
  icon: any;
  section: string;
  sectionKey: string;
  path?: string;
  hasCount?: boolean;
  label?: string;  // Menu name for display
}

// 硬编码的菜单项作为后备
const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', icon: LayoutDashboard, section: 'workspace', sectionKey: 'nav.workspace' },
  { id: 'qa-chat', icon: MessageSquare, section: 'ai-chat', sectionKey: 'nav.ai-chat' },
  { id: 'agent-plaza', icon: Bot, section: 'ai-chat', sectionKey: 'nav.ai-chat' },
  { id: 'agent-chat', icon: Bot, section: 'ai-chat', sectionKey: 'nav.ai-chat' },
  { id: 'conversation-history', icon: History, section: 'ai-chat', sectionKey: 'nav.ai-chat' },
  { id: 'knowledge-bases', icon: Database, section: 'knowledge', sectionKey: 'nav.knowledge' },
  { id: 'data-ingestion', icon: Plug, section: 'knowledge', sectionKey: 'nav.knowledge' },
  { id: 'retrieval-test', icon: Search, section: 'knowledge', sectionKey: 'nav.knowledge' },
  { id: 'model-management', icon: Cpu, section: 'governance', sectionKey: 'nav.governance' },
  { id: 'model-routing', icon: GitBranch, section: 'governance', sectionKey: 'nav.governance' },
  { id: 'skill-management', icon: Package, section: 'governance', sectionKey: 'nav.governance' },
  { id: 'prompt-templates', icon: FileText, section: 'governance', sectionKey: 'nav.governance' },
  { id: 'synonym-management', icon: Languages, section: 'governance', sectionKey: 'nav.governance' },
  { id: 'desensitization-management', icon: Shield, section: 'governance', sectionKey: 'nav.governance' },
  { id: 'monitoring', icon: Activity, section: 'analytics', sectionKey: 'nav.analytics' },
  { id: 'execution-tracing', icon: ActivitySquare, section: 'analytics', sectionKey: 'nav.analytics' },
  { id: 'token-usage', icon: BarChart3, section: 'analytics', sectionKey: 'nav.analytics' },
  { id: 'quota-management', icon: Users, section: 'analytics', sectionKey: 'nav.analytics' },
  { id: 'evaluation', icon: Settings, section: 'analytics', sectionKey: 'nav.analytics' },
  { id: 'users-roles', icon: Users, section: 'admin', sectionKey: 'nav.admin' },
  { id: 'api-explorer', icon: Blocks, section: 'admin', sectionKey: 'nav.admin' },
  { id: 'settings', icon: Settings, section: 'admin', sectionKey: 'nav.admin' },
];

// 菜单路径映射
const MENU_PATH_MAP: Record<string, string> = {
  '/admin': 'users-roles',
  '/admin/users': 'users-roles',
  '/admin/roles': 'users-roles',
  '/admin/departments': 'users-roles',
  '/admin/menus': 'users-roles',
  '/admin/dashboard': 'dashboard',
};

// 图标映射
const ICON_MAP: Record<string, any> = {
  'Settings': Settings,
  'Users': Users,
  'Shield': Shield,
  'Building': Database,
  'Menu': LayoutDashboard,
  'BarChart': BarChart2,
  'Database': Database,
  'Search': Search,
  'MessageSquare': MessageSquare,
  'Bot': Bot,
  'History': History,
  'Plug': Plug,
  'Cpu': Cpu,
  'GitBranch': GitBranch,
  'Package': Package,
  'FileText': FileText,
  'Languages': Languages,
  'Activity': Activity,
  'ActivitySquare': ActivitySquare,
  'BarChart3': BarChart3,
  'Blocks': Blocks,
  'LayoutDashboard': LayoutDashboard,
};

function getIconByName(iconName?: string) {
  if (!iconName) return LayoutDashboard;
  return ICON_MAP[iconName] || LayoutDashboard;
}

// 根据后端菜单路径获取前端 tab id
function getMenuTabId(menu: MenuData): string {
  // 检查是否有自定义路径映射
  if (menu.path && MENU_PATH_MAP[menu.path]) {
    return MENU_PATH_MAP[menu.path];
  }
  // 默认使用菜单的 name_i18n 或 name 作为 key
  const key = menu.name_i18n || menu.name;
  // 转换为前端 tab id 格式
  return key.replace('menu.', '').replace(/\./g, '-');
}

export function Layout({ children, activeTab, setActiveTab, currentUser, menus, onLogout }: LayoutProps) {
  const { t, language, setLanguage } = useI18n();

  const getUserInitials = () => {
    if (currentUser?.fullName) {
      return currentUser.fullName.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
    }
    return currentUser?.username?.toUpperCase().slice(0, 2) || 'U';
  };

  const getUserRole = () => {
    if (currentUser?.roles?.length) {
      return currentUser.roles[0].name;
    }
    return 'User';
  };

  // 从后端菜单构建导航项
  const dynamicNavItems = useMemo(() => {
    if (!menus || menus.length === 0) {
      return NAV_ITEMS;
    }

    const items: NavItem[] = [];
    const seenIds = new Set<string>();

    // 根据路径确定分组
    const getSectionForPath = (path: string): string => {
      if (path?.includes('/admin')) return 'admin';
      if (path?.includes('/knowledge') || path?.includes('/data-ingestion')) return 'knowledge';
      if (path?.includes('/model') || path?.includes('/skill') || path?.includes('/governance')) return 'governance';
      if (path?.includes('/analytics') || path?.includes('/monitor') || path?.includes('/token') || path?.includes('/quota') || path?.includes('/evaluation') || path?.includes('/api-explorer') || path?.includes('/settings')) return 'analytics';
      if (path?.includes('/workspace') || path?.includes('/dashboard')) return 'workspace';
      if (path?.includes('/ai-chat') || path?.includes('/qa-chat') || path?.includes('/agent') || path?.includes('/conversation')) return 'ai-chat';
      return 'workspace';
    };

    // 递归处理菜单树
    const processMenu = (menuList: MenuData[]) => {
      for (const menu of menuList) {
        // 跳过不可见、隐藏或非激活的菜单
        if (!menu.is_visible || menu.is_hidden || !menu.is_active) {
          continue;
        }

        const icon = getIconByName(menu.icon);

        // 目录类型（menu）作为分组，子菜单根据父级目录确定分组
        let section: string;
        if (menu.menu_type === 'menu') {
          // 目录本身根据名称确定分组
          section = getSectionForMenuName(menu.name);
          // 递归处理子菜单
          if (menu.children && menu.children.length > 0) {
            processMenuWithSection(menu.children, section);
          }
          continue;
        } else {
          // 子菜单继承父级目录的分组
          section = getSectionForPath(menu.path);
        }

        // 子菜单（sub_menu）和按钮（button）添加到导航
        const tabId = `m-${menu.id}`;

        if (seenIds.has(tabId)) {
          continue;
        }
        seenIds.add(tabId);

        items.push({
          id: tabId,
          icon,
          section,
          sectionKey: menu.name_i18n || `nav.m-${menu.id}`,
          path: menu.path,
          label: menu.name,
        });

        // 递归处理更深层的子菜单
        if (menu.children && menu.children.length > 0) {
          processMenuWithSection(menu.children, section);
        }
      }
    };

    // 递归处理菜单树（带分组参数）
    const processMenuWithSection = (menuList: MenuData[], section: string) => {
      for (const menu of menuList) {
        if (!menu.is_visible || menu.is_hidden || !menu.is_active) {
          continue;
        }

        const tabId = `m-${menu.id}`;
        if (seenIds.has(tabId)) {
          continue;
        }
        seenIds.add(tabId);

        const icon = getIconByName(menu.icon);

        items.push({
          id: tabId,
          icon,
          section,
          sectionKey: menu.name_i18n || `nav.m-${menu.id}`,
          path: menu.path,
          label: menu.name,
        });

        if (menu.children && menu.children.length > 0) {
          processMenuWithSection(menu.children, section);
        }
      }
    };

    // 根据目录名称确定分组
    const getSectionForMenuName = (menuName: string): string => {
      const sectionMap: Record<string, string> = {
        '系统管理': 'admin',
        '工作台': 'workspace',
        'AI 对话': 'ai-chat',
        '知识库': 'knowledge',
        'AI 资源治理': 'governance',
        '运营分析': 'analytics',
      };
      return sectionMap[menuName] || 'workspace';
    };

    processMenu(menus);

    // 如果没有动态菜单，返回硬编码的菜单
    return items.length > 0 ? items : NAV_ITEMS;
  }, [menus]);

  const sections = useMemo(() => {
    return dynamicNavItems.reduce<Record<string, { label: string, items: NavItem[] }>>((acc, item) => {
      if (!acc[item.section]) {
        // 使用硬编码的分组标签
        const sectionLabels: Record<string, string> = {
          workspace: t('nav.workspace'),
          'ai-chat': t('nav.ai-chat'),
          knowledge: t('nav.knowledge'),
          governance: t('nav.governance'),
          analytics: t('nav.analytics'),
          admin: t('nav.admin'),
        };
        acc[item.section] = { label: sectionLabels[item.section] || item.section, items: [] };
      }
      acc[item.section].items.push(item);
      return acc;
    }, {});
  }, [dynamicNavItems, t]);

  const isItemActive = (itemId: string) => activeTab === itemId;

  return (
    <div style={{
      display: 'flex',
      height: '100vh',
      overflow: 'hidden',
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif",
      color: 'var(--text-primary)',
      backgroundColor: '#FFFFFF',
    }}>
      {/* Sidebar */}
      <aside style={{
        width: '200px',
        backgroundColor: 'var(--sidebar-bg)',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        flexShrink: 0,
        borderRight: '1px solid #F0F0F0',
        overflowY: 'auto',
        overflowX: 'hidden',
      }}>
        {/* Logo */}
        <div style={{ padding: '20px 16px 12px' }}>
          <div style={{ display: 'flex', alignItems: 'baseline' }}>
            <span style={{
              fontSize: '17px',
              fontWeight: 700,
              letterSpacing: '-0.3px',
              color: '#1F2937',
            }}>
              KnowRAG
            </span>
            <span style={{
              fontSize: '10px',
              color: 'var(--text-tertiary)',
              marginLeft: '6px',
              fontWeight: 500,
            }}>
              {language === 'zh' ? '企业版' : 'Enterprise'}
            </span>
          </div>
        </div>

        {/* Navigation */}
        <nav style={{ flex: 1, padding: '0 8px 8px' }}>
          {Object.entries(sections).map(([sectionKey, section]) => (
            <div key={sectionKey} style={{ marginBottom: '4px' }}>
              <p style={{
                fontSize: '10px',
                color: 'var(--text-tertiary)',
                fontWeight: 600,
                padding: '12px 12px 6px',
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
              }}>
                {section.label}
              </p>
              {section.items.map((item) => {
                const active = isItemActive(item.id);
                return (
                  <button
                    key={item.id}
                    onClick={() => setActiveTab(item.id)}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                      fontSize: '13px',
                      textAlign: 'left',
                      padding: '7px 12px',
                      margin: '1px 0',
                      borderRadius: '6px',
                      border: 'none',
                      cursor: 'pointer',
                      fontWeight: active ? 600 : 400,
                      color: active ? 'var(--accent)' : 'var(--text-secondary)',
                      backgroundColor: active ? '#FFFFFF' : 'transparent',
                      boxShadow: active ? '0 1px 2px rgba(0,0,0,0.04)' : 'none',
                      transition: 'all 0.15s ease',
                      position: 'relative' as const,
                    }}
                    onMouseEnter={(e) => {
                      if (!active) {
                        e.currentTarget.style.backgroundColor = 'var(--gray-50)';
                        e.currentTarget.style.color = 'var(--text-primary)';
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!active) {
                        e.currentTarget.style.backgroundColor = 'transparent';
                        e.currentTarget.style.color = 'var(--text-secondary)';
                      }
                    }}
                  >
                    {active && (
                      <div style={{
                        position: 'absolute',
                        left: 0,
                        top: 6,
                        bottom: 6,
                        width: '3px',
                        borderRadius: '0 3px 3px 0',
                        backgroundColor: 'var(--accent)',
                      }} />
                    )}
                    <item.icon
                      style={{
                        width: '16px',
                        height: '16px',
                        flexShrink: 0,
                        color: active ? 'var(--accent)' : 'var(--text-tertiary)',
                      }}
                    />
                    {item.sectionKey ? t(item.sectionKey) : item.label || item.id}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        {/* User footer */}
        <div style={{
          padding: '12px 12px 16px',
          marginTop: 'auto',
          borderTop: '1px solid var(--sidebar-border)',
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            marginBottom: '10px',
          }}>
            <div style={{
              width: '30px',
              height: '30px',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '12px',
              fontWeight: 600,
              color: '#FFFFFF',
              background: 'var(--accent)',
              flexShrink: 0,
            }}>
              {getUserInitials()}
            </div>
            <div style={{
              flex: 1,
              minWidth: 0,
              fontSize: '12px',
            }}>
              <div style={{
                fontWeight: 500,
                color: 'var(--text-primary)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {currentUser?.username || 'User'}
              </div>
              <div style={{ color: 'var(--text-tertiary)', fontSize: '11px' }}>
                {getUserRole()}
              </div>
            </div>
            {onLogout && (
              <button
                onClick={onLogout}
                title={language === 'zh' ? '退出登录' : 'Logout'}
                style={{
                  padding: '4px',
                  borderRadius: '6px',
                  backgroundColor: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  color: 'var(--text-tertiary)',
                  display: 'flex',
                  transition: 'all 0.15s ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--error-bg)';
                  e.currentTarget.style.color = 'var(--error)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                  e.currentTarget.style.color = 'var(--text-tertiary)';
                }}
              >
                <LogOut style={{ width: '14px', height: '14px' }} />
              </button>
            )}
          </div>

          <button
            onClick={() => setLanguage(language === 'zh' ? 'en' : 'zh')}
            style={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '4px',
              borderRadius: '6px',
              border: '1px solid var(--sidebar-border)',
              fontSize: '11px',
              padding: '5px 0',
              backgroundColor: 'transparent',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              color: 'var(--text-secondary)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'var(--gray-50)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            <span style={{
              padding: '2px 10px',
              borderRadius: '4px',
              fontWeight: language === 'zh' ? 600 : 400,
              color: language === 'zh' ? 'var(--accent)' : 'var(--text-secondary)',
              backgroundColor: language === 'zh' ? 'var(--accent-light)' : 'transparent',
              transition: 'all 0.15s ease',
            }}>
              中文
            </span>
            <span style={{
              padding: '2px 10px',
              borderRadius: '4px',
              fontWeight: language === 'en' ? 600 : 400,
              color: language === 'en' ? 'var(--accent)' : 'var(--text-secondary)',
              backgroundColor: language === 'en' ? 'var(--accent-light)' : 'transparent',
              transition: 'all 0.15s ease',
            }}>
              EN
            </span>
          </button>
        </div>
      </aside>

      {/* Main content area */}
      <main style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
        backgroundColor: '#FFFFFF',
      }}>
        {children}
      </main>
    </div>
  );
}
