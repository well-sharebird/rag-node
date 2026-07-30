import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeRaw from 'rehype-raw';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import mermaid from 'mermaid';
import { Check, Copy, ChevronRight, ChevronDown, Info, AlertTriangle, AlertCircle, CheckCircle, Lightbulb } from 'lucide-react';
import 'katex/dist/katex.min.css';

interface MarkdownRendererProps {
  content: string;
}

// ============== Admonition Types ==============
type AdmonitionType = 'note' | 'tip' | 'warning' | 'danger' | 'info';

interface AdmonitionProps {
  type: AdmonitionType;
  title?: string;
  children: React.ReactNode;
}

const ADMONITION_STYLES: Record<AdmonitionType, { bg: string; border: string; icon: React.ReactNode; title: string }> = {
  note: {
    bg: 'bg-blue-50',
    border: 'border-blue-500',
    icon: <Info className="w-4 h-4 text-blue-600" />,
    title: 'Note',
  },
  tip: {
    bg: 'bg-green-50',
    border: 'border-green-500',
    icon: <Lightbulb className="w-4 h-4 text-green-600" />,
    title: 'Tip',
  },
  warning: {
    bg: 'bg-yellow-50',
    border: 'border-yellow-500',
    icon: <AlertTriangle className="w-4 h-4 text-yellow-600" />,
    title: 'Warning',
  },
  danger: {
    bg: 'bg-red-50',
    border: 'border-red-500',
    icon: <AlertCircle className="w-4 h-4 text-red-600" />,
    title: 'Danger',
  },
  info: {
    bg: 'bg-blue-50',
    border: 'border-blue-500',
    icon: <Info className="w-4 h-4 text-blue-600" />,
    title: 'Info',
  },
};

function Admonition({ type, title, children }: AdmonitionProps) {
  const style = ADMONITION_STYLES[type] || ADMONITION_STYLES.note;

  return (
    <div className={`my-4 rounded-lg border-l-4 ${style.bg} overflow-hidden`}>
      <div className={`flex items-center gap-2 px-4 py-3 ${style.border} border-l-4`}>
        {style.icon}
        <span className="font-semibold text-sm text-gray-800">{title || style.title}</span>
      </div>
      <div className="px-4 py-3 text-sm text-gray-700">
        {children}
      </div>
    </div>
  );
}

// ============== JSON Tree View ==============
interface JsonTreeViewProps {
  code: string;
}

function JsonTreeView({ code }: JsonTreeViewProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['root']));

  let jsonData: any;
  try {
    jsonData = typeof code === 'string' ? JSON.parse(code) : code;
  } catch {
    return (
      <div className="my-3 p-4 bg-red-50 rounded-lg border border-red-200">
        <p className="text-sm text-red-600">Invalid JSON</p>
      </div>
    );
  }

  const toggleNode = (path: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  const renderValue = (value: any, path: string, key?: string): React.ReactNode => {
    const isExpanded = expanded.has(path);
    const isObject = value !== null && typeof value === 'object';
    const isArray = Array.isArray(value);
    const isEmpty = isObject && Object.keys(value).length === 0;

    if (!isObject) {
      // Primitive value
      return (
        <div className="flex items-center">
          {key !== undefined && (
            <span className="text-var(--accent) mr-1">"{key}":</span>
          )}
          <span className={
            typeof value === 'string' ? 'text-green-600' :
            typeof value === 'number' ? 'text-orange-600' :
            'text-blue-600'
          }>
            {typeof value === 'string' ? `"${value}"` : String(value)}
          </span>
        </div>
      );
    }

    // Object or Array
    const entries = isArray
      ? value.map((v, i) => [String(i), v] as [string, any])
      : Object.entries(value);

    return (
      <div>
        <div
          className="flex items-center gap-1 cursor-pointer hover:bg-gray-100 rounded px-1 -ml-1"
          onClick={() => toggleNode(path)}
        >
          {isEmpty ? (
            <span className="w-4 h-4" />
          ) : isExpanded ? (
            <ChevronDown className="w-4 h-4 text-gray-500" />
          ) : (
            <ChevronRight className="w-4 h-4 text-gray-500" />
          )}
          {key !== undefined && (
            <span className="text-var(--accent)">"{key}":</span>
          )}
          <span className="text-gray-600">
            {isArray ? `Array[${value.length}]` : `Object{${Object.keys(value).length}}`}
          </span>
        </div>
        {isExpanded && !isEmpty && (
          <div className="ml-4 border-l border-gray-200 pl-2">
            {entries.map(([k, v]) => renderValue(v, `${path}.${k}`, k))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="my-3 p-4 bg-gray-50 rounded-lg border border-gray-200 overflow-auto max-h-96">
      <div className="font-mono text-sm">
        {renderValue(jsonData, 'root')}
      </div>
    </div>
  );
}

// ============== Code Block ==============
function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Check if it's a mermaid diagram (including mindmap, gantt, etc.)
  if (language === 'mermaid' || language === 'mindmap' || language === 'gantt' || language === 'journey') {
    return <MermaidDiagram code={code} type={language} />;
  }

  // Check if it's JSON and should use tree view
  if (language === 'json-tree') {
    return <JsonTreeView code={code} />;
  }

  return (
    <div className="relative group my-3 rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 text-gray-300 text-xs">
        <span className="font-mono">{language || 'code'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-700 transition-colors"
          title={copied ? 'Copied!' : 'Copy code'}
        >
          {copied ? (
            <Check className="w-3.5 h-3.5" />
          ) : (
            <Copy className="w-3.5 h-3.5" />
          )}
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        customStyle={{
          margin: 0,
          borderRadius: 0,
          fontSize: '13px',
          lineHeight: '1.5',
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

// ============== Mermaid Diagram ==============
function MermaidDiagram({ code, type = 'mermaid' }: { code: string; type?: string }) {
  const [svg, setSvg] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const renderMermaid = async () => {
      try {
        mermaid.initialize({
          startOnLoad: false,
          theme: 'default',
          securityLevel: 'loose',
          fontFamily: 'inherit',
        });

        // Clean the code for rendering - normalize whitespace and fix common issues
        let cleanCode = code.trim();

        // Fix: Replace newlines in node labels with spaces to avoid parse errors
        // e.g., "A[原始文档\n1]" -> "A[原始文档 1]"
        cleanCode = cleanCode.replace(/\[([^\]]*)\n([^\]]*)\]/g, '[$1 $2]');

        // Ensure proper line breaks in graph definitions
        cleanCode = cleanCode.replace(/graph\s*(TD|LR|BT|RL)\s*/g, 'graph $1\n');

        // First, parse the code to check for syntax errors (mermaid v10+ API)
        try {
          await mermaid.parse(cleanCode);
        } catch (parseErr) {
          console.warn('Mermaid syntax error, skipping render:', cleanCode.substring(0, 200));
          if (mounted) setSvg(null);
          return;
        }

        // Create a temporary container for rendering - off-screen
        const tempId = `mermaid-temp-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const tempContainer = document.createElement('div');
        tempContainer.id = tempId;
        tempContainer.style.cssText = 'position:absolute;left:-9999px;top:-9999px;visibility:hidden;';
        document.body.appendChild(tempContainer);

        // Track nodes added by mermaid to clean up later
        const nodesToAdd = new Set<Node>();
        const observer = new MutationObserver((mutations) => {
          mutations.forEach((m) => {
            m.addedNodes.forEach((node) => {
              if (node.nodeName === 'DIV' && (node as Element).id?.startsWith('mermaid-')) {
                nodesToAdd.add(node);
              }
            });
          });
        });

        observer.observe(document.body, { childList: true, subtree: true });

        try {
          // Render into temp container (mermaid v11 renders to DOM by default)
          const { svg } = await mermaid.render(tempId, cleanCode, tempContainer);

          if (mounted) {
            // Check if the rendered SVG contains error markers
            const hasError = svg.includes('error-icon') ||
                            svg.includes('Syntax error') ||
                            svg.includes('error-diagram') ||
                            svg.includes('mermaid-error');

            if (hasError) {
              console.warn('Mermaid rendered an error SVG, discarding');
              setSvg(null);
            } else {
              setSvg(svg);
            }
          }
        } finally {
          // Clean up: remove temp container and any mermaid-added nodes
          observer.disconnect();
          const existingTemp = document.getElementById(tempId);
          if (existingTemp) {
            existingTemp.remove();
          }
          // Remove any stray mermaid nodes that might have been added to body
          nodesToAdd.forEach((node) => {
            if (node.parentNode) {
              node.parentNode.removeChild(node);
            }
          });
        }
      } catch (err) {
        console.error('Mermaid error:', err);
        if (mounted) {
          setSvg(null);
        }
      }
    };

    renderMermaid();

    return () => {
      mounted = false;
    };
  }, [code, type]);

  // 没有成功渲染出 SVG 时，不显示任何内容
  if (!svg) {
    return null;
  }

  return (
    <div className="my-4 flex justify-center">
      <div dangerouslySetInnerHTML={{ __html: svg }} style={{ maxWidth: '100%' }} />
    </div>
  );
}

// ============== Custom Admonition Parser ==============
// Parse :::type syntax and convert to Admonition component
function parseAdmonitions(content: string): string {
  // Match :::type [title]\ncontent\n:::
  const admonitionRegex = /:::(note|tip|warning|danger|info)(?:\s+(.+?))?\n([\s\S]*?):::/g;

  return content.replace(admonitionRegex, (match, type, title, body) => {
    // Add newlines before and after to ensure it's treated as a block element, not inline within a <p>
    return `\n\n<admonition type="${type}" title="${title || ''}">${body.trim()}</admonition>\n\n`;
  });
}

// ============== Heading ==============
function Heading({ level, children }: { level: number; children: React.ReactNode }) {
  const sizeClasses = {
    1: 'text-2xl font-bold mt-6 mb-4',
    2: 'text-xl font-semibold mt-5 mb-3',
    3: 'text-lg font-semibold mt-4 mb-2',
    4: 'text-base font-medium mt-3 mb-2',
    5: 'text-sm font-medium mt-2 mb-1',
    6: 'text-sm font-medium mt-2 mb-1',
  };

  const HeadingTag = {
    1: 'h1' as const,
    2: 'h2' as const,
    3: 'h3' as const,
    4: 'h4' as const,
    5: 'h5' as const,
    6: 'h6' as const,
  }[level];

  return (
    <HeadingTag className={sizeClasses[level] || sizeClasses[3]}>
      {children}
    </HeadingTag>
  );
}

// ============== Table ==============
function Table({ children }: { children: React.ReactNode }) {
  return (
    <div className="my-4 overflow-x-auto">
      <table className="min-w-full border-collapse">
        {children}
      </table>
    </div>
  );
}

function TableRow({ children }: { children: React.ReactNode }) {
  return (
    <tr className="border-b border-gray-200 last:border-b-0">
      {children}
    </tr>
  );
}

function TableCell({ children, head }: { children: React.ReactNode; head?: boolean }) {
  const Tag = head ? 'th' : 'td';
  return (
    <Tag className="px-4 py-2 text-left text-sm border-r border-gray-200 last:border-r-0">
      {children}
    </Tag>
  );
}

// ============== Link ==============
function Link({ href, children }: { href: string; children: React.ReactNode }) {
  const isExternal = href.startsWith('http');
  return (
    <a
      href={href}
      target={isExternal ? '_blank' : undefined}
      rel={isExternal ? 'noopener noreferrer' : undefined}
      className="text-blue-600 hover:underline inline-flex items-center gap-1"
    >
      {children}
      {isExternal && (
        <svg className="w-3 h-3 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
        </svg>
      )}
    </a>
  );
}

// ============== Image ==============
function Image({ src, alt }: { src: string; alt?: string }) {
  return (
    <div className="my-4">
      <img
        src={src}
        alt={alt}
        className="max-w-full h-auto rounded-lg border border-gray-200"
        onError={(e) => {
          (e.target as HTMLImageElement).style.display = 'none';
        }}
      />
      {alt && <p className="text-sm text-gray-500 text-center mt-2">{alt}</p>}
    </div>
  );
}

// ============== Blockquote ==============
function Blockquote({ children }: { children: React.ReactNode }) {
  return (
    <blockquote className="my-3 pl-4 pr-3 py-2 bg-blue-50 border-l-4 border-blue-400 rounded-r-lg text-sm text-gray-700">
      {children}
    </blockquote>
  );
}

// ============== Lists ==============
function UnorderedList({ children }: { children: React.ReactNode }) {
  return (
    <ul className="my-2 ml-4 list-disc list-outside space-y-1">
      {children}
    </ul>
  );
}

function OrderedList({ children }: { children: React.ReactNode }) {
  return (
    <ol className="my-2 ml-4 list-decimal list-outside space-y-1">
      {children}
    </ol>
  );
}

function ListItem({ children }: { children: React.ReactNode }) {
  return <li className="text-sm leading-relaxed">{children}</li>;
}

// ============== Inline Math ==============
function InlineMath({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-block px-1 py-0.5 bg-gray-100 rounded text-sm font-mono">
      {children}
    </span>
  );
}

// ============== Main Component ==============
export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  if (!content) return null;

  // Parse admonitions before rendering
  const processedContent = parseAdmonitions(content);

  return (
    <div className="markdown-body prose prose-sm max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex, rehypeRaw]}
        components={{
          // Custom admonition component
          // @ts-ignore - custom component
          admonition: ({ type, title, children }) => (
            <Admonition type={type as AdmonitionType} title={title}>
              {children}
            </Admonition>
          ),

          // Code blocks
          code({ node, inline, className, children, ...props }: any) {
            const match = /language-(\w+)/.exec(className || '');
            const language = match ? match[1] : '';
            const code = String(children).replace(/\n$/, '');

            if (inline) {
              if (language === 'math' || className?.includes('math')) {
                return <InlineMath>{children}</InlineMath>;
              }
              return (
                <code
                  className="px-1.5 py-0.5 bg-gray-100 rounded text-sm font-mono text-pink-600"
                  {...props}
                >
                  {children}
                </code>
              );
            }

            return <CodeBlock language={language} code={code} />;
          },

          // Headings
          h1: ({ children }) => <Heading level={1}>{children}</Heading>,
          h2: ({ children }) => <Heading level={2}>{children}</Heading>,
          h3: ({ children }) => <Heading level={3}>{children}</Heading>,
          h4: ({ children }) => <Heading level={4}>{children}</Heading>,
          h5: ({ children }) => <Heading level={5}>{children}</Heading>,
          h6: ({ children }) => <Heading level={6}>{children}</Heading>,

          // Table
          table: ({ children }) => <Table>{children}</Table>,
          thead: ({ children }) => (
            <thead className="bg-gray-50">{children}</thead>
          ),
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: ({ children }) => <TableRow>{children}</TableRow>,
          th: ({ children }) => <TableCell head>{children}</TableCell>,
          td: ({ children }) => <TableCell>{children}</TableCell>,

          // Links
          a: ({ href, children }) => <Link href={href!}>{children}</Link>,

          // Images
          img: ({ src, alt }) => <Image src={src!} alt={alt} />,

          // Blockquotes
          blockquote: ({ children }) => <Blockquote>{children}</Blockquote>,

          // Lists
          ul: ({ children }) => <UnorderedList>{children}</UnorderedList>,
          ol: ({ children }) => <OrderedList>{children}</OrderedList>,
          li: ({ children }) => <ListItem>{children}</ListItem>,

          // Paragraph
          p: ({ children, node, ...props }) => {
            // 检查是否包含块级元素（code 块、div 等），如果是则使用 div
            const childArray = React.Children.toArray(children);
            const hasBlockChildren = childArray.some(
              (child) =>
                React.isValidElement(child) &&
                (child.type === 'div' ||
                 child.type === 'pre' ||
                 child.type === 'table' ||
                 child.type === 'ul' ||
                 child.type === 'ol' ||
                 child.type === 'admonition')
            );

            // 如果是空的 p 标签，不渲染
            if (childArray.length === 0 || (childArray.length === 1 && childArray[0] === '')) {
              return null;
            }

            if (hasBlockChildren) {
              return <div className="my-2 text-sm leading-relaxed" {...props}>{children}</div>;
            }
            return <p className="my-2 text-sm leading-relaxed" {...props}>{children}</p>;
          },

          // Horizontal rule
          hr: () => <hr className="my-6 border-gray-200" />,
        }}
      >
        {processedContent}
      </ReactMarkdown>
    </div>
  );
}
