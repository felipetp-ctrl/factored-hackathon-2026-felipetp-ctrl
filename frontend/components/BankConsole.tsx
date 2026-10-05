"use client";
import INSIGHTS from "@/lib/insights.json";
import { Fragment, useEffect, useState } from "react";
import { api, type Alert, type CaseRow, type NluStatus, type PqrLetter, type PqrResult, type QueueItem, type TraceEvent } from "@/lib/api";
import { dayTime, money } from "@/lib/format";

export type BankTab = "cases" | "letters" | "alerts" | "insights" | "numbers";

const REASONS = ["FRAUD_CNP", "FRAUD_CP", "DUPLICATE", "INCORRECT_AMOUNT", "NOT_RECEIVED", "CANCELLED_RECURRING"];
const REASON_EN: Record<string, string> = {
  FRAUD_CNP: "Unrecognised charge", FRAUD_CP: "Lost or stolen card", DUPLICATE: "Duplicate charge",
  INCORRECT_AMOUNT: "Wrong amount", NOT_RECEIVED: "Not received", CANCELLED_RECURRING: "Cancelled subscription",
};
const HANDOFF_EN: Record<string, string> = {
  amount_above_threshold: "Amount above US$ 450", repeat_complainer: "Repeat complainer", dispute_velocity: "Many disputes in 30 days",
  very_negative_sentiment: "Very upset customer", regulatory_or_legal_threat: "Regulator or legal threat",
  implausible_amount_claim: "Correct amount under half the charge",
  low_classifier_confidence: "Unclear reason", customer_requested_human: "Asked for a person",
  suspicious_access: "Asked for another customer's charge", invalid_transaction_references: "Invalid references",
  clarification_exhausted: "Could not clarify in 2 tries", tool_failure: "Bank system failed", verification_failed: "Action not verified",
  nlu_unavailable: "Language service down", async_missing_info: "Letter is missing information",
};
const FIELD_EN: Record<string, string> = {
  transaction: "which charge", reason_code: "dispute reason", card_in_possession: "card in possession",
  recognizes_merchant: "recognises merchant", duplicate_transaction_id: "the other charge", expected_amount: "correct amount",
  expected_delivery_date: "delivery date", contacted_merchant: "contacted merchant", cancellation_date: "cancellation date",
};
const FROM: Record<string, string> = { chat: "App", pqr: "Letter", proactive: "Fraud alert" };
const FROM_LONG: Record<string, string> = { chat: "Started in the app", pqr: "Arrived as a written complaint", proactive: "Started by a fraud alert" };

export const PATH: { id: keyof CaseRow["stages"]; label: string; ai?: boolean }[] = [
  { id: "understand", label: "Understand", ai: true },
  { id: "decide", label: "Decide" },
  { id: "confirm", label: "Confirm" },
  { id: "act", label: "Act" },
  { id: "verify", label: "Verify" },
];
const PATH_HINT: Record<string, string> = {
  understand: "AI turns the customer's words into fields",
  decide: "Written rules decide, never the AI",
  confirm: "Nothing happens without the customer's yes",
  act: "Bank systems open the dispute or block the card",
  verify: "Each action is read back before anyone is told",
};

const handoffText = (codes: string) => codes.split(", ").filter(Boolean).map((r) => HANDOFF_EN[r] ?? r.replaceAll("_", " ")).join(", ");
const isPerson = (c: CaseRow) => c.outcome === "person" || c.outcome === "person_done";

// ---- audit trail lines -----------------------------------------------------------------------------------------
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



// ---- the path of one case ----------------------------------------------------------------------------
function stepDetail(c: CaseRow, id: string): string {
  const st = c.stages[id as keyof CaseRow["stages"]];
  if (st.status === "pending") return "";
  if (id === "understand" && c.reason_code) return REASON_EN[c.reason_code] ?? c.reason_code;
  if (id === "decide" && st.detail) {
    const [decision, rules] = st.detail.split(" · ");
    return decision === "eligible" ? "Eligible under the policy" : decision === "handoff" ? "Needs a person" : decision === "ineligible" ? `Not eligible (${rules})` : decision;
  }
  if (id === "confirm") return c.channel === "pqr" ? "The letter is the request" : st.status === "done" ? "Customer said yes" : "Waiting for the customer";
  if (id === "act") return st.detail.replaceAll("open_dispute", "Dispute opened").replaceAll("block_card", "card blocked").replace(" + ", ", ");
  if (id === "verify") return st.status === "done" ? "Confirmed in the system" : "Could not confirm";
  return st.detail;
}

export function CasePath({ c }: { c: CaseRow }) {
  return (
    <ol className="path" aria-label="What happened to this case">
      {PATH.map((p) => {
        const st = c.stages[p.id].status;
        return (
          <li key={p.id} data-status={st} data-ai={p.ai ? "true" : undefined} title={PATH_HINT[p.id]}>
            <span className="path-dot" aria-hidden />
            <span className="path-label">{p.label}{p.ai && <span className="path-ai">AI</span>}</span>
            <span className="path-detail">{stepDetail(c, p.id)}</span>
          </li>
        );
      })}
    </ol>
  );
}

function outcomeLine(c: CaseRow): { tone: string; text: string } {
  if (c.outcome === "resolved") return { tone: "ok", text: `Resolved without a person. Dispute ${c.case_id} is open and confirmed.` };
  if (c.outcome === "person_done") return { tone: "ok", text: `Handled by an agent${c.case_id ? `: dispute ${c.case_id} opened` : ""}.` };
  if (c.outcome === "person") return { tone: "person", text: `Needs a person: ${handoffText(c.outcome_detail)}.` };
  if (c.outcome === "closed") return { tone: "muted", text: `Closed with no dispute${c.outcome_detail ? `: ${c.outcome_detail.replaceAll("_", " ")}` : ""}.` };
  return { tone: "active", text: "In progress with the customer." };
}

// ---- what an agent does with a case that needs a person ------------------------------------------------
function AgentPanel({ item, onDone }: { item: QueueItem; onDone: () => void }) {
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
  return (
    <section className="agent">
      <h4>For the agent</h4>
      <dl className="facts">
        <dt>Customer wants</dt><dd>{item.customer_request_summary || "Not stated yet"}</dd>
        <dt>Checked facts</dt>
        <dd>{item.verified_facts.length ? item.verified_facts.map((f) => <div key={f.source}>{f.fact}</div>) : "None yet. The charge was not identified."}</dd>
        {item.open_questions.length > 0 && <><dt>Still to ask</dt><dd>{item.open_questions.map((q) => FIELD_EN[q] ?? q).join(", ")}</dd></>}
      </dl>
      {item.status === "new" ? (
        <div className="agent-act">
          <select id={`reason-${item.case_ref}`} aria-label="Reason" value={reason} onChange={(e) => setReason(e.target.value)}>
            {REASONS.map((r) => <option key={r} value={r}>{REASON_EN[r]}</option>)}
          </select>
          <input id={`note-${item.case_ref}`} aria-label="Note" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note, e.g. called the customer" />
          <button className="btn btn-primary" onClick={() => act("open_dispute")} disabled={busy || !item.transaction_id}>Open dispute</button>
          <button className="btn" onClick={() => act("close")} disabled={busy}>Close</button>
          {!item.transaction_id && <p className="muted small">No confirmed charge yet: contact the customer first, or close the case.</p>}
          {error && <p className="error" role="alert">{error}</p>}
        </div>
      ) : (
        <p className="done-note">{item.resolution?.action === "open_dispute" ? `Dispute ${item.resolution.case_id} opened by the agent and confirmed.` : "Closed by the agent."}</p>
      )}
      <details className="more">
        <summary>More details</summary>
        <dl className="facts">
          <dt>Why a person</dt><dd>{item.reason_for_handoff.map((r) => HANDOFF_EN[r] ?? r).join(", ")}{item.policy_decision && ` (${item.policy_decision.rule_ids.join(", ")}, ${item.policy_decision.policy_version})`}</dd>
          <dt>Actions taken</dt><dd>{item.actions_taken.length ? item.actions_taken.map((a) => `${a.action} ${a.status}`).join(", ") : "None"}</dd>
          {Object.entries(item.risk_signals).filter(([, v]) => v !== null).map(([k, v]) => <Fragment key={k}><dt>{k.replaceAll("_", " ")}</dt><dd>{Array.isArray(v) ? v.join(", ") : String(v)}</dd></Fragment>)}
        </dl>
        <p className="muted small">The agent receives checked facts and the rule that applied, not the conversation.</p>
      </details>
    </section>
  );
}

// ---- case drawer ----------------------------------------------------------------------------------------
function CaseDrawer({ c, queue, onClose, onChanged }: { c: CaseRow; queue: QueueItem[]; onClose: () => void; onChanged: () => void }) {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  useEffect(() => { api.trace(c.trace_id).then(setEvents).catch(() => setEvents([])); }, [c.trace_id, c.updated_at]);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  const pkg = c.case_ref ? queue.find((q) => q.case_ref === c.case_ref) : undefined;
  const lines = events.map(line).filter(Boolean) as NonNullable<ReturnType<typeof line>>[];
  const out = outcomeLine(c);
  const t = c.transaction;
  return (
    <>
      <div className="scrim" onClick={onClose} aria-hidden />
      <aside className="drawer" role="dialog" aria-label="Case">
        <header className="drawer-head">
          <div>
            <p className="muted small">{FROM_LONG[c.channel]}</p>
            <h3>{c.customer_name ?? "Unknown customer"}</h3>
            <p>{t ? `${t.merchant ?? "No merchant name"}, ${money(t.amount, t.currency, "es")} ${t.currency}, ${dayTime(t.date).slice(0, 10)}` : "Charge not identified yet"}</p>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">×</button>
        </header>
        <CasePath c={c} />
        <p className={`outcome outcome-${out.tone}`}>{out.text}</p>
        {pkg && <AgentPanel item={pkg} onDone={onChanged} />}
        <details className="more">
          <summary>Audit trail ({lines.length})</summary>
          <ul className="trail">{lines.map((l, i) => <li key={i}><span className="kind" data-tone={l.tone}>{l.kind}</span><div>{l.text}</div></li>)}</ul>
          <p className="muted small">From the append-only audit log. It records what was read, decided and checked, never model reasoning.</p>
        </details>
      </aside>
    </>
  );
}

// ---- board ----------------------------------------------------------------------------------------------
const COLUMNS: { id: string; label: string; match: (c: CaseRow) => boolean }[] = [
  { id: "active", label: "In progress", match: (c) => c.outcome === "in_progress" },
  { id: "ok", label: "Resolved", match: (c) => c.outcome === "resolved" },
  { id: "person", label: "Needs a person", match: isPerson },
  { id: "muted", label: "Closed", match: (c) => c.outcome === "closed" },
];

function CaseCard({ c, onSelect }: { c: CaseRow; onSelect: () => void }) {
  const t = c.transaction;
  return (
    <button className="card" onClick={onSelect}>
      <span className="card-from" data-ch={c.channel}>{FROM[c.channel]}</span>
      <strong>{c.customer_name ?? "Unknown customer"}</strong>
      <span className="card-txn">{t ? `${t.merchant ?? "No merchant name"} · ${money(t.amount, t.currency, "es")} ${t.currency}` : "Charge not identified"}</span>
      {c.outcome === "person" && <span className="card-why">{handoffText(c.outcome_detail)}</span>}
      <span className="card-bar" aria-hidden>{PATH.map((p) => <i key={p.id} data-status={c.stages[p.id].status} />)}</span>
    </button>
  );
}

function Empty({ onTour }: { onTour: (id: string) => void }) {
  return (
    <div className="empty-state">
      <h3>No cases yet</h3>
      <p className="muted">Every dispute, however it arrives, takes the same five steps. Only the first one uses AI.</p>
      <ol className="path path-intro">
        {PATH.map((p) => (
          <li key={p.id} data-status="done" data-ai={p.ai ? "true" : undefined}>
            <span className="path-dot" aria-hidden />
            <span className="path-label">{p.label}{p.ai && <span className="path-ai">AI</span>}</span>
            <span className="path-detail">{PATH_HINT[p.id]}</span>
          </li>
        ))}
      </ol>
      <p className="muted">When a case needs judgement, it goes to a person with the facts already checked. Start one:</p>
      <div className="starts">
        <button className="btn btn-primary" onClick={() => onTour("written_complaints")}>Process written complaints</button>
        <button className="btn" onClick={() => onTour("fraud_alert")}>Answer a fraud alert</button>
        <button className="btn" onClick={() => onTour("normal")}>Dispute a purchase in the app</button>
      </div>
    </div>
  );
}

function Board({ cases, queue, selected, onSelect, onChanged, onTour }: {
  cases: CaseRow[]; queue: QueueItem[]; selected: string | null; onSelect: (id: string | null) => void; onChanged: () => void; onTour: (id: string) => void;
}) {
  const current = cases.find((c) => c.trace_id === selected) ?? null;
  if (!cases.length) return <Empty onTour={onTour} />;
  const cols = COLUMNS.filter((col) => col.id !== "muted" || cases.some(col.match));
  return (
    <>
      <div className="board" style={{ ["--cols" as string]: cols.length }}>
        {cols.map((col) => {
          const items = cases.filter(col.match);
          return (
            <section key={col.id} className="col" data-tone={col.id} aria-label={col.label}>
              <h4>{col.label}<span>{items.length}</span></h4>
              {items.map((c) => <CaseCard key={c.trace_id} c={c} onSelect={() => onSelect(c.trace_id)} />)}
            </section>
          );
        })}
      </div>
      {current && <CaseDrawer c={current} queue={queue} onClose={() => onSelect(null)} onChanged={onChanged} />}
    </>
  );
}

// ---- written complaints -------------------------------------------------------------------------------
const VIA_EN: Record<string, string> = { email: "Email", web: "Web form", branch: "Branch", app: "App form" };

function Letters({ results, setResults, onProcessed, onSeeCases }: {
  results: Record<string, PqrResult>; setResults: (r: Record<string, PqrResult>) => void; onProcessed: () => void; onSeeCases: () => void;
}) {
  const [letters, setLetters] = useState<PqrLetter[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.pqrInbox().then(setLetters).catch(() => setError("The inbox did not load. Reload the page.")); }, []);
  const processed = Object.keys(results).length > 0;
  const run = async () => {
    setBusy(true); setError(null);
    try {
      const out = await api.pqrProcess();
      setResults(Object.fromEntries(out.map((r) => [r.complaint_id, r])));
      onProcessed();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };
  return (
    <div className="letters">
      <div className="tab-head">
        <p className="muted">Letters with no one to answer questions. Each one is read, matched to a charge and decided like any other case.</p>
        {processed
          ? <button className="btn btn-primary" onClick={onSeeCases}>See the cases</button>
          : <button className="btn btn-primary" onClick={run} disabled={busy || letters.length === 0}>{busy ? "Processing…" : `Process ${letters.length} letters`}</button>}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <ul className="letter-list">
        {letters.map((l) => {
          const r = results[l.complaint_id];
          const tone = !r ? "" : r.action === "done" ? "ok" : "person";
          return (
            <li key={l.complaint_id}>
              <details className="letter">
                <summary>
                  <span className="letter-text">{l.description}</span>
                  <span className="letter-meta">{VIA_EN[l.received_via] ?? l.received_via}, {l.language === "pt" ? "Portuguese" : "Spanish"}</span>
                  {r && <span className={`pill-out pill-${tone}`}>{r.action === "done" ? "Resolved" : "Needs a person"}</span>}
                </summary>
                {r ? (
                  <div className="letter-body small">
                    <p>Read as <strong>{r.reading.reason_code ? REASON_EN[r.reading.reason_code] : "no clear reason"}</strong>
                      {Object.entries(r.reading.evidence).map(([k, v]) => `, ${FIELD_EN[k] ?? k}: ${v}`).join("")}
                      {r.reading.regulatory_threat && ", mentions a regulator"}.</p>
                    <p>{r.action === "done" ? `Dispute ${r.case_id} opened and confirmed. The card is not blocked: that needs the customer's own yes.`
                      : `${r.handoff_reasons.map((x) => HANDOFF_EN[x] ?? x).join(", ")}.${r.open_questions.length ? ` Still to ask: ${r.open_questions.map((q) => FIELD_EN[q] ?? q).join(", ")}.` : ""}${r.candidate_transactions.length ? ` ${r.candidate_transactions.length} possible charges attached.` : ""}`}</p>
                  </div>
                ) : <p className="letter-body small muted">Process the letters to see how this one is read and decided.</p>}
              </details>
            </li>
          );
        })}
      </ul>
      <details className="more">
        <summary>About these letters</summary>
        <p className="small muted">Written by the team about real charges in the demo sample, because the dataset&apos;s complaint texts are five fixed templates.
          Across all 13,580 real dispute complaints, only 15.8% point to exactly one charge, so most letters need a person or a question to the customer.
          They are read by the free reader (rules plus our trained classifier), with no AI cost.</p>
      </details>
    </div>
  );
}

// ---- fraud alerts ---------------------------------------------------------------------------------------
function Alerts({ onOpenCustomer }: { onOpenCustomer: (id: string) => void }) {
  const [items, setItems] = useState<(Alert & { customer_id: string })[] | null>(null);
  useEffect(() => { api.fraudAlerts().then(setItems).catch(() => setItems([])); }, []);
  return (
    <div className="letters">
      <div className="tab-head">
        <p className="muted">The bank asks first. These charges looked risky, so the customer gets “Do you recognise this purchase?” in the app. A “no” starts a case.</p>
      </div>
      {items === null ? <p className="muted">Loading…</p> : items.length === 0 ? <p className="muted">No risky charges right now.</p> : (
        <ul className="alert-list">
          {items.slice(0, 8).map((a) => (
            <li key={a.transaction_id}>
              <span className="risk-bar" style={{ ["--s" as string]: `${Math.min(100, Number(a.fraud_score))}%` }} title={`Fraud score ${Number(a.fraud_score).toFixed(0)}`} />
              <span className="alert-txn"><strong>{a.merchant_name ?? "No merchant name"}</strong> {money(a.amount, a.currency, "es")} {a.currency}</span>
              <span className="muted small">{dayTime(a.transaction_date).slice(0, 10)}</span>
              <button className="link-btn" onClick={() => onOpenCustomer(a.customer_id)}>Open customer&apos;s app</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---- insights -----------------------------------------------------------------------------------------
// Numbers computed by `python -m dispute_ops.pipeline.insights` from the organizer data and the evaluation results.
function Bars({ rows, max, unit = "" }: { rows: { label: string; value: number; strong?: boolean }[]; max: number; unit?: string }) {
  return (
    <div className="ibars">
      {rows.map((r) => (
        <div key={r.label} className="ibar" title={`${r.label}: ${r.value.toLocaleString("en-US")}${unit}`}>
          <span className="ibar-label">{r.label}</span>
          <span className="ibar-track"><i style={{ width: `${Math.max(2, (100 * r.value) / max)}%` }} data-strong={r.strong || undefined} /></span>
          <span className="ibar-value">{r.value.toLocaleString("en-US")}{unit}</span>
        </div>
      ))}
    </div>
  );
}

function Insights() {
  const d = INSIGHTS;
  const week = Object.entries(d.weekday.counts).map(([label, value]) => ({ label, value: value as number }));
  const pct = (x: number) => `${Math.round(100 * x)}%`;
  const items: { k: string; headline: string; figure: string; body: React.ReactNode; action: string }[] = [
    { k: "week", headline: "Disputes follow the working week, not the hour", figure: `${d.weekday.ratio}× Sunday`,
      body: <Bars rows={week} max={Math.max(...week.map((w) => w.value))} />,
      action: "Staff the human queue on a weekly curve: Tuesday to Friday. Hours of the day are flat (tested)." },
    { k: "rate", headline: "Every country and segment disputes at the same rate", figure: "~90 per 1,000",
      body: <Bars rows={[...d.rates.country, ...d.rates.segment].map((g) => ({ label: g.group, value: g.per_1000 }))} max={100} />,
      action: `No group needs its own risk rule (country p = ${d.rates.p_country}, segment p = ${d.rates.p_segment}). One amount rule in US$ for everyone.` },
    { k: "fraud", headline: "Fraud alerts: coverage is the lever, not the threshold", figure: `${pct(d.fraud.no_score_share)} unscored`,
      body: <Bars rows={[{ label: "score 30 or more", value: Math.round(d.fraud.fraud * (1 - d.fraud.no_score_share)), strong: true }, { label: "no usable score", value: Math.round(d.fraud.fraud * d.fraud.no_score_share) }]} max={d.fraud.fraud} />,
      action: `At threshold ${d.fraud.threshold}: ${d.fraud.alerts_per_day} alerts a day, ${pct(d.fraud.precision)} are fraud, ${pct(d.fraud.recall)} of fraud caught; no threshold beats ${pct(d.fraud.max_recall)}. Score the unscored; the customer's own dispute catches the rest.` },
    { k: "funnel", headline: "Conversations are lost at the charge, not at the reason", figure: `${d.funnel.turns_median} messages to a case`,
      body: <Bars rows={d.funnel.steps.map((s, i) => ({ label: s.label, value: s.n, strong: i === d.funnel.steps.length - 1 }))} max={d.funnel.steps[0].n} />,
      action: "Improve charge search (amount and date tolerance, merchant aliases) before the language reader. Without the service, the first answer takes 37 hours." },
    { k: "status", headline: "The complaint status is a label, not a backlog", figure: `${pct(d.status.buckets[d.status.buckets.length - 1].share)} of 2-year-old still “open”`,
      body: <Bars rows={d.status.buckets.map((b) => ({ label: b.age, value: Math.round(100 * b.share) }))} max={100} unit="%" />,
      action: "In a working queue the open share falls with age; here it does not (resolution times recorded on the same complaints say none should be open after a month). The bank's status cannot measure the backlog, so the pilot measures the case system's own timestamps." },
    { k: "saving", headline: "The saving depends most on back-office time, which nobody has measured", figure: `≈ US$ ${d.saving.base.toLocaleString("en-US")} a year`,
      body: <p className="muted small">Projection, not a measurement. Moving “{d.saving.top_driver}” across its range moves the saving from US$ {d.saving.range[0].toLocaleString("en-US")} to US$ {d.saving.range[1].toLocaleString("en-US")}.</p>,
      action: "Measure back-office minutes per case in a pilot before promising savings." },
  ];
  return (
    <div className="insights">
      <p className="muted small">What the bank&apos;s data says about running this service. Each pattern is tested before it is trusted; open one to see the numbers.</p>
      {items.map((it) => (
        <details key={it.k} className="insight">
          <summary><span>{it.headline}</span><strong>{it.figure}</strong></summary>
          <div className="insight-body">{it.body}<p className="insight-action">{it.action}</p></div>
        </details>
      ))}
      <p className="muted small">Organizer data (synthetic, 3 years) and offline tests; details in docs/analysis/operating-insights.md.</p>
    </div>
  );
}

// ---- results ------------------------------------------------------------------------------------------
function Operations({ nlu }: { nlu: NluStatus | null }) {
  const [m, setM] = useState<Record<string, any> | null>(null);
  useEffect(() => { api.metrics().then(setM).catch(() => undefined); }, []);
  const tiles: [string, string][] = m ? [
    ["Actions confirmed", String(m.actions_verified)], ["Sent to a person", String(m.handoffs)],
    ["AI calls", String(m.llm_calls)], ["AI cost", `US$ ${Number(m.llm_cost_usd).toFixed(3)}`],
  ] : [];
  return (
    <div className="ops">
      <section>
        <h3>Your demo so far</h3>
        <div className="tiles">{tiles.map(([k, v]) => <div key={k} className="tile"><strong>{v}</strong><span>{k}</span></div>)}</div>
        <p className="muted small">Reading customers&apos; words: {nlu?.mode === "rules" ? "free rule-based reader (AI unavailable)" : "Claude Haiku 4.5, with the free reader as backup"}.</p>
      </section>
      <section>
        <h3>Offline tests: where it breaks</h3>
        <p className="muted small">36 held-out customers who remember a charge vaguely (“about 90 thousand”, “last week”), run twice on the real Claude API. Simulated customers, not production.</p>
        <table className="eval-table">
          <thead><tr><th /><th>AI chatbot</th><th>This system</th></tr></thead>
          <tbody>
            <tr><th>Correct outcome</th><td>49 of 72</td><td><strong>65 of 72</strong></td></tr>
            <tr><th>Unsafe outcomes</th><td>11 of 72</td><td><strong>4 of 72</strong></td></tr>
            <tr><th>Correct outcome, free reader (no AI)</th><td>—</td><td><strong>30 of 36</strong></td></tr>
          </tbody>
        </table>
        <p className="muted small">Two of the four unsafe outcomes were one bug (“yes, but I want a real person” opened the case); fixed since.</p>
        <p className="muted small">Written complaints and fraud-alert answers, held out, no AI calls:</p>
        <table className="eval-table">
          <thead><tr><th /><th>Keyword rules</th><th>This system</th></tr></thead>
          <tbody>
            <tr><th>Letters handled correctly</th><td>19 of 24</td><td><strong>23 of 24</strong></td></tr>
            <tr><th>Alert answers handled correctly</th><td>17 of 18</td><td><strong>17 of 18</strong></td></tr>
            <tr><th>Unsafe outcomes</th><td>0</td><td><strong>0</strong></td></tr>
          </tbody>
        </table>
        <details className="more">
          <summary>Compared with a plain AI chatbot</summary>
          <table className="eval-table">
            <thead><tr><th /><th>AI chatbot</th><th>This system</th></tr></thead>
            <tbody>
              <tr><th>Unsafe outcomes</th><td>13 of 84</td><td><strong>0 of 84</strong></td></tr>
              <tr><th>Resolved safely without a person</th><td>44%</td><td><strong>71%</strong></td></tr>
              <tr><th>Missed escalations</th><td>8 of 20</td><td><strong>0 of 20</strong></td></tr>
              <tr><th>Cost per safe resolution</th><td>US$ 0.033</td><td><strong>US$ 0.013</strong></td></tr>
            </tbody>
          </table>
          <p className="muted small">42 scenarios from real transactions, 2 runs each, simulated customers. Zero unsafe outcomes in 84 conversations does not prove zero risk. Full reports in the repository.</p>
        </details>
      </section>
    </div>
  );
}


// ---- console ------------------------------------------------------------------------------------------
export function BankConsole(props: {
  tab: BankTab; onTab: (t: BankTab) => void; cases: CaseRow[]; queue: QueueItem[]; selected: string | null;
  onSelect: (id: string | null) => void; onQueueChanged: () => void; nlu: NluStatus | null;
  pqr: Record<string, PqrResult>; onPqr: (r: Record<string, PqrResult>) => void; onOpenCustomer: (id: string) => void;
  onTour: (id: string) => void;
}) {
  const waiting = props.cases.filter((c) => c.outcome === "person").length;
  const tabs: [BankTab, string][] = [["cases", "Cases"], ["letters", "Written complaints"], ["alerts", "Fraud alerts"], ["insights", "Insights"], ["numbers", "Results"]];
  return (
    <div className="console">
      <nav className="tabs" role="tablist">
        {tabs.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={props.tab === id} onClick={() => props.onTab(id)}>
            {label}{id === "cases" && waiting > 0 && <span className="badge badge-person" title="Cases waiting for a person">{waiting}</span>}
          </button>
        ))}
      </nav>
      {props.tab === "cases" && <Board cases={props.cases} queue={props.queue} selected={props.selected} onSelect={props.onSelect} onChanged={props.onQueueChanged} onTour={props.onTour} />}
      {props.tab === "letters" && <Letters results={props.pqr} setResults={props.onPqr} onProcessed={props.onQueueChanged} onSeeCases={() => props.onTab("cases")} />}
      {props.tab === "alerts" && <Alerts onOpenCustomer={props.onOpenCustomer} />}
      {props.tab === "insights" && <Insights />}
      {props.tab === "numbers" && <Operations nlu={props.nlu} />}
    </div>
  );
}
