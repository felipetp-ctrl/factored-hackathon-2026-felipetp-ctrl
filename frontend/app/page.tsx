"use client";
import { useEffect, useState } from "react";
import { AgentView } from "@/components/AgentView";
import { CustomerView } from "@/components/CustomerView";
import { OpsView } from "@/components/OpsView";

const VIEWS = [
  { id: "customer", label: "Customer" },
  { id: "agent", label: "Agent" },
  { id: "ops", label: "Operations" },
] as const;
type ViewId = (typeof VIEWS)[number]["id"];

export default function Home() {
  const [view, setView] = useState<ViewId>("customer");
  const [agentKey, setAgentKey] = useState(process.env.NEXT_PUBLIC_AGENT_KEY ?? "");

  useEffect(() => {
    try { const saved = sessionStorage.getItem("agentKey"); if (saved) setAgentKey(saved); } catch { /* storage unavailable */ }
  }, []);
  const saveKey = (k: string) => { setAgentKey(k); try { sessionStorage.setItem("agentKey", k); } catch { /* ignore */ } };

  return (
    <>
      <header className="bar">
        <div className="brand"><span className="brand-mark" aria-hidden />LATAM Bank · Disputes</div>
        <nav className="tabs" role="tablist">
          {VIEWS.map((v) => (
            <button key={v.id} role="tab" className="tab" aria-selected={view === v.id} onClick={() => setView(v.id)}>{v.label}</button>
          ))}
        </nav>
        <label className="bar-right">Agent key
          <input type="password" value={agentKey} onChange={(e) => saveKey(e.target.value)} placeholder="needed for bank-side views" />
        </label>
      </header>
      <main>
        {view === "customer" && <CustomerView agentKey={agentKey} />}
        {view === "agent" && <AgentView agentKey={agentKey} />}
        {view === "ops" && <OpsView agentKey={agentKey} />}
      </main>
    </>
  );
}
