import { useState } from 'react';
import { AppProvider } from '@/lib/app-context';
import { I18nProvider, useI18n } from '@/src/lib/i18n';
import { AuthProvider, useAuth } from '@/src/lib/auth-context';
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
import { DataIngestionView } from './components/DataIngestionView';
import { SkillManagement } from './pages/SkillManagement';
import { ModelManagement } from './pages/ModelManagement';
import { UserManagement } from './pages/UserManagement';
import { EvaluationPage } from './pages/EvaluationPage';
import { TokenUsageAnalysis } from './pages/TokenUsageAnalysis';
import { QuotaManagement } from './pages/QuotaManagement';
import { Login } from './pages/Login';
import { Loader2 } from 'lucide-react';

function PlaceholderView({ title, description }: { title: string, description: string }) {
  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <header className="h-[52px] px-5 bg-white flex items-center shrink-0" style={{ borderBottom: '0.5px solid #e2e1dd' }}>
        <h1 className="text-[15px] font-medium text-[#1a1a1a]">{title}</h1>
      </header>
      <div className="flex-1 flex flex-col items-center justify-center text-center p-10 bg-[#f7f7f5]">
        <div className="w-14 h-14 rounded-full flex items-center justify-center mb-5" style={{ background: '#eeedfe' }}>
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: '#534ab7' }}>
            <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
          </svg>
        </div>
        <h2 className="text-base font-medium text-[#1a1a1a] mb-2">{title}</h2>
        <p className="text-[#6b6b6b] text-[13px] max-w-sm">{description}</p>
      </div>
    </div>
  );
}

function MainAppContent() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const { t } = useI18n();
  const { isAuthenticated, isLoading, logout, user } = useAuth();

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <DashboardView onNavigate={setActiveTab} />;
      case 'qa-chat':
        return <QAChatView />;
      case 'knowledge-bases':
        return <KnowledgeBasesView />;
      case 'documents':
        return <DocumentsView />;
      case 'retrieval-test':
        return <RetrievalTestView />;
      case 'api-explorer':
        return <ApiExplorerView />;
      case 'monitoring':
        return <MonitoringView />;
      case 'settings':
        return <SystemSettingsView />;
      case 'data-ingestion':
      case 'data-sources':
        return <DataIngestionView />;
      case 'skill-management':
        return <SkillManagement />;
      case 'model-management':
      case 'model-management-page':
        return <ModelManagement />;
      case 'users-roles':
        return <UserManagement />;
      case 'evaluation':
        return <EvaluationPage />;
      case 'token-usage':
        return <TokenUsageAnalysis />;
      case 'quota-management':
        return <QuotaManagement />;
      default:
        return <DashboardView onNavigate={setActiveTab} />;
    }
  };

  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Login />;
  }

  return (
    <Layout
      activeTab={activeTab}
      setActiveTab={setActiveTab}
      currentUser={user}
      onLogout={logout}
    >
      {renderContent()}
    </Layout>
  );
}

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <AppProvider>
          <MainAppContent />
          <Toaster position="top-right" richColors closeButton />
        </AppProvider>
      </AuthProvider>
    </I18nProvider>
  );
}
