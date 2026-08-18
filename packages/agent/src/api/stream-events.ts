/**
 * /execute/stream SSE 事件协议 —— 前端镜像（与 backend/packages/agent/schemas/stream.py 对齐）
 *
 * 后端唯一真源是 Python 侧 Pydantic 判别联合 AgentStreamEvent；
 * 本文件用 TS 判别联合镜像同一契约，并导出一组类型守卫做收窄，
 * 取代 QAChatView 里一串内联 `parsed.type ===` 假设。
 *
 * 新增一个事件的姿势（与后端子模块 docstring 同步）：
 * 1. 后端 schema/stream.py 加 model + Union 分支 + ev_xxx() 工厂
 * 2. 生产者调工厂
 * 3. 本文件 Union 加一个分支 + 加一个 isXxx 守卫
 * 4. QAChatView 用守卫收窄
 */

export type ToolStatus = 'running' | 'success' | 'error' | 'denied' | 'limited' | 'circuit' | 'blocked';

export interface ToolEventFile {
  filename: string;
  relative_path: string;
}

export interface ToolEventData {
  phase: 'start' | 'done';
  tool: string;
  input?: Record<string, unknown>;
  status?: ToolStatus;
  result?: string;
  files?: ToolEventFile[];
  sandbox?: string;
}

export interface OrchestratorPlanData {
  need_sub_agents: boolean;
  run_mode?: 'serial' | 'parallel';
  plan?: unknown[];
}

export interface SubAgentData {
  sub_agent_id: string;
  status: 'running' | 'done';
  success?: boolean;
  content?: string;
}

export interface ApprovalRequiredData {
  sub_agent_id?: string;
  pending?: unknown[];
}

export interface DoneData {
  reason?: 'completed' | 'max_iterations' | 'interrupted';
  rounds?: number;
  tools_used?: string[];
  files?: ToolEventFile[];
}

export type AgentStreamEvent =
  | { type: 'orchestrator_plan'; data?: OrchestratorPlanData }
  | { type: 'reasoning'; content?: string }
  | { type: 'token'; content?: string }
  | { type: 'tool_event'; data?: ToolEventData }
  | { type: 'sub_agent'; data?: SubAgentData }
  | { type: 'approval_required'; data?: ApprovalRequiredData }
  | { type: 'done'; data?: DoneData }
  | { type: 'error'; error?: string; error_code?: string; error_category?: string }
  | { type: 'complete'; run_id?: string }
  | { type: 'citations'; citations?: unknown[] }
  | { type: 'agent_selected'; agent_name?: string };

// -------- 类型守卫（判别字段收窄） --------

export function isOrchestratorPlan(ev: AgentStreamEvent): ev is Extract<AgentStreamEvent, { type: 'orchestrator_plan' }> {
  return ev.type === 'orchestrator_plan';
}

export function isSubAgent(ev: AgentStreamEvent): ev is Extract<AgentStreamEvent, { type: 'sub_agent' }> {
  return ev.type === 'sub_agent';
}

export function isAgentSelected(ev: AgentStreamEvent): ev is Extract<AgentStreamEvent, { type: 'agent_selected' }> {
  return ev.type === 'agent_selected';
}

export function isApprovalRequired(ev: AgentStreamEvent): ev is Extract<AgentStreamEvent, { type: 'approval_required' }> {
  return ev.type === 'approval_required';
}

export function isToolEvent(ev: AgentStreamEvent): ev is Extract<AgentStreamEvent, { type: 'tool_event' }> {
  return ev.type === 'tool_event';
}

export function isReasoning(ev: AgentStreamEvent): ev is Extract<AgentStreamEvent, { type: 'reasoning' }> {
  return ev.type === 'reasoning';
}

export function isToken(ev: AgentStreamEvent): ev is Extract<AgentStreamEvent, { type: 'token' }> {
  return ev.type === 'token';
}

export function isDone(ev: AgentStreamEvent): ev is Extract<AgentStreamEvent, { type: 'done' }> {
  return ev.type === 'done';
}

export function isErrorEvent(ev: AgentStreamEvent): ev is Extract<AgentStreamEvent, { type: 'error' }> {
  return ev.type === 'error';
}

export function isComplete(ev: AgentStreamEvent): ev is Extract<AgentStreamEvent, { type: 'complete' }> {
  return ev.type === 'complete';
}

export function isCitations(ev: AgentStreamEvent): ev is Extract<AgentStreamEvent, { type: 'citations' }> {
  return ev.type === 'citations';
}
