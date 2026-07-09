import { useEffect, useState } from 'react';
import { fetchDashboard, DashboardData } from '@/lib/api-client';
import { useI18n } from '@/src/lib/i18n';
import { Activity, Server, HardDrive, Cpu } from 'lucide-react';

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
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#F8FAFC]">
      <header className="h-20 px-8 bg-white/80 backdrop-blur-md border-b border-slate-200/60 flex items-center shrink-0">
        <div>
          <h1 className="text-xl font-bold text-slate-900">{t('monitoring.title')}</h1>
          <p className="text-[13px] text-slate-500">{t('monitoring.desc')}</p>
        </div>
      </header>
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto space-y-8">
          <div className="grid grid-cols-3 gap-6">
            {services.map(svc => {
              const isHealthy = svc.status === 'healthy' || svc.status === 'ok';
              return (
                <div key={svc.name} className="bg-white border border-slate-200/60 rounded-2xl p-6">
                  <div className="flex items-center gap-3 mb-4">
                    <svc.icon className="w-5 h-5 text-slate-400" />
                    <span className="text-sm font-semibold text-slate-700">{svc.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className={`w-2.5 h-2.5 rounded-full ${isHealthy ? 'bg-emerald-500' : 'bg-red-500'}`} />
                    <span className={`text-sm font-bold ${isHealthy ? 'text-emerald-600' : 'text-red-600'}`}>{isHealthy ? t('monitoring.healthy') : svc.status}</span>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="bg-white border border-slate-200/60 rounded-3xl p-8 text-center">
            <Activity className="w-12 h-12 text-slate-200 mx-auto mb-4" />
            <h3 className="text-lg font-bold text-slate-900 mb-2">{t('monitoring.metrics.title')}</h3>
            <p className="text-sm text-slate-500">{t('monitoring.metrics.desc')}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
