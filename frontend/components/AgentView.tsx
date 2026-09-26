"use client";
import { Fragment, useCallback, useEffect, useState } from "react";
import { api, type Handoff, type TraceEvent } from "@/lib/api";

const REASON_TEXT: Record<string, string> = {
  amount_above_threshold: "Amount above the automatic limit",
  repeat_complainer: "Customer with repeated complaints",
  dispute_velocity: "Many disputes in 30 days",
  account_takeover_signal: "Possible account takeover",
  very_negative_sentiment: "Very upset customer",
  regulatory_or_legal_threat: "Threatens regulator, legal action or press",
  low_classifier_confidence: "Unclear dispute reason",
  customer_requested_human: "Customer asked for a person",
  clarification_exhausted: "Could not identify the details after two questions",
  async_missing_info: "Written complaint missing information",
  tool_failure: "Bank system unavailable",
  verification_failed: "Action could not be confirmed",
  nlu_unavailable: "Language service unavailable",
  suspicious_access: "Asked about another customer's transaction",
  invalid_transaction_references: "Gave transaction references that do not exist",
};

export function AgentView({ agentKey }: { agentKey: string }) {
  const [queue, setQueue] = useState<Handoff[]>([]);
  const [selected, setSelected] = useState<Handoff | null>(null);
  const [trace, setTrace] = useState<TraceEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!agentKey) return;
    try { const q = await api.handoffs(agentKey); setQueue(q); setError(null); }
    catch { setError("Could not load the queue. Check the agent key."); }
  }, [agentKey]);
  useEffect(() => { load(); }, [load]);

  if (!agentKey) return <div className="pane"><p className="empty">Enter the agent key in the top bar to open the handoff queue.</p></div>;

  return (
    <div className="view agent">
      <div className="pane">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>Waiting for an agent</h2>
          <button className="btn btn-quiet" onClick={load}>Refresh</button>
        </div>
        {error && <div className="error">{error}</div>}
        {queue.length === 0 ? <p className="empty">No cases waiting. Cases the assistant hands over appear here with everything already checked.</p> : (
          <ul className="queue">
            {queue.map((h) => (
              <li key={h.case_ref}>
                <button aria-current={selected?.case_ref === h.case_ref} onClick={() => { setSelected(h); setTrace(null); }}>
                  <div><strong>{REASON_TEXT[h.reason_for_handoff[0]] ?? h.reason_for_handoff[0]}</strong></div>
                  <div className="muted">{h.customer_request_summary || "No summary"} · {h.channel} · {h.language.toUpperCase()}</div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="pane pkg">
        {!selected ? <p className="empty">Select a case to see what was verified, what was done and what is still open.</p> : (
          <>
            <h2>Case <span className="mono">{selected.case_ref}</span></h2>
            <section>
              <h3>Why it came to you</h3>
              <ul>{selected.reason_for_handoff.map((r) => <li key={r}>{REASON_TEXT[r] ?? r}</li>)}</ul>
              <p>{selected.customer_request_summary}</p>
            </section>
            <section>
              <h3>Verified facts</h3>
              {selected.verified_facts.length === 0 ? <p className="muted">Nothing verified yet.</p> :
                <dl>{selected.verified_facts.map((f) => <Fragment key={f.source}><dt className="mono">{f.source}</dt><dd>{f.fact}</dd></Fragment>)}</dl>}
            </section>
            <section>
              <h3>Actions already taken</h3>
              {selected.actions_taken.length === 0 ? <p className="muted">No actions were taken on the account.</p> :
                <ul>{selected.actions_taken.map((a, i) => <li key={i}><span className={`chip ${a.status === "verified" ? "chip-ok" : "chip-warn"}`}>{a.action} {a.ref}</span> {a.status}</li>)}</ul>}
            </section>
            <section>
              <h3>Policy</h3>
              {selected.policy_decision ? (
                <dl>
                  <dt>Decision</dt><dd>{selected.policy_decision.decision} {selected.policy_decision.rule_ids.map((r) => <span key={r} className="chip">{r}</span>)}</dd>
                  <dt>Version</dt><dd className="mono">{selected.policy_decision.policy_version}</dd>
                  <dt>Proposed reason</dt><dd className="mono">{selected.proposed_reason_code ?? "—"}</dd>
                  {Object.entries(selected.risk_signals).map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{v ?? "—"}</dd></Fragment>)}
                </dl>
              ) : <p className="muted">The policy was not evaluated before the handoff.</p>}
            </section>
            <section>
              <h3>Still open</h3>
              {selected.open_questions.length === 0 ? <p className="muted">Nothing pending.</p> : <ul>{selected.open_questions.map((q) => <li key={q}>{q}</li>)}</ul>}
            </section>
            <section>
              <button className="btn btn-quiet" onClick={async () => setTrace(await api.trace(selected.trace_id, agentKey))}>Show full trace</button>
              {trace && <table style={{ marginTop: 12 }}><tbody>{trace.map((e, i) => <tr key={i}><td className="mono">{e.at.slice(11, 19)}</td><td>{e.kind}</td><td className="mono" style={{ wordBreak: "break-word" }}>{JSON.stringify(e.data).slice(0, 220)}</td></tr>)}</tbody></table>}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
