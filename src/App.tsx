import { useState } from 'react';
import { BrowserRouter } from 'react-router-dom';
import { AppProvider } from '@/lib/app-context';
import { I18nProvider, useI18n } from '@/src/lib/i18n';
import { AuthProvider, useAuth } from '@/src/lib/auth-context';
import { Toaster } from 'sonner';
import { Layout } from './components/Layout';
import { DashboardView } from './components/DashboardView';
import { KnowledgeBaseManager } from './components/KnowledgeBaseManager';
import { RetrievalTestView } from './components/RetrievalTestView';
import { SystemSettingsView } from './components/SystemSettingsView';
import { QAChatView } from './components/QAChatView';
import { MonitoringView } from './components/MonitoringView';
import { ApiExplorerView } from './components/ApiExplorerView';
import { DataIngestionView } from './components/DataIngestionView';
import { SkillManagement } from './pages/SkillManagement';
import { ModelManagement } from './pages/ModelManagement';
import { ModelRoutingView } from './pages/ModelRoutingView';
import { UserManagement } from './pages/UserManagement';
import { EvaluationPage } from './pages/EvaluationPage';
import { TokenUsageAnalysis } from './pages/TokenUsageAnalysis';
import { QuotaManagement } from './pages/QuotaManagement';
import { DataSourceManagement } from './pages/DataSourceManagement';
import { Login } from './pages/Login';
import { Loader2 } from 'lucide-react';
import { PromptTemplatesView } from './components/PromptTemplatesView';
import { PromptTemplateDetail } from './components/PromptTemplateDetail';
import { MarkdownPreview } from './components/MarkdownPreview';
import { AgentPlaza } from './pages/AgentPlaza';
import { AgentChat } from './pages/AgentChat';
import { SynonymManagement } from './components/SynonymManagement';
import { DesensitizationManagement } from './components/DesensitizationManagement';
import { ExecutionTracingView } from './components/ExecutionTracingView';

function PlaceholderView({ title, description }: { title: string, description: string }) {
  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <header className="h-[52px] px-5 bg-white flex items-center shrink-0" style={{ borderBottom: '0.5px solid var(--gray-200)' }}>
        <h1 className="text-[15px] font-medium text-[var(--text-primary)]">{title}</h1>
      </header>
      <div className="flex-1 flex flex-col items-center justify-center text-center p-10 bg-white">
        <div className="w-14 h-14 rounded-full flex items-center justify-center mb-5" style={{ background: 'var(--accent-light)' }}>
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--accent)' }}>
            <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
          </svg>
        </div>
        <h2 className="text-base font-medium text-[var(--text-primary)] mb-2">{title}</h2>
        <p className="text-[var(--text-secondary)] text-[13px] max-w-sm">{description}</p>
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
          <PromptTemplateDetail
            templateName={selectedPromptTemplate}
            onBack={() => setSelectedPromptTemplate(null)}
          />
        );
      }
      return (
        <PromptTemplatesView
          onNavigateToDetail={(name) => {
            setSelectedPromptTemplate(name);
          }}
        />
      );
    }

    switch (activeTab) {
      case 'dashboard':
        return <DashboardView onNavigate={setActiveTab} />;
      case 'qa-chat':
        return <QAChatView />; // QAChatView 已有 MarkdownRenderer 支持 Bird 风格
      case 'agent-plaza':
        return <AgentPlaza onNavigate={(tab, agentId) => {
          if (tab === 'agent-chat') {
            setActiveTab(tab);
          }
        }} />;
      case 'agent-chat':
        return <AgentChat />;
      case 'knowledge-bases':
        return <KnowledgeBaseManager />;
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
      case 'model-routing':
        return <ModelRoutingView />;
      case 'users-roles':
        return <UserManagement />;
      case 'evaluation':
        return <EvaluationPage />;
      case 'token-usage':
        return <TokenUsageAnalysis />;
      case 'quota-management':
        return <QuotaManagement />;
      case 'data-sources':
        return <DataSourceManagement />;
      case 'markdown-preview':
        return <MarkdownPreview />;
      case 'synonym-management':
        return <SynonymManagement />;
      case 'desensitization-management':
        return <DesensitizationManagement />;
      case 'execution-tracing':
        return <ExecutionTracingView />;
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
    <BrowserRouter>
      <I18nProvider>
        <AuthProvider>
          <AppProvider>
            <MainAppContent />
            <Toaster position="top-right" richColors closeButton />
          </AppProvider>
        </AuthProvider>
      </I18nProvider>
    </BrowserRouter>
  );
}
