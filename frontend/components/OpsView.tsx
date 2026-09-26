"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

const SAMPLE_PQR = [
  { complaint_id: "PQR-DEMO-1", customer_id: "CUST001", transaction_id: "TXN003", description: "Me cobraron dos veces Netflix",
    evidence: { duplicate_transaction_id: "TXN002" }, reason_code: "DUPLICATE", classifier_confidence: 0.95 },
  { complaint_id: "PQR-DEMO-2", customer_id: "CUST001", transaction_id: "TXN001", description: "Cargo no reconocido",
    reason_code: "FRAUD_CNP", classifier_confidence: 0.9 },
  { complaint_id: "PQR-DEMO-3", customer_id: "CUST002", transaction_id: "TXN101", description: "Cargo no reconocido Rappi",
    evidence: { card_in_possession: "yes", recognizes_merchant: "no" }, reason_code: "FRAUD_CNP", classifier_confidence: 0.92 },
  // Like the real complaints: no transaction id, only product and claimed amount -> the system searches.
  { complaint_id: "PQR-DEMO-4", customer_id: "CUST001", affected_product_id: "PRD001", claimed_amount: "399.00",
    description: "Cobro de Netflix que no reconozco", reason_code: "FRAUD_CNP", classifier_confidence: 0.9 },
];

const LABELS: Record<string, string> = {
  replies: "Replies sent", handoffs: "Handoffs", actions_verified: "Actions verified", actions_failed: "Actions failed",
  llm_calls: "Model calls", llm_cost_usd: "Model cost (USD)", latency_ms_p50: "Reply latency p50 (ms)", latency_ms_p95: "Reply latency p95 (ms)",
};

export function OpsView({ agentKey }: { agentKey: string }) {
  const [metrics, setMetrics] = useState<Record<string, any> | null>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [pqr, setPqr] = useState<any[] | null>(null);
  const load = useCallback(async () => {
    if (!agentKey) return;
    const [m, a] = await Promise.all([api.metrics(agentKey), api.alerts(agentKey)]);
    setMetrics(m); setAlerts(a);
  }, [agentKey]);
  useEffect(() => { load().catch(() => undefined); }, [load]);

  if (!agentKey) return <div className="pane"><p className="empty">Enter the agent key in the top bar to see operations.</p></div>;

  return (
    <div className="view ops">
      <div className="pane">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ margin: 0 }}>Live service</h2>
          <button className="btn btn-quiet" onClick={load}>Refresh</button>
        </div>
        {metrics && (
          <table style={{ marginTop: 12 }}>
            <tbody>
              {Object.entries(LABELS).map(([k, label]) => (
                <tr key={k}><th>{label}</th><td className="mono">{typeof metrics[k] === "number" ? Number(metrics[k]).toLocaleString(undefined, { maximumFractionDigits: 4 }) : String(metrics[k])}</td></tr>
              ))}
              <tr><th>Replies by outcome</th><td>{Object.entries(metrics.replies_by_action ?? {}).map(([k, v]) => <span key={k} className="chip">{k} {String(v)}</span>)}</td></tr>
              <tr><th>Handoff reasons</th><td>{Object.entries(metrics.handoff_reasons ?? {}).map(([k, v]) => <span key={k} className="chip">{k} {String(v)}</span>)}</td></tr>
            </tbody>
          </table>
        )}
        <h2 style={{ marginTop: 28 }}>Fraud alerts to send</h2>
        <p className="muted">Recent approved charges with fraud score 80 or higher and no open dispute. Customers confirm or deny from the app.</p>
        <table>
          <thead><tr><th>Transaction</th><th>Customer</th><th>Merchant</th><th>Amount</th><th>Score</th></tr></thead>
          <tbody>{alerts.map((a) => <tr key={a.transaction_id}><td className="mono">{a.transaction_id}</td><td className="mono">{a.customer_id}</td><td>{a.merchant_name}</td><td>{a.amount} {a.currency}</td><td>{a.fraud_score}</td></tr>)}</tbody>
        </table>
      </div>
      <div className="pane">
        <h2>Written complaints (PQR)</h2>
        <p className="muted">Complaints received by email, web or branch run through the same rules. Nothing is asked back in real time: incomplete complaints go to an agent, and cards are never blocked without the customer confirming.</p>
        <button className="btn btn-primary" onClick={async () => setPqr(await api.pqr(agentKey, SAMPLE_PQR))}>Process sample complaints</button>
        {pqr && (
          <table style={{ marginTop: 12 }}>
            <thead><tr><th>Complaint</th><th>Result</th><th>Case</th><th>Why</th></tr></thead>
            <tbody>{pqr.map((r) => (
              <tr key={r.complaint_id}>
                <td className="mono">{r.complaint_id}</td><td>{r.action}</td><td className="mono">{r.case_id ?? "—"}</td>
                <td>{[...r.handoff_reasons, ...r.rule_ids].map((x: string) => <span key={x} className="chip">{x}</span>)}
                  {r.candidate_transactions?.length > 0 && <div className="muted">Candidates for the agent: {r.candidate_transactions.join(", ")}</div>}</td>
              </tr>))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
