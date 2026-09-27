"use client";
import { useEffect, useState } from "react";
import { api, type NluStatus, type QueueItem, type Reply, type TraceEvent } from "@/lib/api";
import { dayTime } from "@/lib/format";

export type BankTab = "queue" | "decisions" | "operations";

const REASONS = ["FRAUD_CNP", "FRAUD_CP", "DUPLICATE", "INCORRECT_AMOUNT", "NOT_RECEIVED", "CANCELLED_RECURRING"];
const REASON_EN: Record<string, string> = {
  FRAUD_CNP: "Unrecognised charge", FRAUD_CP: "Lost or stolen card", DUPLICATE: "Duplicate charge",
  INCORRECT_AMOUNT: "Wrong amount", NOT_RECEIVED: "Not received", CANCELLED_RECURRING: "Cancelled subscription",
};
const HANDOFF_EN: Record<string, string> = {
  amount_above_threshold: "Amount above US$ 450", repeat_complainer: "Repeat complainer", dispute_velocity: "Many disputes in 30 days",
  very_negative_sentiment: "Very upset customer", regulatory_or_legal_threat: "Regulator or legal threat",
  low_classifier_confidence: "Unclear reason", customer_requested_human: "Customer asked for a person",
  suspicious_access: "Asked for another customer's charge", invalid_transaction_references: "Invalid references",
  clarification_exhausted: "Could not clarify in 2 tries", tool_failure: "Bank system failed", verification_failed: "Action not verified",
  nlu_unavailable: "Language service down", async_missing_info: "Written complaint missing data",
};
const FIELD_EN: Record<string, string> = {
  transaction: "which charge", reason_code: "dispute reason", card_in_possession: "card in possession",
  recognizes_merchant: "recognises merchant", duplicate_transaction_id: "the other charge", expected_amount: "correct amount",
  expected_delivery_date: "delivery date", contacted_merchant: "contacted merchant", cancellation_date: "cancellation date",
};

// ---- Queue ---------------------------------------------------------------------------------------------
function Package({ item, onDone }: { item: QueueItem; onDone: () => void }) {
  const [reason, setReason] = useState(item.proposed_reason_code ?? "FRAUD_CNP");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setReason(item.proposed_reason_code ?? "FRAUD_CNP"); setNote(""); setError(null); }, [item.case_ref, item.proposed_reason_code]);
  const act = async (action: "open_dispute" | "close") => {
    setBusy(true); setError(null);
    try { await api.resolve(item.case_ref, { action, note, reason_code: action === "open_dispute" ? reason : null }); onDone(); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  };
  const p = item.policy_decision;
  return (
    <article className="pkg">
      <header className="pkg-head">
        <div>
          <h3 className="mono">{item.case_ref}</h3>
          <p className="muted">{item.channel} · {item.language.toUpperCase()} · customer <span className="mono">{item.customer_id ?? "unknown"}</span> · {dayTime(item.at)}</p>
        </div>
        <span className={`status status-${item.status}`}>{item.status}</span>
      </header>
      <dl className="pkg-grid">
        <dt>Why a person</dt>
        <dd>{item.reason_for_handoff.map((r) => <span key={r} className="chip chip-risk">{HANDOFF_EN[r] ?? r}</span>)}
          {p && <span className="muted"> · {p.rule_ids.join(", ")} ({p.policy_version})</span>}</dd>
        <dt>Customer wants</dt><dd>{item.customer_request_summary || <span className="muted">Not stated yet</span>}</dd>
        <dt>Verified facts</dt>
        <dd>{item.verified_facts.length ? item.verified_facts.map((f) => <div key={f.source}>{f.fact} <span className="muted mono">[{f.source}]</span></div>)
          : <span className="muted">None: the charge was never identified.</span>}</dd>
        <dt>Actions taken</dt>
        <dd>{item.actions_taken.length ? item.actions_taken.map((a, i) => <span key={i} className="chip">{a.action} · {a.status}</span>)
          : <span className="muted">None. Nothing was opened or blocked.</span>}</dd>
        <dt>Still open</dt>
        <dd>{item.open_questions.length ? item.open_questions.map((q) => <span key={q} className="chip">{FIELD_EN[q] ?? q}</span>) : <span className="muted">Nothing</span>}</dd>
        {Object.values(item.risk_signals).some((v) => v !== null) && <>
          <dt>Risk signals</dt>
          <dd>{Object.entries(item.risk_signals).filter(([, v]) => v !== null).map(([k, v]) => <span key={k} className="chip">{k}: {Array.isArray(v) ? v.join(", ") : String(v)}</span>)}</dd>
        </>}
      </dl>
      <p className="muted small">The agent gets facts read from the bank's systems and the policy decision, not the raw chat.</p>
      {item.status === "new" ? (
        <div className="pkg-act">
          <label className="field">Reason
            <select id={`reason-${item.case_ref}`} value={reason} onChange={(e) => setReason(e.target.value)}>
              {REASONS.map((r) => <option key={r} value={r}>{REASON_EN[r]}</option>)}
            </select>
          </label>
          <label className="field grow">Note for the record
            <input id={`note-${item.case_ref}`} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Called the customer, confirmed card in hand" />
          </label>
          <div className="pkg-buttons">
            <button className="btn btn-primary" onClick={() => act("open_dispute")} disabled={busy || !item.transaction_id}>Open dispute</button>
            <button className="btn" onClick={() => act("close")} disabled={busy}>Close without action</button>
          </div>
          {!item.transaction_id && <p className="muted small">No verified charge in this case: contact the customer first, or close it.</p>}
          {error && <p className="error" role="alert">{error}</p>}
          <p className="muted small">Opening re-checks the policy as a human review: handoff triggers no longer block, but the window, status and duplicate rules still apply.</p>
        </div>
      ) : (
        <div className="pkg-done">
          {item.resolution?.action === "open_dispute"
            ? <>Dispute <span className="mono">{item.resolution.case_id}</span> opened by the agent and verified. The customer sees it under their disputes.</>
            : <>Closed without action.</>}
          {item.resolution?.note && <> Note: “{item.resolution.note}”</>}
        </div>
      )}
    </article>
  );
}

function Queue({ items, selected, onSelect, onChanged }: { items: QueueItem[]; selected: string | null; onSelect: (r: string) => void; onChanged: () => void }) {
  const current = items.find((i) => i.case_ref === selected) ?? items[0];
  if (!items.length) return (
    <p className="empty">No cases need a person yet. Run the <strong>Needs a person</strong> or <strong>Attack</strong> scenario and the handoff lands here with its package.</p>
  );
  return (
    <div className="queue-layout">
      <ul className="queue">
        {items.map((i) => (
          <li key={i.case_ref}>
            <button aria-current={current?.case_ref === i.case_ref} onClick={() => onSelect(i.case_ref)}>
              <span className="queue-top"><span className="mono">{i.case_ref.slice(0, 20)}</span><span className={`status status-${i.status}`}>{i.status}</span></span>
              <span className="queue-why">{i.reason_for_handoff.map((r) => HANDOFF_EN[r] ?? r).join(" · ")}</span>
            </button>
          </li>
        ))}
      </ul>
      {current && <Package item={current} onDone={onChanged} />}
    </div>
  );
}

// ---- Decisions -----------------------------------------------------------------------------------------
function line(e: TraceEvent): { kind: string; tone?: "action" | "risk" | "ai"; text: React.ReactNode } | null {
  const d = e.data;
  switch (e.kind) {
    case "started_from_purchase": return { kind: "Started", text: <>Customer tapped the purchase <span className="mono">{d.transaction_id}</span> in the app: no need to search for it.</> };
    case "proactive_alert": return { kind: "Fraud alert", text: <>Asked the customer about <span className="mono">{d.transaction_id}</span> (fraud score {d.fraud_score}).</> };
    case "customer_message": return {
      kind: "Customer", tone: d.injection_flags?.length ? "risk" : undefined, text: <>
        “{d.text}”
        {d.pii?.length > 0 && <div className="muted small">Masked before any model saw it: {d.pii.join(", ")}</div>}
        {d.injection_flags?.length > 0 && <div className="risk small">Injection signals: {d.injection_flags.join(", ")}. They are logged; they cannot grant any permission.</div>}
      </> };
    case "nlu": {
      const r = d.result;
      const fields = Object.entries(r).filter(([k, v]) => v !== null && v !== false && v !== "" &&
        !["intent", "language", "summary", "reason_confidence", "very_negative_sentiment", "regulatory_threat"].includes(k));
      const rules = d.usage.model === "rules" || d.usage.model.startsWith("rules+");
      const clf = d.classifier;
      const learned = clf ? ` · classifier ${clf.version}: ${clf.label} p=${clf.probability.toFixed(2)} ${clf.accepted ? "(used)" : "(below threshold, rules kept)"}` : "";
      return { kind: rules ? "Understood (rules)" : "Understood (AI)", tone: "ai", text: <>
        Intent <strong>{r.intent}</strong>{fields.length > 0 && <> · {fields.map(([k, v]) => `${k}: ${v}`).join(" · ")}</>}
        <div className="muted small">{rules ? `Rule-based fallback${learned} · US$ 0` : `${d.usage.model} · ${Math.round(d.usage.latency_ms)} ms · US$ ${d.usage.cost_usd.toFixed(4)}`}. The model only fills fields; it decides nothing.</div>
      </> };
    }
    case "nlu_failed": return { kind: "AI failed", tone: "risk", text: <>{d.error}{d.breaker_open ? " · circuit open" : ""}</> };
    case "nlu_fallback": return { kind: "Fallback", tone: "risk", text: <>Switched to the rule-based NLU ({String(d.reason).replaceAll("_", " ")}).</> };
    case "transaction_identified": return { kind: "Charge found", text: <span className="mono">{d.transaction_id}</span> };
    case "transaction_lookup_rejected": return { kind: "Lookup refused", tone: "risk", text: <><span className="mono">{d.transaction_id}</span> is not available to this session ({d.error}). The customer gets the same answer as for a charge that does not exist.</> };
    case "clarify": return { kind: "Asked for", text: <>{d.fields.map((f: string) => FIELD_EN[f] ?? f).join(", ")} <span className="muted">(try {d.attempt} of 2)</span></> };
    case "policy_decision": return { kind: "Policy", tone: "action", text: <>
      <strong>{d.decision}</strong> · {d.rule_ids.join(", ")} <span className="muted">({d.policy_version})</span>
      <div className="muted small">age {d.inputs.age_days} d of {d.inputs.window_days} · US$ {d.inputs.amount_usd} vs limit {d.inputs.amount_usd_threshold}{d.missing_evidence?.length ? ` · needs ${d.missing_evidence.map((f: string) => FIELD_EN[f] ?? f).join(", ")}` : ""}</div>
    </> };
    case "block_card_policy": return { kind: "Card policy", tone: "action", text: <>{d.decision} · {d.rule_ids.join(", ")}</> };
    case "confirm_requested": return { kind: "Waiting", text: "Customer confirmation required before any action." };
    case "action": return { kind: "Action", tone: "action", text: <>{d.action} <span className="mono">{d.ref}</span> · {d.status === "verified" ? "confirmed by reading it back" : "failed, not reported as done"}</> };
    case "handoff": return { kind: "Handoff", tone: "risk", text: <>{d.reason_for_handoff.map((r: string) => HANDOFF_EN[r] ?? r).join(", ")} → queue as <span className="mono">{d.case_ref}</span></> };
    case "agent_action": return { kind: "Agent", tone: "action", text: <>{d.action === "open_dispute" ? <>Opened <span className="mono">{d.case_id}</span> under {d.decision?.rule_ids?.join(", ")}{d.decision?.inputs?.overridden_rules?.length ? `, overriding ${d.decision.inputs.overridden_rules.join(", ")}` : ""}</> : "Closed without action"}{d.note && ` · “${d.note}”`}</> };
    case "auth_failed": return { kind: "Session refused", tone: "risk", text: `${d.reason}. Nothing is read or done without a valid session.` };
    case "done": return { kind: "Outcome", tone: "action", text: <>Case <span className="mono">{d.case_id}</span> opened and verified.</> };
    case "customer_declined": return { kind: "Outcome", text: "Customer declined. Nothing was opened." };
    case "closed": return { kind: "Outcome", text: `Closed without action (${String(d.reason).replaceAll("_", " ")}).` };
    default: return null;
  }
}

const STEPS = ["Charge", "Reason", "Evidence", "Policy", "Confirm", "Verified"];
const PROGRESS: Record<string, number> = { START: 0, IDENTIFY_TXN: 0, CLASSIFY: 1, COLLECT_EVIDENCE: 2, CONFIRM: 4, DONE: 6 };
const TERMINAL: Record<string, string> = { INELIGIBLE: "Not eligible", HANDOFF: "To a person", CANCELLED: "No action" };

function Decisions({ events, reply }: { events: TraceEvent[]; reply: Reply | null }) {
  const state = reply?.state ?? "START";
  const reached = PROGRESS[state] ?? 0;
  const lines = events.map(line).filter(Boolean) as NonNullable<ReturnType<typeof line>>[];
  return (
    <div>
      <ol className="steps" aria-label="Case progress">
        {STEPS.map((s, i) => {
          const last = i === STEPS.length - 1;
          const st = TERMINAL[state] && last ? "end" : state === "DONE" ? (last ? "end" : "done") : i < reached ? "done" : i === reached ? "current" : "todo";
          return <li key={s} data-state={st}>{TERMINAL[state] && last ? TERMINAL[state] : s}</li>;
        })}
      </ol>
      {lines.length === 0
        ? <p className="empty">Each message shows up here: what was understood, which versioned rule decided, and which actions were confirmed by reading them back. The model interprets; rules decide; templates speak.</p>
        : <ul className="trail">{lines.map((l, i) => <li key={i}><span className="kind" data-tone={l.tone}>{l.kind}</span><div>{l.text}</div></li>)}</ul>}
    </div>
  );
}

// ---- Operations ----------------------------------------------------------------------------------------
const EVAL = [
  { label: "Correct outcome", base: "56/84", prop: "84/84" },
  { label: "Safe automated resolution", base: "44%", prop: "71%" },
  { label: "Unsafe outcomes", base: "13/84", prop: "0/84" },
  { label: "Missed escalations", base: "8/20", prop: "0/20" },
  { label: "Turn latency p50", base: "3.1 s", prop: "2.1 s" },
  { label: "Cost per safe resolution", base: "US$ 0.033", prop: "US$ 0.013" },
];

function Operations({ nlu }: { nlu: NluStatus | null }) {
  const [m, setM] = useState<Record<string, any> | null>(null);
  useEffect(() => { api.metrics().then(setM).catch(() => undefined); }, []);
  const tiles: [string, string][] = m ? [
    ["Replies", String(m.replies)], ["Handoffs", String(m.handoffs)], ["Agent actions", String(m.agent_actions ?? 0)],
    ["Verified actions", String(m.actions_verified)], ["AI calls", String(m.llm_calls)], ["Rule NLU turns", String(m.rule_nlu_turns ?? 0)],
    ["AI cost", `US$ ${Number(m.llm_cost_usd).toFixed(4)}`], ["Latency p50", `${Math.round(m.latency_ms_p50)} ms`],
  ] : [];
  return (
    <div className="ops">
      <section>
        <h3>This demo session</h3>
        <p className="muted small">Live counters for your workspace only. Language understanding: <strong>{nlu?.mode === "rules" ? "rule-based fallback" : "Claude Haiku 4.5"}</strong>{nlu?.reason ? ` (${nlu.reason.replaceAll("_", " ")})` : ""}.</p>
        <div className="tiles">{tiles.map(([k, v]) => <div key={k} className="tile"><span>{k}</span><strong>{v}</strong></div>)}</div>
      </section>
      <section>
        <h3>Held-out evaluation · test-v2</h3>
        <p className="muted small">42 scenarios from real dataset transactions × 2 runs = 84 simulated conversations per system. Offline simulation, not production.</p>
        <table className="eval-table">
          <thead><tr><th /><th>Prompt-only LLM baseline</th><th>This system</th></tr></thead>
          <tbody>{EVAL.map((r) => <tr key={r.label}><th>{r.label}</th><td>{r.base}</td><td><strong>{r.prop}</strong></td></tr>)}</tbody>
        </table>
        <p className="muted small">Zero observed unsafe outcomes in 84 conversations does not prove zero risk. Full reports in <span className="mono">eval/results/</span>.</p>
      </section>
    </div>
  );
}

// ---- Console -------------------------------------------------------------------------------------------
export function BankConsole(props: {
  tab: BankTab; onTab: (t: BankTab) => void; queue: QueueItem[]; selected: string | null; onSelect: (r: string) => void;
  onQueueChanged: () => void; events: TraceEvent[]; reply: Reply | null; nlu: NluStatus | null;
}) {
  const fresh = props.queue.filter((q) => q.status === "new").length;
  return (
    <div className="console">
      <nav className="console-tabs" role="tablist">
        <button role="tab" aria-selected={props.tab === "queue"} onClick={() => props.onTab("queue")}>Queue{fresh > 0 && <span className="badge badge-hot">{fresh}</span>}</button>
        <button role="tab" aria-selected={props.tab === "decisions"} onClick={() => props.onTab("decisions")}>Decisions</button>
        <button role="tab" aria-selected={props.tab === "operations"} onClick={() => props.onTab("operations")}>Operations</button>
      </nav>
      <div className="console-body">
        {props.tab === "queue" && <Queue items={props.queue} selected={props.selected} onSelect={props.onSelect} onChanged={props.onQueueChanged} />}
        {props.tab === "decisions" && <Decisions events={props.events} reply={props.reply} />}
        {props.tab === "operations" && <Operations nlu={props.nlu} />}
      </div>
    </div>
  );
}
