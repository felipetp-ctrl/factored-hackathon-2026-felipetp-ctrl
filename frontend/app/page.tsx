"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { BankConsole, type BankTab } from "@/components/BankConsole";
import { type AppTab, CustomerApp, type Msg } from "@/components/CustomerApp";
import {
  api, ApiError, type Alert, type Case, type CaseRow, type DemoCustomer, type Health, type Lang, type Me, type PqrResult, type QueueItem, type Reply,
  type Scenario, type Txn,
} from "@/lib/api";
import { FLAG } from "@/lib/format";
import { T } from "@/lib/i18n";

const TOUR_SUB: Record<string, string> = {
  written_complaints: "Six letters, no typing", fraud_alert: "The bank asks first", normal: "Dispute a purchase in the app",
  ambiguous: "Several similar charges", out_of_scope: "A question it should not answer", human: "A case above the limit",
  attack: "Someone else's charge and an injection",
};

const PQR_SCENARIO: Scenario = {
  id: "written_complaints", label: "Written complaints", customer_id: "", language: "es",
  try: "Press “Process 6 letters”, then “See the cases”.",
  expected: "Two letters are resolved with no person. Four need a person, each with its reason: the charge cannot be pinned down, the amount is above the limit, an answer is missing, or the customer mentions a regulator. Click a case to see its path.",
};

export default function Demo() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [customers, setCustomers] = useState<DemoCustomer[]>([]);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [lang, setLang] = useState<Lang>("es");
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [waking, setWaking] = useState(false);  // the free API sleeps when idle; say so instead of a blank page

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

  const [bankTab, setBankTab] = useState<BankTab>("cases");
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [board, setBoard] = useState<CaseRow[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [mobile, setMobile] = useState<"client" | "bank">("bank");
  const [pqr, setPqr] = useState<Record<string, PqrResult>>({});
  const [menu, setMenu] = useState<"tour" | "more" | null>(null);

  const fail = (e: unknown) => {
    if (e instanceof TypeError) setError("The API is waking up or unreachable. On the free plan the first request can take about a minute; try again shortly.");
    else setError(e instanceof Error ? e.message : String(e));
  };

  const refreshHealth = useCallback(() => api.health().then(setHealth).catch(() => undefined), []);
  const refreshQueue = useCallback(() => api.handoffs().then(setQueue).catch(() => undefined), []);
  const refreshBoard = useCallback(() => api.board().then(setBoard).catch(() => undefined), []);
  const refreshBank = useCallback(() => { refreshQueue(); refreshBoard(); }, [refreshQueue, refreshBoard]);
  const refreshCustomer = useCallback(async (tok: string) => {
    const [m, t, c, a] = await Promise.all([api.me(tok), api.transactions(tok), api.cases(tok), api.alerts(tok)]);
    setMe(m); setTxns(t); setCases(c); setAlerts(a);
  }, []);

  const resetChat = () => { setCid(null); setMsgs([]); setReply(null); };

  const openCustomer = useCallback(async (id: string, language: Lang) => {
    setError(null); setBusy(true);
    try {
      const { token: tok } = await api.login(id);
      setToken(tok); setCustomerId(id); setLang(language);
      setCid(null); setMsgs([]); setReply(null); setAppTab("home");
      await refreshCustomer(tok);
    } catch (e) { fail(e); } finally { setBusy(false); }
  }, [refreshCustomer]);

  const chooseScenario = (s: Scenario) => {
    setScenario(s);
    if (s.id === PQR_SCENARIO.id) { setBankTab("letters"); setMobile("bank"); return; }
    setBankTab("cases"); setSelected(null);
    openCustomer(s.customer_id, s.language);
  };

  useEffect(() => {
    const slow = setTimeout(() => setWaking(true), 3000);
    (async () => {
      // A sleeping free-plan API can drop the first request while it starts; try a few times before giving up.
      for (let attempt = 1; ; attempt++) {
        try {
          const [sc, cs] = await Promise.all([api.scenarios(), api.customers()]);
          clearTimeout(slow); setWaking(false); setError(null);
          setScenarios(sc); setCustomers(cs); refreshHealth(); refreshBank();
          const first = sc.find((x) => x.id === "normal") ?? sc[0];
          if (first) await openCustomer(first.customer_id, first.language);
          else if (cs[0]) await openCustomer(cs[0].customer_id, "es");
          return;
        } catch (e) {
          if (e instanceof TypeError && attempt < 6) { await new Promise((r) => setTimeout(r, 10000)); continue; }
          clearTimeout(slow); setWaking(false); fail(e); return;
        }
      }
    })();
    return () => clearTimeout(slow);
  }, [openCustomer, refreshHealth, refreshBank]);

  useEffect(() => {  // cases arrive from every channel; keep the board fresh
    const t = setInterval(refreshBank, 3000);
    return () => clearInterval(t);
  }, [refreshBank]);

  const afterReply = async (r: Reply, tok: string) => {
    setReply(r);
    setMsgs((m) => [...m, { role: "bank", text: r.text, reply: r }]);
    refreshHealth(); refreshBank();
    await refreshCustomer(tok).catch(() => undefined);
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
    setAppTab("chat"); setBankTab("cases"); refreshBank();
  });

  const startPlain = async (tok: string): Promise<string> => {
    const s = await api.start(lang, tok);
    setCid(s.conversation_id); setMsgs([{ role: "bank", text: s.text }]); setReply(null);
    setBankTab("cases");
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
    setBankTab("cases");
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
    setQueue([]); setBoard([]); setSelected(null); setPqr({}); resetChat(); refreshHealth();
    if (customerId) await openCustomer(customerId, lang);
  });

  const outage = health?.nlu.reason === "simulated_outage";
  const nluLabel = health ? (health.nlu.mode === "claude" ? "AI: Claude" : "AI: rules fallback") : "AI: …";

  const allScenarios = scenarios.length ? [PQR_SCENARIO, ...scenarios] : [];
  const tour = (id: string) => { const s = allScenarios.find((x) => x.id === id); if (s) { chooseScenario(s); setMenu(null); } };
  const aiDown = health?.nlu.mode === "rules" && health.nlu.fallback !== false;

  return (
    <div className="demo">
      <header className="top">
        <div className="brand"><span className="brand-mark" aria-hidden />LATAM Bank <span className="brand-sub">Card disputes</span></div>
        <div className="top-tools">
          {(outage || aiDown) && <span className="pill pill-warn" title="Customers' words are read by the free rule-based reader">AI off, rules reading</span>}
          <div className="pop">
            <button className="btn btn-ghost" aria-expanded={menu === "tour"} onClick={() => setMenu(menu === "tour" ? null : "tour")}>Guided tour</button>
            {menu === "tour" && (
              <ol className="menu menu-tour">
                {allScenarios.map((s) => (
                  <li key={s.id}><button onClick={() => tour(s.id)} aria-current={scenario?.id === s.id}>
                    <strong>{s.label}</strong><span>{TOUR_SUB[s.id] ?? ""}</span></button></li>
                ))}
              </ol>
            )}
          </div>
          <div className="seg" role="group" aria-label="Language">
            {(["es", "pt"] as Lang[]).map((l) => (
              <button key={l} aria-pressed={lang === l} onClick={() => { setLang(l); resetChat(); }} disabled={busy}>{l.toUpperCase()}</button>
            ))}
          </div>
          <div className="pop">
            <button className="btn btn-ghost icon" aria-label="Demo controls" aria-expanded={menu === "more"} onClick={() => setMenu(menu === "more" ? null : "more")}>⋯</button>
            {menu === "more" && (
              <div className="menu menu-more">
                <label className="field">Customer
                  <select id="customer" value={customerId ?? ""} onChange={(e) => { setScenario(null); openCustomer(e.target.value, lang); setMenu(null); }} disabled={busy}>
                    {customers.map((c) => <option key={c.customer_id} value={c.customer_id}>{c.first_name ?? c.customer_id}, {c.country}, {c.segment}</option>)}
                  </select>
                </label>
                <button onClick={() => { toggleOutage(); setMenu(null); }} disabled={busy || !health?.demo_mode}>{outage ? "Bring the AI back" : "Simulate an AI outage"}</button>
                <button onClick={() => { expireSession(); setMenu(null); }} disabled={busy || !token}>Expire the customer&apos;s session</button>
                <button onClick={() => { resetDemo(); setMenu(null); }} disabled={busy}>Reset the demo</button>
              </div>
            )}
          </div>
        </div>
      </header>
      {scenario && (
        <div className="tourbar" role="status">
          <span className="tour-k">{scenario.label}</span>
          <p>{scenario.try}</p>
          <details><summary>What should happen?</summary><p>{scenario.expected}</p></details>
          <button className="icon-btn" aria-label="End tour" onClick={() => setScenario(null)}>×</button>
        </div>
      )}
      {waking && !error && <p className="banner-info" role="status">Starting the demo server (free plan, idle servers sleep). The first load takes about 30 seconds; the page fills in by itself.</p>}
      {error && <p className="banner-error" role="alert">{error}</p>}

      <div className="mobile-switch" role="group" aria-label="Side">
        <button aria-pressed={mobile === "bank"} onClick={() => setMobile("bank")}>Bank</button>
        <button aria-pressed={mobile === "client"} onClick={() => setMobile("client")}>Customer app</button>
      </div>

      <main className="ops-layout" onClick={() => menu && setMenu(null)}>
        <section className="side side-bank" data-hidden-mobile={mobile !== "bank"} aria-label="Bank">
          <BankConsole
            tab={bankTab} onTab={setBankTab} cases={board} queue={queue} selected={selected} onSelect={setSelected}
            onQueueChanged={async () => { refreshBank(); if (token) await refreshCustomer(token); }}
            nlu={health?.nlu ?? null} pqr={pqr} onPqr={setPqr} onTour={tour}
            onOpenCustomer={(id) => { setScenario(null); setMobile("client"); openCustomer(id, lang); }}
          />
        </section>
        <section className="side side-client" data-hidden-mobile={mobile !== "client"} aria-label="Customer app">
          <CustomerApp
            lang={lang} me={me} txns={txns} cases={cases} alerts={alerts} tab={appTab} onTab={setAppTab}
            msgs={msgs} reply={reply} busy={busy}
            onDispute={startFromPurchase} onAlert={answerAlert} onSend={send}
            onNewChat={() => { resetChat(); setAppTab("home"); }} onReauth={reauth}
          />
        </section>
      </main>
    </div>
  );
}
