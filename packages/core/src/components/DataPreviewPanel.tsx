/**
 * 数据预览通用组件
 * 支持 JSON、文本、表格、图片等多种格式预览
 */
import { useState } from 'react';
import { cn } from '@/lib/utils';
import { FileText, Table, Image, Code, ChevronDown, ChevronRight, Copy, Check } from 'lucide-react';

export interface DataPreviewPanelProps {
  data: unknown;
  title?: string;
  maxHeight?: string;
  className?: string;
}

export function DataPreviewPanel({ data, title, maxHeight = "300px", className }: DataPreviewPanelProps) {
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(true);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(data, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      console.error('Failed to copy:', e);
    }
  };

  const getDataType = () => {
    if (typeof data === 'string') return 'text';
    if (Array.isArray(data)) return 'array';
    if (typeof data === 'object' && data !== null) return 'json';
    return 'unknown';
  };

  const dataType = getDataType();

  const getDataTypeIcon = () => {
    switch (dataType) {
      case 'text':
        return <FileText className="w-4 h-4" />;
      case 'array':
        return <Table className="w-4 h-4" />;
      case 'json':
        return <Code className="w-4 h-4" />;
      default:
        return <FileText className="w-4 h-4" />;
    }
  };

  const renderContent = () => {
    if (typeof data === 'string') {
      // 判断是否是图片等二进制数据的预览
      if (data.startsWith('25 50 44 46') || data.includes('PDF')) {
        return (
          <div className="flex items-center gap-2 text-gray-500">
            <Image className="w-5 h-5" />
            <span>二进制数据预览 (PDF 文件头)</span>
          </div>
        );
      }
      return (
        <pre className="text-sm text-gray-700 whitespace-pre-wrap font-mono">
          {data.length > 2000 ? data.slice(0, 2000) + '... (已截断)' : data}
        </pre>
      );
    }

    if (Array.isArray(data)) {
      return (
        <div className="text-sm">
          <div className="text-gray-500 mb-2">数组 ({data.length} 项)</div>
          <div className="space-y-1">
            {data.slice(0, 10).map((item, idx) => (
              <div key={idx} className="flex items-start gap-2">
                <span className="text-gray-400 w-6">{idx}.</span>
                <span className="text-gray-700">
                  {typeof item === 'object' ? JSON.stringify(item, null, 2).slice(0, 100) : String(item)}
                  {typeof item === 'object' && JSON.stringify(item).length > 100 ? '...' : ''}
                </span>
              </div>
            ))}
            {data.length > 10 && (
              <div className="text-gray-400 text-center py-2">... 还有 {data.length - 10} 项</div>
            )}
          </div>
        </div>
      );
    }

    if (typeof data === 'object' && data !== null) {
      return (
        <div className="text-sm">
          <pre className="text-gray-700 whitespace-pre-wrap font-mono bg-gray-50 p-3 rounded overflow-auto" style={{ maxHeight }}>
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      );
    }

    return (
      <div className="text-sm text-gray-500">
        无法预览此数据类型
      </div>
    );
  };

  return (
    <div className={cn("border border-gray-200 rounded-lg bg-white overflow-hidden", className)}>
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 bg-gray-50 border-b border-gray-200 cursor-pointer hover:bg-gray-100"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-gray-500" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-500" />
          )}
          <div className="flex items-center gap-2">
            {getDataTypeIcon()}
            <span className="text-sm font-medium text-gray-700">
              {title || (dataType === 'json' ? 'JSON 数据' : dataType === 'text' ? '文本内容' : '数组数据')}
            </span>
          </div>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation();
            handleCopy();
          }}
          className="p-1 hover:bg-white rounded transition-colors"
          title="复制"
        >
          {copied ? (
            <Check className="w-4 h-4 text-green-600" />
          ) : (
            <Copy className="w-4 h-4 text-gray-500" />
          )}
        </button>
      </div>

      {/* Content */}
      {expanded && (
        <div className="p-3 overflow-auto" style={{ maxHeight }}>
          {renderContent()}
        </div>
      )}
    </div>
  );
}
