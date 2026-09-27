"use client";
import { useEffect, useRef, useState } from "react";
import type { Alert, Case, Lang, Me, Reply, Txn } from "@/lib/api";
import { day, dayTime, money } from "@/lib/format";
import { quickReplies, T, why } from "@/lib/i18n";

export type Msg = { role: "bank" | "customer" | "system"; text: string; reply?: Reply | null };
export type AppTab = "home" | "chat" | "cases";

type Props = {
  lang: Lang;
  me: Me | null;
  txns: Txn[];
  cases: Case[];
  alerts: Alert[];
  tab: AppTab;
  onTab: (t: AppTab) => void;
  msgs: Msg[];
  reply: Reply | null;
  busy: boolean;
  onDispute: (t: Txn) => void;
  onAlert: (a: Alert, recognized: boolean) => void;
  onSend: (text: string) => void;
  onNewChat: () => void;
  onReauth: () => void;
};

function Why({ reply, lang }: { reply: Reply; lang: Lang }) {
  const [open, setOpen] = useState(false);
  const text = why(reply, lang);
  if (!text) return null;
  return (
    <div className="why">
      <button className="why-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>{T[lang].why}</button>
      {open && (
        <p className="why-text">
          {text}
          {reply.nlu_mode !== "none" && <span className="why-meta">{T[lang].interpretedBy[reply.nlu_mode]}</span>}
        </p>
      )}
    </div>
  );
}

function Home(p: Props) {
  const t = T[p.lang];
  const card = p.me?.cards[0];
  return (
    <div className="app-scroll">
      <div className="app-hello">
        <p className="app-greet">{p.me ? t.hello(p.me.first_name ?? p.me.customer_id) : "…"}</p>
        {card && (
          <div className={`bank-card ${card.product_status === "Blocked" ? "is-blocked" : ""}`}>
            <span>{card.product_type === "Debit Card" ? "Débito" : t.card}</span>
            <span className="bank-card-num">•••• {card.product_id.slice(-4)}</span>
            <span className="bank-card-state">{card.product_status === "Blocked" ? t.blocked : t.active}</span>
          </div>
        )}
      </div>
      {p.alerts.slice(0, 1).map((a) => (
        <div className="alert" key={a.transaction_id} role="status">
          <strong>{t.alertTitle}</strong>
          <span>{a.merchant_name ?? t.noMerchant} · {money(a.amount, a.currency, p.lang)} {a.currency} · {dayTime(a.transaction_date)}</span>
          <span className="alert-note">{t.alertBody}</span>
          <div className="alert-actions">
            <button className="btn btn-small" onClick={() => p.onAlert(a, true)} disabled={p.busy}>{t.alertYes}</button>
            <button className="btn btn-small btn-danger" onClick={() => p.onAlert(a, false)} disabled={p.busy}>{t.alertNo}</button>
          </div>
        </div>
      ))}
      <button className="btn app-ask" onClick={() => p.onTab("chat")}>{t.askAssistant}</button>
      <h3 className="app-section">{t.recent}</h3>
      <ul className="txns">
        {p.txns.map((x) => {
          const disputable = !x.case_id && (x.transaction_status === "Approved" || x.transaction_status === "Pending");
          return (
            <li key={x.transaction_id} className="txn">
              <div className="txn-main">
                <span className="txn-merchant">{x.merchant_name ?? t.noMerchant}</span>
                <span className="txn-date">{dayTime(x.transaction_date)}
                  {x.transaction_status === "Reversed" && <em> · {t.reversed}</em>}
                  {x.transaction_status === "Pending" && <em> · {t.pending}</em>}
                </span>
              </div>
              <div className="txn-side">
                <span className="txn-amount">{money(x.amount, x.currency, p.lang)} <small>{x.currency}</small></span>
                {x.case_id ? <span className="tag tag-case">{t.inDispute}</span>
                  : disputable && <button className="link-btn" onClick={() => p.onDispute(x)} disabled={p.busy}>{t.dispute}</button>}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function Chat(p: Props) {
  const t = T[p.lang];
  const [text, setText] = useState("");
  const thread = useRef<HTMLDivElement>(null);
  useEffect(() => { thread.current?.scrollTo({ top: thread.current.scrollHeight, behavior: "smooth" }); }, [p.msgs, p.busy]);
  const quick = quickReplies(p.reply, p.lang);
  const ended = p.reply ? ["done", "handoff", "ineligible", "cancelled"].includes(p.reply.action) || p.reply.state === "CANCELLED" : false;
  const pickable = p.reply?.action === "ask" && p.reply.candidates.length > 0;
  const submit = (value: string) => { if (value.trim()) { p.onSend(value.trim()); setText(""); } };
  return (
    <div className="chat">
      <div className="thread" ref={thread} aria-live="polite">
        {p.msgs.length === 0 && <p className="msg-system">{t.startHint}</p>}
        {p.msgs.map((m, i) => (
          <div key={i} className={`msg msg-${m.role}`}>
            <div className="msg-text">{m.text}</div>
            {m.role === "bank" && m.reply && <Why reply={m.reply} lang={p.lang} />}
          </div>
        ))}
        {pickable && p.reply!.candidates.map((c, i) => (
          <button key={c.transaction_id} className="candidate" onClick={() => submit(`${p.lang === "es" ? "Es la compra" : "É a compra"} ${c.transaction_id}`)} disabled={p.busy}>
            <span className="candidate-n">{i + 1}</span>
            <span>{c.merchant || t.noMerchant}<small>{c.date.slice(8, 10)}/{c.date.slice(5, 7)}/{c.date.slice(0, 4)} {c.date.slice(11)}</small></span>
            <strong>{money(c.amount, c.currency, p.lang)} {c.currency}</strong>
          </button>
        ))}
        {p.reply?.action === "reauth" && (
          <div className="msg-system reauth">
            {t.reauth} <button className="btn btn-small" onClick={p.onReauth} disabled={p.busy}>{t.reauthBtn}</button>
          </div>
        )}
        {p.busy && <div className="typing" aria-label="…"><i /><i /><i /></div>}
        {ended && (
          <div className="msg-system">{t.ended} · <button className="link-btn" onClick={p.onNewChat}>{t.newChat}</button></div>
        )}
      </div>
      {quick.length > 0 && (
        <div className="quick">{quick.map((q) => <button key={q} className="chip-btn" onClick={() => submit(q)} disabled={p.busy}>{q}</button>)}</div>
      )}
      <form className="composer" onSubmit={(e) => { e.preventDefault(); submit(text); }}>
        <input id="chat-input" aria-label={t.placeholder} value={text} onChange={(e) => setText(e.target.value)}
               placeholder={t.placeholder} disabled={p.busy || ended} />
        <button className="btn btn-primary" disabled={p.busy || ended || !text.trim()}>{t.send}</button>
      </form>
    </div>
  );
}

function Cases(p: Props) {
  const t = T[p.lang];
  if (!p.cases.length) return <p className="app-empty">{t.noCases}</p>;
  return (
    <ul className="cases app-scroll">
      {p.cases.map((c) => (
        <li key={c.case_id} className="case">
          <div className="case-top"><span className="mono">{c.case_id}</span><span className="tag tag-case">{t.caseStatus[c.status] ?? c.status}</span></div>
          <strong>{c.merchant_name ?? t.noMerchant} · {money(c.amount, c.currency, p.lang)} {c.currency}</strong>
          <span>{t.reason[c.reason_code] ?? c.reason_code} · {day(c.transaction_date)}</span>
          <span className="case-by">{t.openedBy[c.opened_by]} · {dayTime(c.created_at)}</span>
        </li>
      ))}
    </ul>
  );
}

export function CustomerApp(p: Props) {
  const t = T[p.lang];
  return (
    <div className="phone">
      <div className="phone-top"><span className="phone-brand">LATAM Bank</span><span className="phone-lang">{p.lang.toUpperCase()}</span></div>
      <div className="phone-body">
        {p.tab === "home" && <Home {...p} />}
        {p.tab === "chat" && <Chat {...p} />}
        {p.tab === "cases" && <Cases {...p} />}
      </div>
      <nav className="phone-nav" aria-label="App">
        {(["home", "chat", "cases"] as AppTab[]).map((id) => (
          <button key={id} aria-current={p.tab === id} onClick={() => p.onTab(id)}>
            {t.tabs[id]}{id === "cases" && p.cases.length > 0 && <span className="badge">{p.cases.length}</span>}
          </button>
        ))}
      </nav>
    </div>
  );
}
