export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Lang = "es" | "pt";
export type Candidate = { transaction_id: string; merchant: string; amount: string; currency: string; date: string };
export type VerifiedFact = { fact: string; source: string };
export type ActionRecord = { action: string; status: "verified" | "failed"; at: string; ref: string | null };
export type PolicyDecision = {
  decision: string; rule_ids: string[]; policy_version: string; inputs: Record<string, any>;
  missing_evidence?: string[]; handoff_reasons?: string[];
};
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
  risk_signals: Record<string, any>;
  trace_id: string;
  customer_id: string | null;
  transaction_id: string | null;
};
export type QueueItem = Handoff & {
  at: string;
  status: "new" | "resolved" | "closed";
  resolution: { action: string; case_id?: string; note: string; at: string; decision?: PolicyDecision } | null;
};
export type Reply = {
  conversation_id: string;
  text: string;
  language: Lang;
  state: string;
  action: string;
  ask_for: string[];
  candidates: Candidate[];
  offer_block_card: boolean;
  case_id: string | null;
  card_status: string | null;
  handoff: Handoff | null;
  policy: PolicyDecision | null;
  injection_flags: string[];
  pii_redacted: string[];
  nlu_mode: "claude" | "rules" | "none";
  usage: { model: string; cost_usd: number; latency_ms: number } | null;
  latency_ms: number;
};
export type Me = {
  customer_id: string; first_name: string | null; country: string; segment: string;
  cards: { product_id: string; product_type: string; product_status: string }[];
};
export type Txn = {
  transaction_id: string; product_id: string; transaction_date: string; amount: string; currency: string;
  amount_usd: string; merchant_name: string | null; transaction_status: string; transaction_country: string;
  case_id: string | null;
};
export type Case = {
  case_id: string; transaction_id: string; reason_code: string; status: string; created_at: string;
  policy_version: string; opened_by: "assistant" | "agent"; merchant_name: string | null; amount: string;
  currency: string; transaction_date: string;
};
export type Alert = Omit<Txn, "case_id"> & { fraud_score: string | null };
export type Scenario = { id: string; label: string; customer_id: string; language: Lang; try: string; expected: string };
export type NluStatus = { mode: "claude" | "rules"; reason: string | null; fallback: boolean };
export type Health = { status: string; policy_version: string; now: string; demo_mode: boolean; nlu: NluStatus };
export type TraceEvent = { trace_id: string; at: string; kind: string; data: Record<string, any> };
export type DemoCustomer = { customer_id: string; first_name: string | null; country: string; segment: string };

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** Each browser tab gets its own copy of the demo data, so judges never see each other's cases. */
let workspace = "";
export function workspaceId(): string {
  if (workspace) return workspace;
  try { workspace = sessionStorage.getItem("demoWorkspace") ?? ""; } catch { /* storage unavailable */ }
  if (!workspace) {
    workspace = `ws-${Math.random().toString(36).slice(2, 12)}`;
    try { sessionStorage.setItem("demoWorkspace", workspace); } catch { /* ignore */ }
  }
  return workspace;
}

async function call<T>(path: string, init: RequestInit & { token?: string } = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json", "X-Demo-Workspace": workspaceId() };
  if (init.token) headers.Authorization = `Bearer ${init.token}`;
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = typeof body.detail === "string" ? body.detail : body.detail?.message ?? res.statusText;
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const post = (body: unknown) => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  health: () => call<Health>("/health"),
  scenarios: () => call<Scenario[]>("/demo/scenarios"),
  customers: () => call<DemoCustomer[]>("/demo/customers"),
  reset: () => call<{ status: string }>("/demo/reset", post({})),
  outage: (on: boolean) => call<{ nlu: NluStatus }>("/demo/outage", post({ on })),
  login: (customer_id: string, ttl_seconds?: number) => call<{ token: string }>("/auth/session", post({ customer_id, ttl_seconds })),
  me: (token: string) => call<Me>("/me", { token }),
  transactions: (token: string) => call<Txn[]>("/me/transactions", { token }),
  cases: (token: string) => call<Case[]>("/me/cases", { token }),
  alerts: (token: string) => call<Alert[]>("/me/alerts", { token }),
  start: (language: Lang, token?: string, transaction_id?: string) =>
    call<{ conversation_id: string; text: string; reply: Reply | null }>("/conversations", { ...post({ language, transaction_id }), token }),
  send: (cid: string, text: string, token: string) => call<Reply>(`/conversations/${cid}/messages`, { ...post({ text }), token }),
  startAlert: (txn: string, language: Lang, token: string) =>
    call<{ conversation_id: string; text: string }>(`/alerts/${txn}/start`, { ...post({ language }), token }),
  handoffs: () => call<QueueItem[]>("/agent/handoffs"),
  resolve: (ref: string, body: { action: "open_dispute" | "close"; note: string; reason_code?: string | null }) =>
    call<{ status: string; case_id?: string; decision?: PolicyDecision }>(`/agent/handoffs/${ref}/resolve`, post(body)),
  trace: (id: string) => call<TraceEvent[]>(`/agent/traces/${id}`),
  metrics: () => call<Record<string, any>>("/agent/metrics"),
};
