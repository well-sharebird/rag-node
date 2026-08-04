import { useI18n } from '@/src/lib/i18n';
import { DataSourceManagement } from '@/src/pages/DataSourceManagement';

export function DataIngestionView() {
  const { t } = useI18n();

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="h-[52px] px-5 bg-white border-b border-[#e2e1dd]/50 flex items-center shrink-0">
        <h1 className="text-[15px] font-medium text-[var(--text-primary)]">{t('nav.data-ingestion')}</h1>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        <DataSourceManagement />
      </div>
    </div>
  );
}
