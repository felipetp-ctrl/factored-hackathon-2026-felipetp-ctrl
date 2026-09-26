"use client";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, type Reply, type TraceEvent } from "@/lib/api";
import { Inspector } from "./Inspector";

type Msg = { role: "bank" | "customer" | "system"; text: string };

const QUICK = {
  es: {
    confirmBlock: ["Sí, abrir la disputa y bloquear la tarjeta", "Sí, abrir la disputa sin bloquear", "No, cancelar"],
    confirm: ["Sí, confirmo", "No, cancelar"],
    alert: ["Sí, fui yo", "No, no fui yo"],
    pick: (id: string) => `Es la compra ${id}`,
  },
  pt: {
    confirmBlock: ["Sim, abrir a contestação e bloquear o cartão", "Sim, abrir sem bloquear", "Não, cancelar"],
    confirm: ["Sim, confirmo", "Não, cancelar"],
    alert: ["Sim, fui eu", "Não, não fui eu"],
    pick: (id: string) => `É a compra ${id}`,
  },
};

export function CustomerView({ agentKey }: { agentKey: string }) {
  const [customers, setCustomers] = useState<{ customer_id: string; country: string; segment: string }[]>([]);
  const [customerId, setCustomerId] = useState("CUST001");
  const [lang, setLang] = useState<"es" | "pt">("es");
  const [token, setToken] = useState<string | null>(null);
  const [cid, setCid] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [reply, setReply] = useState<Reply | null>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [alertMode, setAlertMode] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => { api.customers().then(setCustomers).catch(() => setError("The API is not reachable. Start it with `make api`.")); }, []);
  useEffect(() => { threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight }); }, [msgs]);

  const refreshTrace = async (id: string) => {
    if (!agentKey) return;
    try { setEvents(await api.trace(id, agentKey)); } catch { /* inspector needs the agent key */ }
  };

  const signIn = async (ttl?: number) => {
    setError(null);
    const { token } = await api.login(customerId, ttl);
    setToken(token);
    return token;
  };

  const newConversation = async () => {
    setBusy(true);
    try {
      await signIn();
      const c = await api.startConversation(lang);
      setCid(c.conversation_id); setMsgs([{ role: "bank", text: c.text }]); setReply(null); setEvents([]); setAlertMode(false);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };

  const simulateAlert = async () => {
    setBusy(true); setError(null);
    try {
      const t = await signIn();
      const alerts = agentKey ? await api.alerts(agentKey) : [];
      const mine = alerts.find((a) => a.customer_id === customerId);
      if (!mine) { setError("No recent high-risk transaction for this customer."); return; }
      const c = await api.startAlert(mine.transaction_id, lang, t);
      setCid(c.conversation_id); setMsgs([{ role: "bank", text: c.text }]); setReply(null); setAlertMode(true);
      await refreshTrace(c.conversation_id);
    } catch (e) { setError(e instanceof ApiError && e.status === 401 ? "Enter the agent key to simulate alerts." : String(e)); }
    finally { setBusy(false); }
  };

  const expireSession = async () => {
    await signIn(1);
    setMsgs((m) => [...m, { role: "system", text: "Session set to expire in 1 second (demo)." }]);
  };

  const send = async (value: string) => {
    if (!cid || !token || !value.trim()) return;
    setBusy(true); setError(null); setText("");
    setMsgs((m) => [...m, { role: "customer", text: value }]);
    try {
      const r = await api.send(cid, value, token);
      setReply(r); setAlertMode(false);
      setMsgs((m) => [...m, { role: "bank", text: r.text }]);
      await refreshTrace(cid);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 429 ? "Too many messages. Wait a minute and try again." : String(e));
    } finally { setBusy(false); }
  };

  const q = QUICK[lang];
  const quick: string[] =
    alertMode ? q.alert
    : reply?.action === "confirm" ? (reply.offer_block_card ? q.confirmBlock : q.confirm)
    : reply?.candidates.length ? reply.candidates.map((c) => q.pick(c.transaction_id))
    : [];

  return (
    <div className="view customer">
      <div className="pane">
        <div className="controls">
          <div className="row">
            <label className="field">Customer (test identity)
              <select value={customerId} onChange={(e) => setCustomerId(e.target.value)}>
                {customers.map((c) => <option key={c.customer_id} value={c.customer_id}>{c.customer_id} · {c.country} · {c.segment}</option>)}
              </select>
            </label>
            <label className="field">Language
              <select value={lang} onChange={(e) => setLang(e.target.value as "es" | "pt")}>
                <option value="es">Español</option><option value="pt">Português</option>
              </select>
            </label>
          </div>
          <div className="row">
            <button className="btn btn-primary" onClick={newConversation} disabled={busy}>Start conversation</button>
            <button className="btn btn-quiet" onClick={simulateAlert} disabled={busy}>Simulate fraud alert</button>
            <button className="btn btn-quiet" onClick={expireSession} disabled={!token || busy}>Expire session</button>
          </div>
          {error && <div className="error" role="alert">{error}</div>}
        </div>
        <div className="phone">
          <div className="phone-head"><strong>LATAM Bank</strong><span className="muted">{token ? `Signed in as ${customerId}` : "Not signed in"}</span></div>
          <div className="thread" ref={threadRef} aria-live="polite">
            {msgs.length === 0 && <p className="msg-system">Start a conversation to talk to the dispute assistant.</p>}
            {msgs.map((m, i) => <div key={i} className={`msg msg-${m.role}`}>{m.text}</div>)}
            {reply?.action === "reauth" && (
              <button className="btn btn-quiet" style={{ alignSelf: "center" }} onClick={() => signIn().then(() =>
                setMsgs((m) => [...m, { role: "system", text: "Signed in again. Resend your last message." }]))}>Sign in again</button>
            )}
          </div>
          {quick.length > 0 && <div className="quick">{quick.map((x) => <button key={x} className="btn btn-quiet" onClick={() => send(x)} disabled={busy}>{x}</button>)}</div>}
          <form className="composer" onSubmit={(e) => { e.preventDefault(); send(text); }}>
            <input aria-label="Message" value={text} onChange={(e) => setText(e.target.value)} placeholder={cid ? (lang === "es" ? "Escriba su mensaje" : "Escreva sua mensagem") : ""} disabled={!cid || busy} />
            <button className="btn btn-primary" disabled={!cid || busy || !text.trim()}>Send</button>
          </form>
        </div>
      </div>
      <div className="pane">
        {agentKey ? <Inspector events={events} reply={reply} /> : <p className="empty">Enter the agent key in the top bar to see the bank-side decision trail next to the chat.</p>}
      </div>
    </div>
  );
}
