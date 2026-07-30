# 前端集成指南

## 概述

现在前端可以通过统一的 API 端点调用工厂模式的 Agent 执行服务。

## API 端点

### 1. 执行 Agent（非流式）

```http
POST /api/v1/agents/{agent_id}/execute
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体**:
```json
{
  "query": "分析这个 Python 项目",
  "model_name": "claude-3-opus",
  "plan_mode": true,
  "skills": ["code_interpreter"],
  "mcp_servers": ["filesystem"],
  "session_id": "session-123"
}
```

**响应**:
```json
{
  "run_id": "uuid-xxx",
  "response": "分析结果...",
  "messages": [
    {"role": "human", "content": "分析这个 Python 项目"},
    {"role": "ai", "content": "分析结果..."}
  ],
  "factory_mode": true,
  "agent_type": "lead_agent"
}
```

### 2. 执行 Agent（流式）

```http
POST /api/v1/agents/{agent_id}/execute/stream
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体**:
```json
{
  "query": "分析这个 Python 项目",
  "model_name": "claude-3-opus",
  "plan_mode": true,
  "session_id": "session-123"
}
```

**响应**: SSE (Server-Sent Events)

```
event: token
data: {"content": "分"}

event: token
data: {"content": "析"}

event: done
data: {"status": "completed"}
```

### 3. 获取可用子智能体

```http
GET /api/v1/agents/subagents
Authorization: Bearer {token}
```

**响应**:
```json
[
  {
    "type": "code_analyzer",
    "name": "代码分析专家",
    "description": "你是一位资深代码分析专家...",
    "default_skills": ["code_interpreter"]
  },
  {
    "type": "doc_writer",
    "name": "技术文档专家",
    "description": "你是一位专业技术文档工程师...",
    "default_skills": ["file_processor"]
  }
]
```

### 4. 注册自定义子智能体

```http
POST /api/v1/agents/subagents
Content-Type: application/json
Authorization: Bearer {token}
```

**请求体**:
```json
{
  "name": "security_auditor",
  "system_prompt": "你是一位安全审计专家...",
  "skills": ["code_interpreter"],
  "model_config": {
    "provider": "anthropic",
    "model": "claude-3-opus"
  }
}
```

**响应**:
```json
{
  "id": "custom_subagent_security_auditor_xxx",
  "name": "security_auditor",
  "type": "custom_subagent"
}
```

## 前端使用示例

### React Hook 示例

```typescript
// src/hooks/useAgentExecute.ts
import { useState, useCallback } from 'react';
import { executeAgent, executeAgentStreamFetch } from '@/lib/api/agent-execute';

interface UseAgentExecuteOptions {
  agentId: string;
  model_name?: string;
  plan_mode?: boolean;
  session_id?: string;
}

export function useAgentExecute(options: UseAgentExecuteOptions) {
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  // 非流式执行
  const execute = useCallback(async (query: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await executeAgent(options.agentId, {
        query,
        model_name: options.model_name,
        plan_mode: options.plan_mode,
        session_id: options.session_id,
      });
      setResponse(result.response);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : '执行失败');
      throw err;
    } finally {
      setLoading(false);
    }
  }, [options]);

  // 流式执行
  const executeStream = useCallback(async (query: string, onToken: (token: string) => void) => {
    setLoading(true);
    setError(null);
    let fullResponse = '';
    
    try {
      const controller = await executeAgentStreamFetch(options.agentId, {
        query,
        model_name: options.model_name,
        plan_mode: options.plan_mode,
        session_id: options.session_id,
      }, {
        onToken: (token) => {
          fullResponse += token;
          onToken(token);
        },
        onDone: () => {
          setResponse(fullResponse);
          setLoading(false);
        },
        onError: (err) => {
          setError(err);
          setLoading(false);
        },
      });
      
      return controller; // 用于中止
    } catch (err) {
      setError(err instanceof Error ? err.message : '执行失败');
      setLoading(false);
      throw err;
    }
  }, [options]);

  return {
    loading,
    response,
    error,
    execute,
    executeStream,
    clearResponse: () => setResponse(''),
  };
}
```

### 组件使用示例

```tsx
// src/components/AgentChat.tsx
import React, { useState } from 'react';
import { useAgentExecute } from '@/hooks/useAgentExecute';
import { Textarea } from '@/components/bird/Textarea';
import { Button } from '@/components/bird/Button';

interface AgentChatProps {
  agentId: string;
}

export function AgentChat({ agentId }: AgentChatProps) {
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<Array<{role: string, content: string}>>([]);
  
  const { loading, response, executeStream } = useAgentExecute({
    agentId,
    plan_mode: true,
  });

  const handleSubmit = async () => {
    if (!query.trim() || loading) return;
    
    const userMessage = { role: 'user', content: query };
    setMessages(prev => [...prev, userMessage]);
    
    const currentQuery = query;
    setQuery('');
    
    // 流式执行
    let aiContent = '';
    await executeStream(currentQuery, (token) => {
      aiContent += token;
      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (last && last.role === 'assistant') {
          return [...prev.slice(0, -1), { role: 'assistant', content: aiContent }];
        }
        return [...prev, { role: 'assistant', content: aiContent }];
      });
    });
  };

  return (
    <div className="agent-chat">
      <div className="messages">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            {msg.content}
          </div>
        ))}
      </div>
      
      <div className="input-area">
        <Textarea
          value={query}
          onChange={setQuery}
          placeholder="输入你的问题..."
          disabled={loading}
        />
        <Button onClick={handleSubmit} disabled={loading || !query.trim()}>
          {loading ? '执行中...' : '发送'}
        </Button>
      </div>
    </div>
  );
}
```

### 子智能体选择器示例

```tsx
// src/components/SubagentSelector.tsx
import React, { useEffect, useState } from 'react';
import { getAvailableSubagents } from '@/lib/api/agent-execute';

interface Subagent {
  type: string;
  name: string;
  description: string;
  default_skills: string[];
}

export function SubagentSelector({ onSelect }: { onSelect: (type: string) => void }) {
  const [subagents, setSubagents] = useState<Subagent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAvailableSubagents().then(data => {
      setSubagents(data);
      setLoading(false);
    });
  }, []);

  if (loading) return <div>加载中...</div>;

  return (
    <div className="subagent-selector">
      <h3>选择子智能体</h3>
      <div className="subagent-list">
        {subagents.map(sub => (
          <div
            key={sub.type}
            className="subagent-card"
            onClick={() => onSelect(sub.type)}
          >
            <h4>{sub.name}</h4>
            <p>{sub.description}</p>
            <div className="skills">
              {sub.default_skills.map(skill => (
                <span key={skill} className="skill-tag">{skill}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

## 完整流程示例

### 1. 前端创建智能体

```typescript
// 创建智能体
const createAgent = async () => {
  const response = await fetch('/api/v1/agents', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({
      name: "代码分析助手",
      description: "专业的代码分析助手",
      agent_type: "single",
      system_prompt: "你是一位代码分析专家...",
      enabled_skills: ["code_interpreter"],
      extensions_config: {
        plan_mode_enabled: true,
        mcp_servers_enabled: ["filesystem"],
      },
    }),
  });
  
  const agent = await response.json();
  return agent.id; // 保存 agent_id
};
```

### 2. 前端执行智能体

```typescript
// 执行智能体
const runAgent = async (agentId: string, query: string) => {
  const response = await fetch(`/api/v1/agents/${agentId}/execute`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({
      query,
      model_name: "claude-3-opus",  // 运行时选择模型
      plan_mode: true,               // 启用计划模式
    }),
  });
  
  const result = await response.json();
  console.log(result.response); // 智能体响应
};
```

### 3. 前端流式执行

```typescript
// 流式执行智能体
const runAgentStream = async (agentId: string, query: string) => {
  const response = await fetch(`/api/v1/agents/${agentId}/execute/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
    },
    body: JSON.stringify({
      query,
      plan_mode: true,
    }),
  });
  
  const reader = response.body?.getReader();
  const decoder = new TextDecoder();
  
  while (true) {
    const { done, value } = await reader!.read();
    if (done) break;
    
    const chunk = decoder.decode(value);
    // 解析 SSE 事件
    const lines = chunk.split('\n');
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        if (data.content) {
          console.log('Token:', data.content);
        }
      }
    }
  }
};
```

## 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      前端 React App                          │
│                                                              │
│  ┌────────────────┐  ┌──────────────────┐  ┌─────────────┐ │
│  │ AgentChat      │  │ SubagentSelector │  │ 其他组件    │ │
│  │ Component      │  │ Component        │  │             │ │
│  └───────┬────────┘  └────────┬─────────┘  └─────────────┘ │
│          │                    │                              │
│          ▼                    ▼                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │         agent-execute.ts (API Client)                   ││
│  │  - executeAgent()                                       ││
│  │  - executeAgentStreamFetch()                            ││
│  │  - getAvailableSubagents()                              ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP/REST API
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   后端 FastAPI Server                        │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │         agents.py (API Routes)                          ││
│  │  - POST /api/v1/agents/{id}/execute                     ││
│  │  - POST /api/v1/agents/{id}/execute/stream              ││
│  │  - GET  /api/v1/agents/subagents                        ││
│  └─────────────────────────────────────────────────────────┘│
│                              │                               │
│                              ▼                               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │      AgentOrchestrationService (编排服务)                ││
│  │  - execute_lead_agent()                                 ││
│  │  - execute_subagent_direct()                            ││
│  └─────────────────────────────────────────────────────────┘│
│                              │                               │
│              ┌───────────────┴───────────────┐               │
│              ▼                               ▼               │
│  ┌─────────────────────┐      ┌─────────────────────────┐   │
│  │ LeadAgentFactory    │      │ SubagentService         │   │
│  │ (动态创建主智能体)   │      │ (动态唤起子智能体)       │   │
│  └─────────────────────┘      └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## 总结

现在前端可以通过以下方式与智能体交互：

1. **创建智能体**: `POST /api/v1/agents`
2. **执行智能体**: `POST /api/v1/agents/{id}/execute`
3. **流式执行**: `POST /api/v1/agents/{id}/execute/stream`
4. **管理子智能体**: `GET/POST /api/v1/agents/subagents`

所有执行都通过工厂模式，支持：
- 运行时动态模型选择
- 计划模式
- 技能/MCP 服务器覆盖
- 子智能体动态唤起
