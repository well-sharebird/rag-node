import { ReactNode, useMemo, useState } from 'react';
import { Database, FileUp, Search, Settings, LayoutDashboard, MessageSquare, Plug, Users, BarChart3, Activity, Blocks, Cpu, LogOut, Package, FileText, GitBranch, Bot, Shield, Languages, ActivitySquare } from 'lucide-react';
import { useI18n } from '@/src/lib/i18n';

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
  onLogout?: () => void;
}

interface NavItem {
  id: string;
  icon: typeof LayoutDashboard;
  section: string;
  sectionKey: string;
  hasCount?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', icon: LayoutDashboard, section: 'workspace', sectionKey: 'nav.workspace' },
  { id: 'qa-chat', icon: MessageSquare, section: 'workspace', sectionKey: 'nav.workspace' },
  { id: 'agent-plaza', icon: Bot, section: 'workspace', sectionKey: 'nav.workspace' },
  { id: 'knowledge-bases', icon: Database, section: 'knowledge', sectionKey: 'nav.knowledge' },
  { id: 'data-ingestion', icon: Plug, section: 'knowledge', sectionKey: 'nav.knowledge' },
  { id: 'retrieval-test', icon: Search, section: 'knowledge', sectionKey: 'nav.knowledge' },
  { id: 'model-management', icon: Cpu, section: 'governance', sectionKey: 'nav.governance' },
  { id: 'model-routing', icon: GitBranch, section: 'governance', sectionKey: 'nav.governance' },
  { id: 'skill-management', icon: Package, section: 'governance', sectionKey: 'nav.governance' },
  { id: 'prompt-templates', icon: FileText, section: 'governance', sectionKey: 'nav.governance' },
  { id: 'synonym-management', icon: Languages, section: 'governance', sectionKey: 'nav.governance' },
  { id: 'desensitization-management', icon: Shield, section: 'governance', sectionKey: 'nav.governance' },
  { id: 'monitoring', icon: Activity, section: 'operations', sectionKey: 'nav.operations' },
  { id: 'execution-tracing', icon: ActivitySquare, section: 'operations', sectionKey: 'nav.operations' },
  { id: 'token-usage', icon: BarChart3, section: 'operations', sectionKey: 'nav.operations' },
  { id: 'quota-management', icon: Users, section: 'operations', sectionKey: 'nav.operations' },
  { id: 'evaluation', icon: Settings, section: 'operations', sectionKey: 'nav.operations' },
  { id: 'users-roles', icon: Users, section: 'admin', sectionKey: 'nav.admin' },
  { id: 'api-explorer', icon: Blocks, section: 'admin', sectionKey: 'nav.admin' },
  { id: 'settings', icon: Settings, section: 'admin', sectionKey: 'nav.admin' },
];

export function Layout({ children, activeTab, setActiveTab, currentUser, onLogout }: LayoutProps) {
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

  const sections = useMemo(() => {
    return NAV_ITEMS.reduce<Record<string, { label: string, items: NavItem[] }>>((acc, item) => {
      if (!acc[item.section]) {
        acc[item.section] = { label: t(item.sectionKey), items: [] };
      }
      acc[item.section].items.push(item);
      return acc;
    }, {});
  }, [t]);

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
      {/* Sidebar — 方案A：浅灰侧栏 #FAFBFC，内容区纯白 */}
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
                      // Left border indicator for active
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
                    {/* Left border indicator for active item */}
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
                    {t(`nav.${item.id}`)}
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
            {/* Avatar */}
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

          {/* Language toggle */}
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
