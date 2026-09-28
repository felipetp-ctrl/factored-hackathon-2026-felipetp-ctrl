"use client";
import { useEffect, useState } from "react";
import { api, type Alert, type CaseRow, type NluStatus, type PqrLetter, type PqrResult, type QueueItem, type TraceEvent } from "@/lib/api";
import { dayTime, FLAG, money } from "@/lib/format";
import { humanize, STAGES } from "@/components/Workflow";

export type BankTab = "cases" | "complaints" | "alerts" | "operations";

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

const CHANNEL_EN: Record<string, string> = { chat: "App", pqr: "Letter", proactive: "Alert" };
const COLUMNS: { id: string; label: string; match: CaseRow["outcome"][]; tone: string }[] = [
  { id: "in_progress", label: "In progress", match: ["in_progress"], tone: "active" },
  { id: "resolved", label: "Resolved automatically", match: ["resolved"], tone: "ok" },
  { id: "person", label: "With a person", match: ["person", "person_done"], tone: "person" },
  { id: "closed", label: "Closed, no action", match: ["closed"], tone: "muted" },
];

function CaseCard({ c, on, onSelect }: { c: CaseRow; on: boolean; onSelect: () => void }) {
  const t = c.transaction;
  return (
    <button className="card" aria-pressed={on} onClick={onSelect}>
      <span className="card-top">
        <span className={`chan chan-${c.channel}`}>{CHANNEL_EN[c.channel]}</span>
        <span className="muted small">{c.language.toUpperCase()} · {dayTime(c.updated_at)}</span>
      </span>
      <strong className="card-name">{c.customer_name ?? "Unknown customer"} {c.country && <span className="muted small">{FLAG[c.country] ?? c.country}</span>}</strong>
      <span className="card-txn">{t ? <>{t.merchant ?? "No merchant name"} · {money(t.amount, t.currency, "es")} {t.currency}</> : <span className="muted">charge not identified</span>}</span>
      <span className="card-reason">{c.reason_code ? REASON_EN[c.reason_code] ?? c.reason_code : <span className="muted">reason not known</span>}</span>
      <span className="card-bar" aria-label="Steps reached">
        {STAGES.map((s) => <i key={s.id} data-status={c.stages[s.id].status} title={`${s.label}: ${c.stages[s.id].status}`} />)}
      </span>
      {(c.outcome === "person" || c.outcome === "person_done" || c.outcome === "closed") && c.outcome_detail &&
        <span className="card-why">{c.outcome_detail.split(", ").map((r) => HANDOFF_EN[r] ?? humanize(r)).join(" · ")}</span>}
    </button>
  );
}

function CaseDetail({ c, queue, onChanged }: { c: CaseRow; queue: QueueItem[]; onChanged: () => void }) {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  useEffect(() => { api.trace(c.trace_id).then(setEvents).catch(() => setEvents([])); }, [c.trace_id, c.updated_at]);
  const pkg = c.case_ref ? queue.find((q) => q.case_ref === c.case_ref) : undefined;
  const lines = events.map(line).filter(Boolean) as NonNullable<ReturnType<typeof line>>[];
  return (
    <article className="detail">
      <header className="detail-head">
        <div>
          <span className={`chan chan-${c.channel}`}>{CHANNEL_EN[c.channel]}</span>
          <h3>{c.customer_name ?? "Unknown customer"} · {c.transaction ? `${c.transaction.merchant ?? "no merchant"} ${money(c.transaction.amount, c.transaction.currency, "es")} ${c.transaction.currency}` : "charge not identified yet"}</h3>
          <p className="muted small mono">{c.trace_id}{c.case_id && <> · case {c.case_id}</>}</p>
        </div>
      </header>
      <ol className="detail-steps">
        {STAGES.map((s) => (
          <li key={s.id} data-status={c.stages[s.id].status}>
            <span className={`wf-who wf-who-${s.whoTone}`}>{s.who}</span>
            <strong>{s.label}</strong>
            <span>{c.stages[s.id].detail || { done: "done", active: "in progress", stopped: "stopped here", pending: "not reached" }[c.stages[s.id].status]}</span>
          </li>
        ))}
      </ol>
      {pkg && <Package item={pkg} onDone={onChanged} />}
      <details className="detail-trail" open={!pkg}>
        <summary>Audit trail · {lines.length} records</summary>
        {lines.length === 0 ? <p className="empty">No records yet.</p>
          : <ul className="trail">{lines.map((l, i) => <li key={i}><span className="kind" data-tone={l.tone}>{l.kind}</span><div>{l.text}</div></li>)}</ul>}
        <p className="muted small">Built from the append-only audit log: what was read, which rule decided, what was done and how it was checked. There is no model reasoning in it.</p>
      </details>
    </article>
  );
}

function CaseBoard({ cases, queue, selected, onSelect, onChanged }: {
  cases: CaseRow[]; queue: QueueItem[]; selected: string | null; onSelect: (id: string) => void; onChanged: () => void;
}) {
  const current = cases.find((c) => c.trace_id === selected) ?? null;
  if (!cases.length) return (
    <div className="empty board-empty">
      <p><strong>No cases yet.</strong> Start one of three ways:</p>
      <ul>
        <li><strong>Written complaints</strong> tab: process six letters. No typing needed.</li>
        <li><strong>Fraud alert</strong> scenario: the customer answers the bank&apos;s alert in the app.</li>
        <li>On the phone, tap <strong>“No reconozco”</strong> on a purchase.</li>
      </ul>
    </div>
  );
  return (
    <div className="board-wrap">
      <div className="board">
        {COLUMNS.map((col) => {
          const items = cases.filter((c) => col.match.includes(c.outcome));
          return (
            <section key={col.id} className={`col col-${col.tone}`} aria-label={col.label}>
              <h4>{col.label} <span className="col-n">{items.length}</span></h4>
              {items.map((c) => <CaseCard key={c.trace_id} c={c} on={c.trace_id === selected} onSelect={() => onSelect(c.trace_id)} />)}
            </section>
          );
        })}
      </div>
      {current ? <CaseDetail c={current} queue={queue} onChanged={onChanged} />
        : <p className="muted small">Click a case to see its steps, the handoff package and the audit trail.</p>}
    </div>
  );
}

// ---- Fraud alerts --------------------------------------------------------------------------------------
function Alerts({ onOpenCustomer }: { onOpenCustomer: (id: string) => void }) {
  const [items, setItems] = useState<(Alert & { customer_id: string })[] | null>(null);
  useEffect(() => { api.fraudAlerts().then(setItems).catch(() => setItems([])); }, []);
  return (
    <div className="pqr">
      <div>
        <h3>Fraud alerts</h3>
        <p className="muted small">The bank writes first. Recent charges with a fraud score of 35 or more and no dispute get a question in the customer&apos;s app: “Do you recognise this purchase?”
          A “no” opens the same case flow as any other channel. The threshold was lowered from 80 to 35 after a label audit (ADR-020): the score is the dataset&apos;s only fraud signal.</p>
      </div>
      {items === null ? <p className="muted">Loading…</p> : items.length === 0 ? <p className="empty">No alerts in the look-back window.</p> : (
        <table className="eval-table alerts-table">
          <thead><tr><th>Customer</th><th>Charge</th><th>Score</th><th>When</th><th /></tr></thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.transaction_id}>
                <td className="mono">{a.customer_id}</td>
                <td>{a.merchant_name ?? "No merchant name"} · {money(a.amount, a.currency, "es")} {a.currency} <span className="muted">≈ US$ {Number(a.amount_usd).toFixed(0)}</span></td>
                <td><span className="score" style={{ ["--s" as string]: `${Math.min(100, Number(a.fraud_score))}%` }}>{Number(a.fraud_score).toFixed(0)}</span></td>
                <td className="muted">{dayTime(a.transaction_date)}</td>
                <td><button className="btn btn-small" onClick={() => onOpenCustomer(a.customer_id)}>Open their phone</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
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

// ---- Written complaints (PQR) ---------------------------------------------------------------------------
const VIA_EN: Record<string, string> = { email: "Email", web: "Web form", branch: "Branch", app: "App form" };

function Outcome({ r }: { r: PqrResult }) {
  if (r.action === "done") return (
    <p className="pqr-out pqr-ok"><strong>Dispute opened automatically</strong> · <span className="mono">{r.case_id}</span> · {r.rule_ids.join(", ")}
      <span className="muted"> · card not blocked: that needs the customer&apos;s explicit yes</span></p>
  );
  if (r.action === "handoff") return (
    <div className="pqr-out pqr-person">
      <p><strong>To a person</strong> · {r.handoff_reasons.map((x) => HANDOFF_EN[x] ?? x).join(", ")}</p>
      {r.open_questions.length > 0 && <p className="small">Still to find out: {r.open_questions.map((q) => FIELD_EN[q] ?? q).join(", ")}</p>}
      {r.candidate_transactions.length > 0 && <p className="small">{r.candidate_transactions.length} possible charges attached for the agent to check with the customer</p>}
    </div>
  );
  return <p className="pqr-out">{r.action} · {r.state}</p>;
}

function Complaints({ results, setResults, onProcessed }: {
  results: Record<string, PqrResult>; setResults: (r: Record<string, PqrResult>) => void; onProcessed: () => void;
}) {
  const [letters, setLetters] = useState<PqrLetter[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.pqrInbox().then(setLetters).catch(() => setError("Could not load the inbox.")); }, []);
  const processed = Object.keys(results).length > 0;
  const run = async () => {
    setBusy(true); setError(null);
    try {
      const out = await api.pqrProcess();
      setResults(Object.fromEntries(out.map((r) => [r.complaint_id, r])));
      onProcessed();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };
  const opened = Object.values(results).filter((r) => r.action === "done").length;
  return (
    <div className="pqr">
      <div className="pqr-head">
        <div>
          <h3>Written complaints</h3>
          <p className="muted small">Letters that arrive by email, web form or branch, with nobody to answer questions. The same case engine as the chat reads them, finds the charge and applies the policy.
            The reader here is the free one (rules + our trained classifier intent-v2), with no model cost.</p>
        </div>
        <button className="btn btn-primary" onClick={run} disabled={busy || processed || letters.length === 0}>{busy ? "Processing…" : processed ? "Processed" : `Process ${letters.length} complaints`}</button>
      </div>
      {processed && <p className="pkg-done">{opened} of {letters.length} opened without a person; {letters.length - opened} sent to a person with the data found and what is still missing. See them on the <strong>Cases</strong> tab.</p>}
      {error && <p className="error" role="alert">{error}</p>}
      <p className="pqr-real small"><strong>Why this matters.</strong> We ran the same charge matcher on all 13,580 real dispute complaints in the dataset: only <strong>15.8%</strong> point to exactly one charge, 63.5% fit several and 20.7% fit none. A letter alone rarely identifies the charge, so most go to a person with a shortlist, and the chat is where the bank can ask.</p>
      <ul className="pqr-list">
        {letters.map((l) => {
          const r = results[l.complaint_id];
          return (
            <li key={l.complaint_id} className="pqr-item">
              <div className="pqr-meta">
                <span className="mono">{l.complaint_id}</span>
                <span>{VIA_EN[l.received_via] ?? l.received_via} · {l.language.toUpperCase()} · {dayTime(l.created_at)}</span>
                <span className="muted">{l.claimed_amount ? `claims ${l.claimed_amount}` : "no amount"} · {l.affected_product_id ? "card given" : "no card given"}</span>
              </div>
              <blockquote className="pqr-letter">{l.description}</blockquote>
              {r && (
                <>
                  <p className="pqr-read small">
                    <span className="kind">Read</span>{" "}
                    {r.reading.reason_code ? <>{REASON_EN[r.reading.reason_code] ?? r.reading.reason_code} ({Math.round(r.reading.confidence * 100)}%)</> : "no reason found"}
                    {Object.entries(r.reading.evidence).map(([k, v]) => <span key={k} className="chip">{FIELD_EN[k] ?? k}: {v}</span>)}
                    {r.reading.regulatory_threat && <span className="chip chip-risk">regulator threat</span>}
                    {r.transaction_id && <> · charge <span className="mono">{r.transaction_id}</span></>}
                  </p>
                  <Outcome r={r} />
                </>
              )}
            </li>
          );
        })}
      </ul>
      <p className="muted small">Letters written by the team about real charges of the demo sample; the real complaint texts are five templates, so they cannot show reading. Processing runs once per demo; <em>Reset demo</em> brings the inbox back.</p>
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
      <section>
        <h3>Where it breaks · hard-v1</h3>
        <p className="muted small">test-v2 customers knew each charge to the cent. hard-v1 customers remember like people do (a rounded amount, &ldquo;last week&rdquo;, one word of the merchant). The set was frozen before any fix; blind test, 36 scenarios, one run. Customers were simulated by another model, and the Claude reader was a Claude subagent given the production prompt, not the API.</p>
        <table className="eval-table">
          <thead><tr><th /><th>Before fixes</th><th>After fixes</th></tr></thead>
          <tbody>
            <tr><th>Correct · free fallback</th><td>16/36</td><td><strong>30/36</strong></td></tr>
            <tr><th>Correct · Claude reader</th><td>24/36</td><td><strong>31/36</strong></td></tr>
            <tr><th>Unsafe · free fallback</th><td>1</td><td>3 (1 after a post-hoc fix)</td></tr>
          </tbody>
        </table>
      </section>
    </div>
  );
}

// ---- Console -------------------------------------------------------------------------------------------
export function BankConsole(props: {
  tab: BankTab; onTab: (t: BankTab) => void; cases: CaseRow[]; queue: QueueItem[]; selected: string | null;
  onSelect: (id: string) => void; onQueueChanged: () => void; nlu: NluStatus | null;
  pqr: Record<string, PqrResult>; onPqr: (r: Record<string, PqrResult>) => void; onOpenCustomer: (id: string) => void;
}) {
  const waiting = props.queue.filter((q) => q.status === "new").length;
  const tabs: [BankTab, string][] = [["cases", "Cases"], ["complaints", "Written complaints"], ["alerts", "Fraud alerts"], ["operations", "Operations"]];
  return (
    <div className="console">
      <nav className="console-tabs" role="tablist">
        {tabs.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={props.tab === id} onClick={() => props.onTab(id)}>
            {label}
            {id === "cases" && props.cases.length > 0 && <span className="badge">{props.cases.length}</span>}
            {id === "cases" && waiting > 0 && <span className="badge badge-hot" title="waiting for a person">{waiting}</span>}
          </button>
        ))}
      </nav>
      <div className="console-body">
        {props.tab === "cases" && <CaseBoard cases={props.cases} queue={props.queue} selected={props.selected} onSelect={props.onSelect} onChanged={props.onQueueChanged} />}
        {props.tab === "complaints" && <Complaints results={props.pqr} setResults={props.onPqr} onProcessed={props.onQueueChanged} />}
        {props.tab === "alerts" && <Alerts onOpenCustomer={props.onOpenCustomer} />}
        {props.tab === "operations" && <Operations nlu={props.nlu} />}
      </div>
    </div>
  );
}
