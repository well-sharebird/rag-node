import { Code, Key, BarChart3, Copy, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useState } from 'react';
import { useI18n } from '@/src/lib/i18n';

const sampleSnippet = `curl -X POST http://localhost:8000/api/v1/retrieval/search \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -d '{"kb_id": "kb_xxx", "query": "your question", "top_k": 5}'`;

export function ApiExplorerView() {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <header className="h-[52px] px-5 bg-white flex items-center shrink-0" style={{ borderBottom: '0.5px solid #e2e1dd' }}>
        <div className="flex items-baseline gap-3">
          <h1 className="text-[15px] font-medium text-[#1a1a1a]">{t('api.title')}</h1>
          <span className="text-[11px] text-[#9b9b9b] hidden sm:inline">{t('api.desc')}</span>
        </div>
      </header>
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl mx-auto space-y-8">
          <div className="grid grid-cols-3 gap-6">
            <div className="bg-white border border-slate-200/60 rounded-2xl p-6 hover:shadow-md transition-shadow cursor-pointer">
              <Code className="w-8 h-8 text-indigo-500 mb-3" />
              <h3 className="font-bold text-slate-900 mb-1">{t('api.docs')}</h3>
              <p className="text-xs text-slate-500">{t('api.docs.desc')}</p>
            </div>
            <div className="bg-white border border-slate-200/60 rounded-2xl p-6 hover:shadow-md transition-shadow cursor-pointer">
              <Key className="w-8 h-8 text-amber-500 mb-3" />
              <h3 className="font-bold text-slate-900 mb-1">{t('api.keys')}</h3>
              <p className="text-xs text-slate-500">{t('api.keys.desc')}</p>
            </div>
            <div className="bg-white border border-slate-200/60 rounded-2xl p-6 hover:shadow-md transition-shadow cursor-pointer">
              <BarChart3 className="w-8 h-8 text-emerald-500 mb-3" />
              <h3 className="font-bold text-slate-900 mb-1">{t('api.usage')}</h3>
              <p className="text-xs text-slate-500">{t('api.usage.desc')}</p>
            </div>
          </div>
          <div className="bg-slate-900 rounded-2xl p-6 overflow-x-auto">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-slate-400 font-mono">{t('api.quickStart')}</span>
              <Button variant="ghost" size="sm" className="text-slate-400 hover:text-white text-xs" onClick={() => { navigator.clipboard.writeText(sampleSnippet); setCopied(true); setTimeout(() => setCopied(false), 2000); }}>
                {copied ? <Check className="w-3.5 h-3.5 mr-1" /> : <Copy className="w-3.5 h-3.5 mr-1" />}
                {copied ? t('api.copied') : t('api.copy')}
              </Button>
            </div>
            <pre className="text-sm text-emerald-400 font-mono whitespace-pre-wrap">{sampleSnippet}</pre>
          </div>
        </div>
      </div>
    </div>
  );
}
