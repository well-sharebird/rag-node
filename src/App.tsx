import { useState } from 'react';
import { AppProvider } from '@/lib/app-context';
import { I18nProvider, useI18n } from '@/src/lib/i18n';
import { AuthProvider, useAuth } from '@/src/lib/auth-context';
import { Toaster } from 'sonner';
import { Layout } from './components/Layout';
import { DashboardViewBird } from './components/DashboardView.bird';
import { KnowledgeBaseManagerBird } from './components/KnowledgeBaseManager.bird';
import { RetrievalTestViewBird } from './components/RetrievalTestView.bird';
import { SystemSettingsViewBird } from './components/SystemSettingsView.bird';
import { QAChatView } from './components/QAChatView';
import { MonitoringView } from './components/MonitoringView';
import { ApiExplorerView } from './components/ApiExplorerView';
import { DataIngestionView } from './components/DataIngestionView';
import { SkillManagementBird } from './pages/SkillManagement.bird';
import { ModelManagementBird } from './pages/ModelManagement.bird';
import { UserManagementBird } from './pages/UserManagement.bird';
import { EvaluationPageBird } from './pages/EvaluationPage.bird';
import { TokenUsageAnalysisBird } from './pages/TokenUsageAnalysis.bird';
import { QuotaManagementBird } from './pages/QuotaManagement.bird';
import { DataSourceManagementBird } from './pages/DataSourceManagement.bird';
import { Login } from './pages/Login';
import { Loader2 } from 'lucide-react';
import { PromptTemplatesViewBird } from './components/PromptTemplatesView.bird';
import { PromptTemplateDetailBird } from './components/PromptTemplateDetail.bird';
import { MarkdownPreview } from './components/MarkdownPreview';

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
  const [selectedPromptTemplate, setSelectedPromptTemplate] = useState<string | null>(null);
  const { t } = useI18n();
  const { isAuthenticated, isLoading, logout, user } = useAuth();

  const renderContent = () => {
    // Prompt Engineering views
    if (activeTab === 'prompt-templates') {
      if (selectedPromptTemplate) {
        return (
          <PromptTemplateDetailBird
            templateName={selectedPromptTemplate}
            onBack={() => setSelectedPromptTemplate(null)}
          />
        );
      }
      return (
        <PromptTemplatesViewBird
          onNavigateToDetail={(name) => {
            setSelectedPromptTemplate(name);
          }}
        />
      );
    }

    switch (activeTab) {
      case 'dashboard':
        return <DashboardViewBird onNavigate={setActiveTab} />;
      case 'qa-chat':
        return <QAChatView />; // QAChatView 已有 MarkdownRenderer 支持 Bird 风格
      case 'knowledge-bases':
        return <KnowledgeBaseManagerBird />;
      case 'retrieval-test':
        return <RetrievalTestViewBird />;
      case 'api-explorer':
        return <ApiExplorerView />;
      case 'monitoring':
        return <MonitoringView />;
      case 'settings':
        return <SystemSettingsViewBird />;
      case 'data-ingestion':
      case 'data-sources':
        return <DataIngestionView />;
      case 'skill-management':
        return <SkillManagementBird />;
      case 'model-management':
      case 'model-management-page':
        return <ModelManagementBird />;
      case 'users-roles':
        return <UserManagementBird />;
      case 'evaluation':
        return <EvaluationPageBird />;
      case 'token-usage':
        return <TokenUsageAnalysisBird />;
      case 'quota-management':
        return <QuotaManagementBird />;
      case 'data-sources':
        return <DataSourceManagementBird />;
      case 'markdown-preview':
        return <MarkdownPreview />;
      default:
        return <DashboardViewBird onNavigate={setActiveTab} />;
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
