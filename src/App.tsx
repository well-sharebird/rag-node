import { useState } from 'react';
import { AppProvider } from '@/lib/app-context';
import { I18nProvider, useI18n } from '@/src/lib/i18n';
import { Toaster } from 'sonner';
import { Layout } from './components/Layout';
import { DashboardView } from './components/DashboardView';
import { KnowledgeBasesView } from './components/KnowledgeBasesView';
import { DocumentsView } from './components/DocumentsView';
import { RetrievalTestView } from './components/RetrievalTestView';
import { SystemSettingsView } from './components/SystemSettingsView';
import { QAChatView } from './components/QAChatView';
import { MonitoringView } from './components/MonitoringView';
import { ApiExplorerView } from './components/ApiExplorerView';
import { ModelManagement } from './pages/ModelManagement';
import { DataSourceManagement } from './pages/DataSourceManagement';

function PlaceholderView({ title, descriptionKey }: { title: string, descriptionKey: string }) {
  const { t } = useI18n();
  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-slate-50">
      <header className="h-24 px-10 border-b border-slate-200 bg-white flex items-center shrink-0 shadow-sm">
        <h1 className="text-xl font-bold text-slate-900">{title}</h1>
      </header>
      <div className="flex-1 flex flex-col items-center justify-center p-10 text-center">
        <div className="w-16 h-16 bg-white border border-slate-200 rounded-sm mb-6 flex items-center justify-center text-slate-400 shadow-sm">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>
        </div>
        <h2 className="text-xl font-bold text-slate-900 mb-2">{title}</h2>
        <p className="text-slate-500 text-sm max-w-md">{t(descriptionKey)}</p>
      </div>
    </div>
  );
}

function MainApp() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const { t } = useI18n();

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <DashboardView onNavigate={setActiveTab} />;
      case 'knowledge-bases':
        return <KnowledgeBasesView />;
      case 'documents':
        return <DocumentsView />;
      case 'data-sources':
        return <DataSourceManagement />;
      case 'retrieval-test':
        return <RetrievalTestView />;
      case 'qa-chat':
        return <QAChatView />;
      case 'api-explorer':
        return <ApiExplorerView />;
      case 'monitoring':
        return <MonitoringView />;
      case 'settings':
        return <SystemSettingsView />;
      case 'model-management':
      case 'model-management-page':
        return <ModelManagement />;
      case 'knowledge-graph':
        return <PlaceholderView title="Knowledge Graph" descriptionKey="apiExplorer.desc" />;
      default:
        return <DashboardView onNavigate={setActiveTab} />;
    }
  };

  return (
    <Layout activeTab={activeTab} setActiveTab={setActiveTab}>
      {renderContent()}
    </Layout>
  );
}

export default function App() {
  return (
    <I18nProvider>
      <AppProvider>
        <MainApp />
        <Toaster position="top-right" richColors closeButton />
      </AppProvider>
    </I18nProvider>
  );
}
