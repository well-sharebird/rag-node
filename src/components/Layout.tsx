import { ReactNode, useMemo } from 'react';
import { Database, FileUp, Search, Settings, Activity, LayoutDashboard, Blocks, ShieldCheck, Network, Globe, MessageSquare, GitBranch, Plug, Cpu } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useI18n } from '@/src/lib/i18n';

interface LayoutProps {
  children: ReactNode;
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export function Layout({ children, activeTab, setActiveTab }: LayoutProps) {
  const { t, language, setLanguage } = useI18n();

  // Nav items with stable IDs and icon references - labels are translated inline below
  const navItemsBase = useMemo(() => [
    { id: 'dashboard', icon: LayoutDashboard, section: 'overview' },
    { id: 'documents', icon: FileUp, section: 'production' },
    { id: 'data-sources', icon: Plug, section: 'production' },
    { id: 'knowledge-bases', icon: Database, section: 'management' },
    { id: 'knowledge-graph', icon: GitBranch, section: 'management' },
    { id: 'retrieval-test', icon: Search, section: 'retrieval' },
    { id: 'qa-chat', icon: MessageSquare, section: 'retrieval' },
    { id: 'model-management', icon: Cpu, section: 'application' },
    { id: 'api-explorer', icon: Blocks, section: 'application' },
    { id: 'monitoring', icon: Activity, section: 'operations' },
    { id: 'settings', icon: ShieldCheck, section: 'operations' },
  ], []);

  // Group items by section - compute inline to avoid stale closures
  const sections = useMemo(() => {
    return navItemsBase.reduce<Record<string, { label: string, items: typeof navItemsBase }>>((acc, item) => {
      if (!acc[item.section]) {
        acc[item.section] = { label: t(`section.${item.section}`), items: [] };
      }
      acc[item.section].items.push(item);
      return acc;
    }, {});
  }, [navItemsBase, t]);

  return (
    <div className="flex h-screen bg-[#F8FAFC] overflow-hidden font-sans text-slate-900 selection:bg-[#1677ff]/20 selection:text-[#1677ff]">
      {/* Sidebar */}
      <aside className="w-[260px] bg-white border-r border-slate-200/70 flex flex-col h-full shrink-0 z-20">
        <div className="h-20 px-6 flex items-center justify-between border-b border-transparent">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-gradient-to-br from-[#1677ff] to-indigo-600 rounded-xl flex flex-col items-center justify-center shrink-0 shadow-[0_4px_12px_rgba(22,119,255,0.3)]">
              <div className="w-4 h-1 bg-white rounded-full mb-0.5"></div>
              <div className="w-4 h-1 bg-white/60 rounded-full"></div>
            </div>
            <span className="font-bold text-[17px] tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-slate-900 to-slate-600">RAG-NODE</span>
          </div>
          <button 
            onClick={() => setLanguage(language === 'zh' ? 'en' : 'zh')}
            className="text-slate-400 hover:text-slate-900 transition-colors w-8 h-8 flex items-center justify-center rounded-full hover:bg-slate-100"
            title={t('lang.switch')}
          >
            <Globe className="w-4 h-4" />
          </button>
        </div>
        
        <nav className="flex-1 overflow-y-auto px-4 py-6 space-y-8 custom-scrollbar">
          {Object.keys(sections).map((sectionKey) => {
            const section = sections[sectionKey];
            return (
            <div key={sectionKey} className="space-y-3">
              {sectionKey !== 'overview' && (
                <p className="text-[11px] uppercase tracking-widest text-slate-400 font-semibold px-3">
                  {section.label}
                </p>
              )}
              <ul className="space-y-1">
                {section.items.map((item) => {
                  const isActive = activeTab === item.id;
                  return (
                    <li key={item.id}>
                      <button
                        onClick={() => setActiveTab(item.id)}
                        className={cn(
                          "w-full flex items-center gap-3 text-[14px] transition-all duration-200 text-left py-2.5 px-3 rounded-xl",
                          isActive
                            ? "bg-[#1677ff]/10 text-[#1677ff] font-semibold"
                            : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                        )}
                      >
                        <item.icon className={cn("w-4.5 h-4.5", isActive ? "text-[#1677ff]" : "text-slate-400")} />
                        {t(`nav.${item.id}`)}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )})}
        </nav>
        
        <div className="p-5">
          <div className="bg-slate-50/80 border border-slate-200/60 p-4 rounded-2xl relative overflow-hidden group">
            <div className="absolute inset-0 bg-gradient-to-br from-[#1677ff]/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
            <div className="flex items-center justify-between mb-3 relative z-10">
              <p className="text-[11px] text-slate-500 font-bold uppercase tracking-wider">{t('status.title')}</p>
              <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
            </div>
            <div className="flex items-center justify-between relative z-10">
              <span className="text-xs text-slate-600 font-medium">API Latency</span>
              <span className="text-xs text-slate-900 font-bold font-mono">-- ms</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-full overflow-hidden relative">
        <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] opacity-[0.03] pointer-events-none mix-blend-multiply"></div>
        {children}
      </main>
    </div>
  );
}
