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

function Dispute(p: Props) {
  const t = T[p.lang];
  const f = t.form;
  const [text, setText] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const top = useRef<HTMLDivElement>(null);
  useEffect(() => { top.current?.scrollTo({ top: 0, behavior: "smooth" }); }, [p.reply]);
  const quick = quickReplies(p.reply, p.lang);
  const r = p.reply;
  const ended = r ? ["done", "handoff", "ineligible", "cancelled"].includes(r.action) || r.state === "CANCELLED" : false;
  const pickable = r?.action === "ask" && r.candidates.length > 0;
  const submit = (value: string) => { if (value.trim()) { p.onSend(value.trim()); setText(""); } };
  const lastBank = [...p.msgs].reverse().find((m) => m.role === "bank");
  const draft = r?.draft;
  const tx = draft?.transaction;
  const asked = new Set(r?.ask_for ?? []);
  const evidence = Object.entries(draft?.evidence ?? {});
  const result = !r ? null : r.action === "done" ? f.done : r.action === "handoff" ? f.person : ended ? f.closed : null;
  const yn = (v: string) => (v === "yes" ? f.yes : v === "no" ? f.no : v);
  const stepState = (ok: boolean, isAsked: boolean) => (ok ? "ok" : isAsked ? "ask" : "todo");
  return (
    <div className="dispute app-scroll" ref={top}>
      <h3 className="dispute-title">{f.title}</h3>
      {p.msgs.length === 0 ? (
        <p className="dispute-start">{f.start}</p>
      ) : (
        <ol className="form" aria-label={f.yourCase}>
          <li data-state={stepState(!!tx, asked.has("transaction"))}>
            <span className="form-k">{f.charge}</span>
            <span className="form-v">{tx ? <>{tx.merchant || t.noMerchant} · {money(tx.amount, tx.currency, p.lang)} {tx.currency} · {tx.date.slice(8, 10)}/{tx.date.slice(5, 7)}</> : f.notYet}</span>
          </li>
          <li data-state={stepState(!!draft?.reason_code, asked.has("reason_code"))}>
            <span className="form-k">{f.reason}</span>
            <span className="form-v">{draft?.reason_code ? t.reason[draft.reason_code] ?? draft.reason_code : f.notYet}</span>
            {draft?.reason_code && <span className="src src-ai">{f.fromText}</span>}
          </li>
          <li data-state={evidence.length && ![...asked].some((a) => a in f.evidence) ? "ok" : [...asked].some((a) => a in f.evidence) ? "ask" : "todo"}>
            <span className="form-k">{f.details}</span>
            <span className="form-v">
              {evidence.map(([k, v]) => <span key={k} className="ev">{f.evidence[k] ?? k}: <strong>{yn(v)}</strong></span>)}
              {[...asked].filter((a) => a in f.evidence).map((a) => <span key={a} className="ev ev-missing">{f.evidence[a]}: {f.missing}</span>)}
              {!evidence.length && ![...asked].some((a) => a in f.evidence) && f.notYet}
            </span>
          </li>
          <li data-state={r?.action === "done" ? "ok" : r?.action === "handoff" ? "person" : ended ? "todo" : r?.action === "confirm" ? "ask" : "todo"}>
            <span className="form-k">{f.result}</span>
            <span className="form-v">{result ?? f.notYet}{r?.case_id && <> · <span className="mono">{r.case_id}</span></>}{r?.card_status === "Blocked" && <> · {t.blocked}</>}</span>
          </li>
        </ol>
      )}

      {lastBank && (
        <div className={`prompt ${ended ? "prompt-end" : ""}`} aria-live="polite">
          <span className="prompt-k">{f.now}</span>
          <p className="msg-text">{lastBank.text}</p>
          {lastBank.reply && <Why reply={lastBank.reply} lang={p.lang} />}
        </div>
      )}
      {pickable && r!.candidates.map((c, i) => (
        <button key={c.transaction_id} className="candidate" onClick={() => submit(`${p.lang === "es" ? "Es la compra" : "É a compra"} ${c.transaction_id}`)} disabled={p.busy}>
          <span className="candidate-n">{i + 1}</span>
          <span>{c.merchant || t.noMerchant}<small>{c.date.slice(8, 10)}/{c.date.slice(5, 7)}/{c.date.slice(0, 4)} {c.date.slice(11)}</small></span>
          <strong>{money(c.amount, c.currency, p.lang)} {c.currency}</strong>
        </button>
      ))}
      {r?.action === "reauth" && (
        <div className="reauth">{t.reauth} <button className="btn btn-small" onClick={p.onReauth} disabled={p.busy}>{t.reauthBtn}</button></div>
      )}
      {quick.length > 0 && <div className="quick">{quick.map((q) => <button key={q} className="chip-btn" onClick={() => submit(q)} disabled={p.busy}>{q}</button>)}</div>}
      {!ended ? (
        <form className="composer" onSubmit={(e) => { e.preventDefault(); submit(text); }}>
          <textarea id="dispute-input" aria-label={f.write} value={text} rows={2} onChange={(e) => setText(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(text); } }}
                    placeholder={f.write} disabled={p.busy} />
          <button className="btn btn-primary" disabled={p.busy || !text.trim()}>{p.busy ? "…" : t.send}</button>
        </form>
      ) : (
        <p className="dispute-end">{t.ended} · <button className="link-btn" onClick={p.onNewChat}>{t.newChat}</button></p>
      )}
      {p.msgs.some((m) => m.role === "customer") && (
        <div className="history">
          <button className="why-toggle" aria-expanded={showHistory} onClick={() => setShowHistory(!showHistory)}>{f.history}</button>
          {showHistory && <ul>{p.msgs.map((m, i) => <li key={i} data-role={m.role}>{m.text}</li>)}</ul>}
        </div>
      )}
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
        {p.tab === "chat" && <Dispute {...p} />}
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
