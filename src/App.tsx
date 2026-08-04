import { useState } from 'react';
import { BrowserRouter } from 'react-router-dom';
import { AppProvider } from '@packages/core/lib/app-context';
import { I18nProvider, useI18n } from '@packages/core/lib/i18n';
import { AuthProvider, useAuth } from '@packages/core/lib/auth-context';
import { Toaster } from 'sonner';
// Core package — system components & pages
import { Layout } from '@packages/core/system/components/Layout';
import { DashboardView } from '@packages/core/system/components/DashboardView';
import { SystemSettingsView } from '@packages/core/system/components/SystemSettingsView';
import { MonitoringView } from '@packages/core/system/components/MonitoringView';
import { ApiExplorerView } from '@packages/core/system/components/ApiExplorerView';
import { MarkdownPreview } from '@packages/core/system/components/MarkdownPreview';
import { UserManagement } from '@packages/core/system/pages/UserManagement';
import { RoleManagement } from '@packages/core/system/pages/RoleManagement';
import { DepartmentManagement } from '@packages/core/system/pages/DepartmentManagement';
import { MenuManagement } from '@packages/core/system/pages/MenuManagement';
import { Login } from '@packages/core/system/pages/Login';
// RAG package
import { KnowledgeBaseManager } from '@packages/rag/components/KnowledgeBaseManager';
import { RetrievalTestView } from '@packages/rag/components/RetrievalTestView';
import { DataIngestionView } from '@packages/rag/components/DataIngestionView';
import { SynonymManagement } from '@packages/rag/components/SynonymManagement';
import { DesensitizationManagement } from '@packages/rag/components/DesensitizationManagement';
import { EvaluationPage } from '@packages/rag/pages/EvaluationPage';
import { DataSourceManagement } from '@packages/rag/pages/DataSourceManagement';
// Model Gateway package
import { ModelManagement } from '@packages/model-gateway/pages/ModelManagement';
import { ModelRoutingView } from '@packages/model-gateway/pages/ModelRoutingView';
import { TokenUsageAnalysis } from '@packages/model-gateway/pages/TokenUsageAnalysis';
import { QuotaManagement } from '@packages/model-gateway/pages/QuotaManagement';
// Prompt package
import { PromptTemplatesView } from '@packages/prompt/components/PromptTemplatesView';
import { PromptTemplateDetail } from '@packages/prompt/components/PromptTemplateDetail';
// Agent package
import { QAChatView } from '@packages/agent/components/QAChatView';
import { ExecutionTracingView } from '@packages/agent/components/ExecutionTracingView';
import { SkillManagement } from '@packages/agent/pages/SkillManagement';
import { AgentPlaza } from '@packages/agent/pages/AgentPlaza';
import { AgentChat } from '@packages/agent/pages/AgentChat';
import { ConversationHistory } from '@packages/agent/pages/ConversationHistory';
import { Loader2 } from 'lucide-react';

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
  const [activeTab, setActiveTab] = useState('m-12'); // 默认仪表盘
  const [selectedPromptTemplate, setSelectedPromptTemplate] = useState<string | null>(null);
  const { t } = useI18n();
  const { isAuthenticated, isLoading, logout, user, menus } = useAuth();

  // 动态菜单 ID 到前端组件的映射 (菜单 ID 来自后端)
  const MENU_COMPONENT_MAP: Record<string, string> = {
    // 系统管理
    'm-2': 'users-roles',          // 用户管理
    'm-3': 'role-management',      // 角色管理
    'm-4': 'department-management',// 部门管理
    'm-5': 'menu-management',      // 菜单管理
    'm-6': 'dashboard',            // 数据看板
    // 工作台
    'm-12': 'dashboard',       // 仪表盘
    // AI 对话
    'm-13': 'qa-chat',         // AI 助手
    'm-14': 'agent-plaza',     // 智能体广场
    'm-15': 'agent-chat',      // 智能体对话
    'm-16': 'conversation-history', // 会话历史
    // 知识库
    'm-17': 'knowledge-bases', // 知识库
    'm-18': 'data-ingestion',  // 数据摄取
    'm-19': 'retrieval-test',  // 检索测试
    // AI 资源治理
    'm-20': 'model-management', // 模型管理
    'm-21': 'skill-management', // 技能仓库
    'm-22': 'prompt-templates', // 提示词工程
    'm-23': 'synonym-management', // 同义词管理
    'm-24': 'desensitization-management', // 数据脱敏
    // 运营分析
    'm-25': 'monitoring',      // 系统监控
    'm-26': 'execution-tracing', // 执行追踪
    'm-27': 'token-usage',     // Token 使用
    'm-28': 'quota-management', // 配额管理
    'm-29': 'evaluation',      // 质量评估
    'm-30': 'api-explorer',    // API 接口
    'm-31': 'settings',        // 系统设置
  };

  const renderContent = () => {
    // 处理动态菜单 ID 映射
    const mappedTab = MENU_COMPONENT_MAP[activeTab] || activeTab;

    // 处理菜单路径点击（从 Layout 传递的 path）
    if (activeTab?.startsWith?.('/')) {
      // 如果是后端菜单路径，查找对应的映射
      const menuIdMatch = activeTab.match(/m-(\d+)/);
      if (menuIdMatch) {
        const menuId = `m-${menuIdMatch[1]}`;
        const componentId = MENU_COMPONENT_MAP[menuId] || 'dashboard';
        return renderComponent(componentId);
      }
    }

    // Prompt Engineering views
    if (mappedTab === 'prompt-templates') {
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

    switch (mappedTab) {
      case 'dashboard':
        return <DashboardView onNavigate={setActiveTab} />;
      case 'qa-chat':
        return <QAChatView />;
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
      case 'role-management':
        return <RoleManagement />;
      case 'department-management':
        return <DepartmentManagement />;
      case 'menu-management':
        return <MenuManagement />;
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
      case 'conversation-history':
        return <ConversationHistory />;
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
      menus={menus}
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
