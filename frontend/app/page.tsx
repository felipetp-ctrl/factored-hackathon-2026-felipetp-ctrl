"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { BankConsole, type BankTab } from "@/components/BankConsole";
import { type AppTab, CustomerApp, type Msg } from "@/components/CustomerApp";
import {
  api, ApiError, type Alert, type Case, type DemoCustomer, type Health, type Lang, type Me, type PqrResult, type QueueItem, type Reply,
  type Scenario, type TraceEvent, type Txn,
} from "@/lib/api";
import { FLAG } from "@/lib/format";
import { T } from "@/lib/i18n";

const PQR_SCENARIO: Scenario = {
  id: "written_complaints", label: "Written complaints", customer_id: "", language: "es",
  try: "Open Written complaints on the bank side and process the inbox: six letters by email, web form, branch and app, in Spanish and Portuguese.",
  expected: "Two disputes open with no person involved. The other four go to the Queue with the reason: a charge that cannot be pinned down, an amount above the limit, a missing answer, or a regulator threat.",
};

export default function Demo() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [customers, setCustomers] = useState<DemoCustomer[]>([]);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [lang, setLang] = useState<Lang>("es");
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [token, setToken] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [txns, setTxns] = useState<Txn[]>([]);
  const [cases, setCases] = useState<Case[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [appTab, setAppTab] = useState<AppTab>("home");

  const [cid, setCid] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [reply, setReply] = useState<Reply | null>(null);
  const [busy, setBusy] = useState(false);
  const lastSent = useRef<string>("");

  const [bankTab, setBankTab] = useState<BankTab>("decisions");
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [mobile, setMobile] = useState<"client" | "bank">("client");
  const [pqr, setPqr] = useState<Record<string, PqrResult>>({});

  const fail = (e: unknown) => {
    if (e instanceof TypeError) setError("The API is waking up or unreachable. On the free plan the first request can take about a minute; try again shortly.");
    else setError(e instanceof Error ? e.message : String(e));
  };

  const refreshHealth = useCallback(() => api.health().then(setHealth).catch(() => undefined), []);
  const refreshQueue = useCallback(() => api.handoffs().then(setQueue).catch(() => undefined), []);
  const refreshTrail = useCallback((id: string | null) => {
    if (id) api.trace(id).then(setEvents).catch(() => undefined); else setEvents([]);
  }, []);
  const refreshCustomer = useCallback(async (tok: string) => {
    const [m, t, c, a] = await Promise.all([api.me(tok), api.transactions(tok), api.cases(tok), api.alerts(tok)]);
    setMe(m); setTxns(t); setCases(c); setAlerts(a);
  }, []);

  const resetChat = () => { setCid(null); setMsgs([]); setReply(null); setEvents([]); };

  const openCustomer = useCallback(async (id: string, language: Lang) => {
    setError(null); setBusy(true);
    try {
      const { token: tok } = await api.login(id);
      setToken(tok); setCustomerId(id); setLang(language);
      setCid(null); setMsgs([]); setReply(null); setEvents([]); setAppTab("home");
      await refreshCustomer(tok);
    } catch (e) { fail(e); } finally { setBusy(false); }
  }, [refreshCustomer]);

  const chooseScenario = (s: Scenario) => {
    setScenario(s);
    if (s.id === PQR_SCENARIO.id) { setBankTab("complaints"); setMobile("bank"); return; }
    openCustomer(s.customer_id, s.language);
  };

  useEffect(() => {
    (async () => {
      try {
        const [sc, cs] = await Promise.all([api.scenarios(), api.customers()]);
        setScenarios(sc); setCustomers(cs); refreshHealth(); refreshQueue();
        if (sc[0]) { setScenario(sc[0]); await openCustomer(sc[0].customer_id, sc[0].language); }
        else if (cs[0]) await openCustomer(cs[0].customer_id, "es");
      } catch (e) { fail(e); }
    })();
  }, [openCustomer, refreshHealth, refreshQueue]);

  useEffect(() => {  // the queue fills from any conversation; keep it fresh
    const t = setInterval(refreshQueue, 4000);
    return () => clearInterval(t);
  }, [refreshQueue]);

  const afterReply = async (r: Reply, tok: string) => {
    setReply(r);
    setMsgs((m) => [...m, { role: "bank", text: r.text, reply: r }]);
    refreshTrail(r.conversation_id);
    refreshHealth();
    await refreshCustomer(tok).catch(() => undefined);
    if (r.action === "handoff") {
      await refreshQueue();
      setSelected(r.handoff?.case_ref ?? null);
      setBankTab("queue");
    }
  };

  const withBusy = async (fn: () => Promise<void>) => {
    setBusy(true); setError(null);
    try { await fn(); } catch (e) {
      if (e instanceof ApiError && e.status === 429) setError("Too many messages in a minute. Wait a moment and try again.");
      else fail(e);
    } finally { setBusy(false); }
  };

  const startFromPurchase = (t: Txn) => token && withBusy(async () => {
    const s = await api.start(lang, token, t.transaction_id);
    setCid(s.conversation_id); setMsgs([{ role: "bank", text: s.text, reply: s.reply }]); setReply(s.reply);
    setAppTab("chat"); setBankTab("decisions"); refreshTrail(s.conversation_id);
  });

  const startPlain = async (tok: string): Promise<string> => {
    const s = await api.start(lang, tok);
    setCid(s.conversation_id); setMsgs([{ role: "bank", text: s.text }]); setReply(null); setEvents([]);
    return s.conversation_id;
  };

  const send = (text: string) => token && withBusy(async () => {
    const id = cid ?? await startPlain(token);
    lastSent.current = text;
    setMsgs((m) => [...m, { role: "customer", text }]);
    setAppTab("chat");
    await afterReply(await api.send(id, text, token), token);
  });

  const answerAlert = (a: Alert, recognized: boolean) => token && withBusy(async () => {
    const s = await api.startAlert(a.transaction_id, lang, token);
    const text = recognized ? T[lang].alertYes : T[lang].alertNo;
    setCid(s.conversation_id); setMsgs([{ role: "bank", text: s.text }, { role: "customer", text }]); setAppTab("chat");
    await afterReply(await api.send(s.conversation_id, text, token), token);
  });

  const reauth = () => customerId && cid && withBusy(async () => {
    const { token: tok } = await api.login(customerId);
    setToken(tok);
    setMsgs((m) => [...m, { role: "system", text: T[lang].reauthDone }]);
    await afterReply(await api.send(cid, lastSent.current, tok), tok);
  });

  const expireSession = () => customerId && withBusy(async () => {
    const { token: tok } = await api.login(customerId, 1);  // a session that expires in one second
    setToken(tok);
    setMsgs((m) => [...m, { role: "system", text: "Session set to expire in 1 second (demo control). Send a message." }]);
    setAppTab("chat");
  });

  const toggleOutage = () => withBusy(async () => {
    const r = await api.outage(!(health?.nlu.reason === "simulated_outage"));
    setHealth((h) => (h ? { ...h, nlu: r.nlu } : h));
  });

  const resetDemo = () => withBusy(async () => {
    await api.reset();
    setQueue([]); setSelected(null); setPqr({}); resetChat(); refreshHealth();
    if (customerId) await openCustomer(customerId, lang);
  });

  const outage = health?.nlu.reason === "simulated_outage";
  const nluLabel = health ? (health.nlu.mode === "claude" ? "AI: Claude" : "AI: rules fallback") : "AI: …";

  return (
    <div className="demo">
      <header className="guide">
        <div className="guide-row">
          <div className="brand"><span className="brand-mark" aria-hidden />LATAM Bank <span className="brand-sub">card dispute operations · live demo</span></div>
          <div className="guide-tools">
            <span className={`pill ${health?.nlu.mode === "rules" ? "pill-warn" : "pill-ok"}`} title={health?.nlu.reason ?? "Claude Haiku 4.5 interprets; rules decide"}>{nluLabel}</span>
            <button className="btn btn-ghost" onClick={toggleOutage} disabled={busy || !health?.demo_mode} aria-pressed={outage}>{outage ? "Restore AI" : "Simulate AI outage"}</button>
            <button className="btn btn-ghost" onClick={expireSession} disabled={busy || !token}>Expire session</button>
            <button className="btn btn-ghost" onClick={resetDemo} disabled={busy}>Reset demo</button>
          </div>
        </div>
        <p className="pitch">One case system for disputed card charges. Cases come in three ways: the <strong>app chat</strong>, <strong>written complaints</strong> and <strong>fraud alerts</strong> the bank sends first.
          Language AI only reads what customers write; written rules decide, every action is checked after it runs, and cases that need judgement go to a person with the facts already gathered.</p>
        <div className="guide-row">
          <nav className="scenarios" aria-label="Guided scenarios">
            <span className="guide-label">Try</span>
            {(scenarios.length ? [...scenarios, PQR_SCENARIO] : []).map((s, i) => (
              <button key={s.id} className="scenario" aria-pressed={scenario?.id === s.id} onClick={() => chooseScenario(s)} disabled={busy}>
                <span className="scenario-n">{i + 1}</span>{s.label}
              </button>
            ))}
          </nav>
          <div className="guide-free">
            <label className="field-inline">Customer
              <select id="customer" value={customerId ?? ""} onChange={(e) => { setScenario(null); openCustomer(e.target.value, lang); }} disabled={busy}>
                {customers.map((c) => <option key={c.customer_id} value={c.customer_id}>{c.first_name ?? c.customer_id} · {FLAG[c.country] ?? c.country} · {c.segment}</option>)}
              </select>
            </label>
            <div className="seg" role="group" aria-label="Language">
              {(["es", "pt"] as Lang[]).map((l) => (
                <button key={l} aria-pressed={lang === l} onClick={() => { setLang(l); resetChat(); }} disabled={busy}>{l === "es" ? "Español" : "Português"}</button>
              ))}
            </div>
          </div>
        </div>
        {scenario && (
          <div className="hint">
            <p><span className="hint-k">Do</span>{scenario.try}</p>
            <p><span className="hint-k">Expect</span>{scenario.expected}</p>
          </div>
        )}
        {error && <p className="banner-error" role="alert">{error}</p>}
      </header>

      <div className="mobile-switch" role="group" aria-label="Side">
        <button aria-pressed={mobile === "client"} onClick={() => setMobile("client")}>Customer app</button>
        <button aria-pressed={mobile === "bank"} onClick={() => setMobile("bank")}>Bank side{queue.some((q) => q.status === "new") && " •"}</button>
      </div>

      <main className="split">
        <section className="side side-client" data-hidden-mobile={mobile !== "client"} aria-label="Customer app">
          <p className="side-label">What the customer sees</p>
          <CustomerApp
            lang={lang} me={me} txns={txns} cases={cases} alerts={alerts} tab={appTab} onTab={setAppTab}
            msgs={msgs} reply={reply} busy={busy}
            onDispute={startFromPurchase} onAlert={answerAlert} onSend={send}
            onNewChat={() => { resetChat(); setAppTab("home"); }} onReauth={reauth}
          />
        </section>
        <section className="side side-bank" data-hidden-mobile={mobile !== "bank"} aria-label="Bank side">
          <p className="side-label">What the bank sees · every channel lands here</p>
          <BankConsole
            tab={bankTab} onTab={setBankTab} queue={queue} selected={selected} onSelect={setSelected}
            onQueueChanged={async () => { await refreshQueue(); if (token) await refreshCustomer(token); refreshTrail(cid); }}
            events={events} reply={reply} nlu={health?.nlu ?? null} pqr={pqr} onPqr={setPqr}
          />
        </section>
      </main>
    </div>
  );
}
