import { useI18n } from '@/src/lib/i18n';
import { DataSourceManagementBird } from '@/src/pages/DataSourceManagement.bird';

export function DataIngestionView() {
  const { t } = useI18n();

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="h-[52px] px-5 bg-white border-b border-[#e2e1dd]/50 flex items-center shrink-0">
        <h1 className="text-[15px] font-medium text-[#1a1a1a]">{t('nav.data-ingestion')}</h1>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        <DataSourceManagementBird />
      </div>
    </div>
  );
}
