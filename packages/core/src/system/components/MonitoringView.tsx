import { useEffect, useState } from 'react';
import { fetchDashboard, DashboardData } from '@/lib/api-client';
import { useI18n } from '@/src/lib/i18n';
import { Activity, Server, HardDrive, Cpu } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardBody } from '@/src/components/enterprise';

export function MonitoringView() {
  const { t } = useI18n();
  const [stats, setStats] = useState<DashboardData | null>(null);
  useEffect(() => { fetchDashboard().then(setStats).catch(() => {}); }, []);

  const services = [
    { name: 'Vector DB (Milvus)', status: stats?.services?.milvus ?? 'unknown', icon: HardDrive },
    { name: 'PostgreSQL', status: stats?.services?.postgres ?? 'unknown', icon: Server },
    { name: 'Redis Cache', status: stats?.services?.redis ?? 'unknown', icon: Cpu },
  ];

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <header className="h-[60px] px-6 bg-white flex items-center shrink-0 border-b border-[var(--gray-200)]">
        <div className="flex items-baseline gap-3">
          <h1 className="text-base font-medium text-[var(--text-primary)]">{t('monitoring.title')}</h1>
          <span className="text-xs text-[var(--text-tertiary)] hidden sm:inline">{t('monitoring.desc')}</span>
        </div>
      </header>
      <div className="flex-1 overflow-y-auto p-5 bg-white">
        <div className="max-w-4xl mx-auto space-y-8">
          <div className="grid grid-cols-3 gap-6">
            {services.map(svc => {
              const isHealthy = svc.status === 'healthy' || svc.status === 'ok';
              return (
                <Card key={svc.name}>
                  <CardBody>
                    <div className="flex items-center gap-3 mb-4">
                      <svc.icon className="w-5 h-5 text-[var(--text-tertiary)]" />
                      <span className="text-sm font-semibold text-[var(--text-primary)]">{svc.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className={`w-2.5 h-2.5 rounded-full ${isHealthy ? 'bg-emerald-500' : 'bg-red-500'}`} />
                      <span className={`text-sm font-bold ${isHealthy ? 'text-emerald-600' : 'text-red-600'}`}>{isHealthy ? t('monitoring.healthy') : svc.status}</span>
                    </div>
                  </CardBody>
                </Card>
              );
            })}
          </div>
          <Card>
            <CardBody className="text-center py-8">
              <Activity className="w-12 h-12 text-[var(--gray-200)] mx-auto mb-4" />
              <h3 className="text-lg font-bold text-[var(--text-primary)] mb-2">{t('monitoring.metrics.title')}</h3>
              <p className="text-sm text-[var(--text-secondary)]">{t('monitoring.metrics.desc')}</p>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
