"use client";
import type { Reply, TraceEvent } from "@/lib/api";

const STEPS = ["Transaction", "Reason", "Evidence", "Policy check", "Confirmation", "Verified action"];
const PROGRESS: Record<string, number> = { START: 0, IDENTIFY_TXN: 0, CLASSIFY: 1, COLLECT_EVIDENCE: 2, CONFIRM: 4, DONE: 6 };
const TERMINAL: Record<string, string> = { INELIGIBLE: "Not eligible", HANDOFF: "Sent to a person", CANCELLED: "Closed, no action" };

function Steps({ state }: { state: string }) {
  const terminal = TERMINAL[state];
  const reached = PROGRESS[state] ?? 0;
  return (
    <div className="steps" role="list" aria-label="Case progress">
      {STEPS.map((label, i) => {
        let s: string = i < reached ? "done" : i === reached ? "current" : "todo";
        if (state === "DONE") s = i === STEPS.length - 1 ? "end" : "done";
        if (terminal && i === STEPS.length - 1) s = "end";
        return (
          <div key={label} className="step" data-state={s} role="listitem">
            {terminal && i === STEPS.length - 1 ? terminal : label}
          </div>
        );
      })}
    </div>
  );
}

function Chips({ items, tone }: { items: string[]; tone?: "ok" | "warn" }) {
  return <>{items.map((x) => <span key={x} className={`chip ${tone ? `chip-${tone}` : ""}`}>{x}</span>)}</>;
}

function Row({ kind, tone, children }: { kind: string; tone?: "action" | "risk"; children: React.ReactNode }) {
  return (
    <li>
      <span className="kind" data-tone={tone}>{kind}</span>
      <div>{children}</div>
    </li>
  );
}

function renderEvent(e: TraceEvent, i: number) {
  const d = e.data;
  switch (e.kind) {
    case "customer_message":
      return (
        <Row key={i} kind="Customer said" tone={d.injection_flags?.length ? "risk" : undefined}>
          <div>{d.text}</div>
          {d.pii?.length > 0 && <div className="muted">Masked before the model: <Chips items={d.pii} /></div>}
          {d.injection_flags?.length > 0 && <div>Injection signals: <Chips items={d.injection_flags} tone="warn" /></div>}
        </Row>
      );
    case "nlu": {
      const r = d.result;
      const fields = Object.entries(r).filter(([k, v]) =>
        v !== null && v !== false && v !== "" && !["intent", "language", "summary", "reason_confidence", "reason_code"].includes(k));
      return (
        <Row key={i} kind="Understood">
          <div>
            <span className="chip">{r.intent}</span>
            {r.reason_code && <span className="chip">{r.reason_code} · {Number(r.reason_confidence).toFixed(2)}</span>}
            <span className="chip">{r.language}</span>
          </div>
          {fields.length > 0 && <div className="muted">{fields.map(([k, v]) => `${k}: ${v}`).join(" · ")}</div>}
          <div className="muted">{d.usage.model} · {Math.round(d.usage.latency_ms)} ms · US$ {d.usage.cost_usd.toFixed(4)}</div>
        </Row>
      );
    }
    case "nlu_failed":
      return <Row key={i} kind="Model unavailable" tone="risk">{d.error}{d.breaker_open ? " — circuit open" : ""}</Row>;
    case "transaction_identified":
      return <Row key={i} kind="Transaction found"><Chips items={[d.transaction_id]} /></Row>;
    case "transaction_lookup_rejected":
      return <Row key={i} kind="Lookup refused" tone="risk">{d.transaction_id} is not available to this session ({d.error}). The customer sees the same answer either way.</Row>;
    case "clarify":
      return <Row key={i} kind="Asked for">{d.fields.join(", ")} <span className="muted">(attempt {d.attempt} of 2)</span></Row>;
    case "policy_decision":
    case "block_card_policy":
      return (
        <Row key={i} kind={e.kind === "policy_decision" ? "Policy" : "Card-block policy"} tone="action">
          <strong>{d.decision}</strong> <Chips items={d.rule_ids} /> <span className="muted">{d.policy_version}</span>
          {d.missing_evidence?.length > 0 && <div className="muted">Missing: {d.missing_evidence.join(", ")}</div>}
        </Row>
      );
    case "confirm_requested":
      return <Row key={i} kind="Waiting">Customer confirmation required before any action.</Row>;
    case "action":
      return (
        <Row key={i} kind="Action" tone="action">
          <Chips items={[`${d.action}${d.ref ? ` ${d.ref}` : ""}`]} tone={d.status === "verified" ? "ok" : "warn"} />
          <span className="muted">{d.status === "verified" ? "confirmed by reading it back" : "failed, not reported as done"}</span>
        </Row>
      );
    case "handoff":
      return <Row key={i} kind="Handoff" tone="risk"><Chips items={d.reason_for_handoff} /> <span className="mono">{d.case_ref}</span></Row>;
    case "auth_failed":
      return <Row key={i} kind="Session refused" tone="risk">{d.reason}</Row>;
    case "proactive_alert":
      return <Row key={i} kind="Fraud alert">{d.transaction_id} · score {d.fraud_score}</Row>;
    case "done":
      return <Row key={i} kind="Outcome" tone="action">Case <span className="mono">{d.case_id}</span> opened and verified.</Row>;
    case "customer_declined":
    case "closed":
      return <Row key={i} kind="Outcome">Closed without action{d.reason ? ` (${d.reason})` : ""}.</Row>;
    default:
      return null;
  }
}

export function Inspector({ events, reply }: { events: TraceEvent[]; reply: Reply | null }) {
  return (
    <div>
      <h2>What the bank decided</h2>
      <Steps state={reply?.state ?? "START"} />
      {events.length === 0 ? (
        <p className="empty">Each message shows up here: what was understood, which policy rule decided, and which actions were confirmed. The model only interprets; the decisions come from versioned rules.</p>
      ) : (
        <ul className="trail">{events.map(renderEvent)}</ul>
      )}
    </div>
  );
}
