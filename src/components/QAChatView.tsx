import { useState } from 'react';
import { useAppContext } from '@/lib/app-context';
import { useI18n } from '@/src/lib/i18n';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Send, Bot, User, BookOpen } from 'lucide-react';

export function QAChatView() {
  const { knowledgeBases } = useAppContext();
  const { t } = useI18n();
  const [selectedKb, setSelectedKb] = useState('');
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant'; content: string; sources?: string[] }[]>([]);
  const [input, setInput] = useState('');

  const handleSend = () => {
    if (!input.trim()) return;
    setMessages(prev => [...prev, { role: 'user', content: input }]);
    setInput('');

    setTimeout(() => {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: t('qa.comingSoon'),
        sources: [t('qa.sourcePreview')]
      }]);
    }, 500);
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#F8FAFC]">
      <header className="h-20 px-8 bg-white/80 backdrop-blur-md border-b border-slate-200/60 flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-xl font-bold text-slate-900">{t('qa.title')}</h1>
          <p className="text-[13px] text-slate-500">{t('qa.desc')}</p>
        </div>
        <Select value={selectedKb} onValueChange={(v) => setSelectedKb(v)}>
          <SelectTrigger className="w-[220px] rounded-xl border-slate-200 h-10">
            <SelectValue placeholder={t('qa.selectKb')} />
          </SelectTrigger>
          <SelectContent className="rounded-xl">
            {knowledgeBases.map(kb => (
              <SelectItem key={kb.id} value={kb.id} className="rounded-lg">{kb.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </header>

      <div className="flex-1 overflow-y-auto p-6">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-3">
            <Bot className="w-12 h-12 text-slate-200" />
            <p className="font-medium text-slate-500">{t('qa.empty.title')}</p>
            <p className="text-sm">{t('qa.empty.desc')}</p>
          </div>
        )}
        <div className="max-w-3xl mx-auto space-y-4">
          {messages.map((msg, i) => (
            <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
              {msg.role === 'assistant' && <div className="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center shrink-0 mt-1"><Bot className="w-4 h-4 text-indigo-600" /></div>}
              <div className={`max-w-[80%] rounded-2xl px-5 py-3 ${msg.role === 'user' ? 'bg-[#1677ff] text-white rounded-tr-sm' : 'bg-white border border-slate-200/60 shadow-sm'}`}>
                <p className="text-[15px] leading-relaxed">{msg.content}</p>
                {msg.sources && (
                  <div className="mt-3 pt-3 border-t border-slate-100">
                    {msg.sources.map((s, j) => (
                      <div key={j} className="flex items-center gap-1.5 text-xs text-slate-500 mt-1">
                        <BookOpen className="w-3 h-3" /> {s}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              {msg.role === 'user' && <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center shrink-0 mt-1"><User className="w-4 h-4 text-blue-600" /></div>}
            </div>
          ))}
        </div>
      </div>

      <div className="p-4 bg-white/80 border-t border-slate-200/60">
        <div className="max-w-3xl mx-auto flex gap-3">
          <Input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSend()}
            placeholder={t('qa.placeholder')} className="rounded-xl h-12 bg-white border-slate-200" />
          <Button onClick={handleSend} className="bg-[#1677ff] hover:bg-[#0958d9] rounded-xl h-12 w-12 shrink-0"><Send className="w-4.5 h-4.5" /></Button>
        </div>
      </div>
    </div>
  );
}
