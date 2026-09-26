export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Candidate = { transaction_id: string; merchant: string; amount: string; currency: string; date: string };
export type VerifiedFact = { fact: string; source: string };
export type ActionRecord = { action: string; status: "verified" | "failed"; at: string; ref: string | null };
export type PolicyDecision = { decision: string; rule_ids: string[]; policy_version: string; inputs: Record<string, unknown> };
export type Handoff = {
  case_ref: string;
  reason_for_handoff: string[];
  language: string;
  channel: string;
  customer_request_summary: string;
  verified_facts: VerifiedFact[];
  proposed_reason_code: string | null;
  actions_taken: ActionRecord[];
  policy_decision: PolicyDecision | null;
  open_questions: string[];
  risk_signals: Record<string, string | null>;
  trace_id: string;
};
export type Reply = {
  conversation_id: string;
  text: string;
  language: string;
  state: string;
  action: string;
  ask_for: string[];
  candidates: Candidate[];
  offer_block_card: boolean;
  case_id: string | null;
  card_status: string | null;
  handoff: Handoff | null;
  injection_flags: string[];
  pii_redacted: string[];
  usage: { model: string; cost_usd: number; latency_ms: number; input_tokens: number; output_tokens: number } | null;
  latency_ms: number;
};
export type TraceEvent = { trace_id: string; at: string; kind: string; data: Record<string, any> };

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit & { token?: string; agentKey?: string } = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (init.token) headers.Authorization = `Bearer ${init.token}`;
  if (init.agentKey) headers["X-Agent-Key"] = init.agentKey;
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  customers: () => call<{ customer_id: string; country: string; segment: string }[]>("/demo/customers"),
  login: (customer_id: string, ttl_seconds?: number) =>
    call<{ token: string }>("/auth/session", { method: "POST", body: JSON.stringify({ customer_id, ttl_seconds }) }),
  startConversation: (language: string) =>
    call<{ conversation_id: string; text: string }>("/conversations", { method: "POST", body: JSON.stringify({ language }) }),
  send: (cid: string, text: string, token: string) =>
    call<Reply>(`/conversations/${cid}/messages`, { method: "POST", body: JSON.stringify({ text }), token }),
  startAlert: (txn: string, language: string, token: string) =>
    call<{ conversation_id: string; text: string }>(`/alerts/${txn}/start`, { method: "POST", body: JSON.stringify({ language }), token }),
  trace: (cid: string, agentKey: string) => call<TraceEvent[]>(`/agent/traces/${cid}`, { agentKey }),
  handoffs: (agentKey: string) => call<(Handoff & { state: string })[]>("/agent/handoffs", { agentKey }),
  alerts: (agentKey: string) => call<{ transaction_id: string; customer_id: string; merchant_name: string; amount: string; currency: string; fraud_score: string; transaction_date: string }[]>("/agent/alerts", { agentKey }),
  metrics: (agentKey: string) => call<Record<string, any>>("/agent/metrics", { agentKey }),
  pqr: (agentKey: string, complaints: unknown[]) =>
    call<{ complaint_id: string; action: string; state: string; case_id: string | null; handoff_reasons: string[]; rule_ids: string[] }[]>(
      "/agent/pqr/run", { method: "POST", body: JSON.stringify({ complaints }), agentKey }),
};
