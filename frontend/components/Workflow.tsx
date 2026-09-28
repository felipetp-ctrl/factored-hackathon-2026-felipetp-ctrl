"use client";
import type { CaseRow, StageKey } from "@/lib/api";

/** How every case moves, whatever channel it came from. With a case selected, its own path lights up. */

const CHANNELS: { id: CaseRow["channel"]; label: string; sub: string }[] = [
  { id: "chat", label: "App", sub: "customer taps a purchase or writes" },
  { id: "pqr", label: "Written complaint", sub: "email, web form, branch" },
  { id: "proactive", label: "Fraud alert", sub: "the bank asks first" },
];

export const STAGES: { id: StageKey; label: string; who: string; whoTone: "ai" | "rule" | "person" | "system"; sub: string }[] = [
  { id: "understand", label: "Understand", who: "AI", whoTone: "ai", sub: "free text → fields" },
  { id: "decide", label: "Decide", who: "Written policy", whoTone: "rule", sub: "versioned rules, rule id" },
  { id: "confirm", label: "Confirm", who: "Customer", whoTone: "person", sub: "nothing runs without a yes" },
  { id: "act", label: "Act", who: "Bank tools", whoTone: "system", sub: "open dispute · block card" },
  { id: "verify", label: "Verify", who: "Read back", whoTone: "system", sub: "only verified is reported" },
];

const OUTCOMES: { id: string; match: CaseRow["outcome"][]; label: string; sub: string; tone: string }[] = [
  { id: "resolved", match: ["resolved"], label: "Resolved", sub: "no person needed", tone: "ok" },
  { id: "person", match: ["person", "person_done"], label: "To a person", sub: "with verified facts", tone: "person" },
  { id: "closed", match: ["closed"], label: "Closed", sub: "not eligible or no action", tone: "muted" },
];

export function Workflow({ cases, selected }: { cases: CaseRow[]; selected: CaseRow | null }) {
  const count = (k: StageKey) => cases.filter((c) => c.stages[k].status === "done").length;
  return (
    <section className="wf" aria-label="How a case moves">
      <div className="wf-head">
        <h2>How a case moves</h2>
        <p className="muted small">{selected
          ? <>Showing <strong>{selected.customer_name ?? "customer"}</strong>&apos;s case. Only the first step uses AI; everything after it is rules, the customer&apos;s yes and checked actions.</>
          : <>Three ways in, one path. Only the first step uses AI. Numbers are cases in this demo that passed each step. Click a case below to trace it.</>}</p>
      </div>
      <div className="wf-grid">
        <ol className="wf-col wf-in" aria-label="Ways in">
          {CHANNELS.map((ch) => {
            const on = selected ? selected.channel === ch.id : false;
            const n = cases.filter((c) => c.channel === ch.id).length;
            return (
              <li key={ch.id} className="wf-chan" data-on={on} data-dim={!!selected && !on}>
                <span className="wf-chan-k">{ch.label}</span>
                <span className="wf-sub">{ch.sub}</span>
                <span className="wf-n">{n}</span>
              </li>
            );
          })}
        </ol>
        <div className="wf-arrow" aria-hidden>→</div>
        <ol className="wf-stages" aria-label="Steps">
          {STAGES.map((s) => {
            const st = selected ? selected.stages[s.id] : null;
            return (
              <li key={s.id} className="wf-stage" data-status={st?.status ?? "idle"}>
                <span className={`wf-who wf-who-${s.whoTone}`}>{s.who}</span>
                <strong>{s.label}</strong>
                <span className="wf-sub">{st ? (st.detail || statusWord(st.status)) : s.sub}</span>
                {!selected && <span className="wf-n">{count(s.id)}</span>}
              </li>
            );
          })}
        </ol>
        <div className="wf-arrow" aria-hidden>→</div>
        <ol className="wf-col wf-out" aria-label="Outcomes">
          {OUTCOMES.map((o) => {
            const on = selected ? o.match.includes(selected.outcome) : false;
            const n = cases.filter((c) => o.match.includes(c.outcome)).length;
            return (
              <li key={o.id} className={`wf-outcome wf-${o.tone}`} data-on={on} data-dim={!!selected && !on}>
                <span className="wf-chan-k">{o.label}</span>
                <span className="wf-sub">{on && selected?.outcome_detail ? humanize(selected.outcome_detail) : o.sub}</span>
                <span className="wf-n">{n}</span>
              </li>
            );
          })}
        </ol>
      </div>
      <p className="wf-foot small"><span className="wf-dash" aria-hidden /> Any step can hand the case to a person: amount above US$ 450, a regulator threat, a request for a human, an unclear reason, a failed tool or a suspicious request.</p>
    </section>
  );
}

function statusWord(s: string): string {
  return { done: "done", active: "in progress", stopped: "stopped here", pending: "not reached" }[s] ?? s;
}

export function humanize(s: string): string {
  return s.replaceAll("_", " ");
}
