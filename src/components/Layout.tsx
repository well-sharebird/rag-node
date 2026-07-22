import { ReactNode, useMemo } from 'react';
import { Database, FileUp, Search, Settings, LayoutDashboard, MessageSquare, Plug, Users, BarChart3, Activity, Blocks, Cpu, LogOut, Package, FileText } from 'lucide-react';
import { cn } from '@/lib/utils';
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

// All original features preserved, organized in 3 groups:
// Workspace: Dashboard, AI Assistant, Knowledge Bases, Documents
// Tools: Retrieval Bench, Data Ingestion, API Explorer, Model Management, Prompt Engineering
// System: Monitoring, Evaluation, Users & Roles, Settings, Token Usage, Quota Management
const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', icon: LayoutDashboard, section: 'workspace', sectionKey: 'nav.workspace' },
  { id: 'qa-chat', icon: MessageSquare, section: 'workspace', sectionKey: 'nav.workspace' },
  { id: 'knowledge-bases', icon: Database, section: 'workspace', sectionKey: 'nav.workspace', hasCount: true },
  { id: 'documents', icon: FileUp, section: 'workspace', sectionKey: 'nav.workspace' },
  { id: 'retrieval-test', icon: Search, section: 'tools', sectionKey: 'nav.tools' },
  { id: 'data-ingestion', icon: Plug, section: 'tools', sectionKey: 'nav.tools' },
  { id: 'skill-management', icon: Package, section: 'tools', sectionKey: 'nav.tools' },
  { id: 'prompt-templates', icon: FileText, section: 'tools', sectionKey: 'nav.tools' },
  { id: 'model-management', icon: Cpu, section: 'tools', sectionKey: 'nav.tools' },
  { id: 'api-explorer', icon: Blocks, section: 'tools', sectionKey: 'nav.tools' },
  { id: 'token-usage', icon: Activity, section: 'system', sectionKey: 'nav.system' },
  { id: 'quota-management', icon: Users, section: 'system', sectionKey: 'nav.system' },
  { id: 'monitoring', icon: BarChart3, section: 'system', sectionKey: 'nav.system' },
  { id: 'evaluation', icon: Settings, section: 'system', sectionKey: 'nav.system' },
  { id: 'users-roles', icon: Users, section: 'system', sectionKey: 'nav.system' },
  { id: 'settings', icon: Settings, section: 'system', sectionKey: 'nav.system' },
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

  return (
    <div className="flex h-screen overflow-hidden font-sans text-[#1a1a1a] bg-[#f7f7f7]"
         style={{ fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif" }}>
      {/* Sidebar — MiMo style: clean, minimal */}
      <aside className="w-[240px] bg-white flex flex-col h-full shrink-0 border-r border-[#e5e5e5] overflow-y-auto">
        {/* Logo — MiMo style */}
        <div className="px-5 pt-6 pb-4">
          <span className="text-lg font-semibold tracking-tight text-[#1a1a1a]">
            KnowRAG
          </span>
          <span className="text-[11px] text-[#999999] ml-2">
            {language === 'zh' ? '企业版' : 'Enterprise'}
          </span>
        </div>

        {/* Navigation — MiMo style */}
        <nav className="flex-1 px-3 py-2 space-y-6">
          {Object.entries(sections).map(([sectionKey, section]) => (
            <div key={sectionKey}>
              <p className="text-[11px] text-[#999999] font-medium px-3 pb-2 uppercase tracking-wide">
                {section.label}
              </p>
              <ul className="space-y-1">
                {section.items.map((item) => {
                  const isActive = activeTab === item.id;
                  return (
                    <li key={item.id}>
                      <button
                        onClick={() => setActiveTab(item.id)}
                        className={cn(
                          "w-full flex items-center gap-3 text-[14px] text-left py-2.5 px-3 rounded-xl transition-all duration-200",
                          isActive
                            ? "bg-[#1a1a1a] text-white font-medium shadow-md"
                            : "text-[#666666] hover:text-[#1a1a1a] hover:bg-[#f5f5f5]"
                        )}
                      >
                        <item.icon className={cn("w-[18px] h-[18px]", isActive ? "text-white" : "text-[#999999]")} />
                        {t(`nav.${item.id}`)}
                        {item.hasCount && (
                          <span className="ml-auto text-[11px] font-medium px-2 py-0.5 rounded-full bg-[#f0f0f0] text-[#666666]">
                            3
                          </span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* User footer — MiMo style */}
        <div className="mt-auto mx-4 mb-4 pt-4 border-t border-[#e5e5e5]">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium text-white bg-[#1a1a1a]">
              {getUserInitials()}
            </div>
            <div className="text-xs leading-tight flex-1 min-w-0">
              <div className="font-medium text-[#1a1a1a] truncate">{currentUser?.username || 'User'}</div>
              <div className="text-[#999999] text-[11px]">{getUserRole()}</div>
            </div>
            {onLogout && (
              <button
                onClick={onLogout}
                className="p-2 rounded-lg hover:bg-[#f5f5f5] text-[#999999] hover:text-[#ff5252] transition-colors"
                title={language === 'zh' ? '退出登录' : 'Logout'}
              >
                <LogOut className="w-4 h-4" />
              </button>
            )}
          </div>
          <button
            onClick={() => setLanguage(language === 'zh' ? 'en' : 'zh')}
            className="w-full flex items-center justify-center gap-0 rounded-xl border border-[#e5e5e5] text-[12px] py-1.5 hover:bg-[#f5f5f5] transition-colors"
          >
            <span className={cn("px-3 py-1 rounded-lg transition-all",
              language === 'zh' ? "bg-[#1a1a1a] text-white font-medium" : "text-[#666666]")}>
              中文
            </span>
            <span className={cn("px-3 py-1 rounded-lg transition-all",
              language === 'en' ? "bg-[#1a1a1a] text-white font-medium" : "text-[#666666]")}>
              EN
            </span>
          </button>
        </div>
      </aside>

      {/* Main content area — MiMo style */}
      <main className="flex-1 flex flex-col h-full overflow-hidden bg-[#f7f7f7]">
        {children}
      </main>
    </div>
  );
}
