import { useState } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { DataSourceManagement } from '@/src/pages/DataSourceManagement';
import { ModelManagement } from '@/src/pages/ModelManagement';
import { cn } from '@/lib/utils';

type Tab = 'sources' | 'models';

export function DataIngestionView() {
  const { t } = useI18n();
  const [tab, setTab] = useState<Tab>('sources');

  const tabItems: { id: Tab; label: string }[] = [
    { id: 'sources', label: t('dataIngestion.sources') },
    { id: 'models', label: t('dataIngestion.models') },
  ];

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Apple-style minimal header with integrated tabs */}
      <header className="h-[52px] px-5 bg-white border-b border-[#e2e1dd]/50 flex items-center shrink-0">
        <h1 className="text-[15px] font-medium text-[#1a1a1a] mr-8">{t('nav.data-ingestion')}</h1>
        <nav className="flex gap-0">
          {tabItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setTab(item.id)}
              className={cn(
                "px-4 py-3 text-[13px] border-b-2 transition-colors duration-150",
                tab === item.id
                  ? "font-medium border-b-[#534ab7]"
                  : "text-[#6b6b6b] hover:text-[#1a1a1a] border-b-transparent"
              )}
              style={tab === item.id ? { color: '#534ab7' } : undefined}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {tab === 'sources' ? <DataSourceManagement /> : <ModelManagement />}
      </div>
    </div>
  );
}
