"""The bank's view of every case, whatever channel it came from: one row per flow, with the stage it reached.

Built only from the flow's own state and its append-only audit trail (never from model output), so the board shows
what was verified: Understand -> Decide -> Confirm -> Act -> Verify, then the outcome (resolved, a person, closed)."""

from __future__ import annotations

from typing import Any

from dispute_ops.domain import Channel
from dispute_ops.flow import DisputeFlow, State
from dispute_ops.store import Store

OUTCOME = {State.DONE: "resolved", State.HANDOFF: "person", State.INELIGIBLE: "closed", State.CANCELLED: "closed"}


def _stage(status: str, detail: str = "") -> dict[str, str]:
    return {"status": status, "detail": detail}


def snapshot(flow: DisputeFlow, store: Store) -> dict[str, Any] | None:
    events = store.list_audit(flow.trace_id)
    if not events:
        return None
    kinds = [e.kind for e in events]
    customer_turns = kinds.count("customer_message")
    # a chat opened and never used is not a case yet
    if flow.channel == Channel.CHAT and customer_turns == 0 and flow.txn is None:
        return None
    customer = store.get_customer(flow.customer_id) if flow.customer_id else None
    nlu = [e for e in events if e.kind == "nlu"]
    reader = nlu[-1].data.get("usage", {}).get("model", "") if nlu else ""
    policy = [e for e in events if e.kind == "policy_decision"]
    actions = [e for e in events if e.kind == "action"]
    agent = [e for e in events if e.kind == "agent_action"]
    handoff = next((e.data for e in reversed(events) if e.kind == "handoff"), None)
    final = flow.state in OUTCOME

    # Understand: the charge and the reason are both known
    if flow.txn is not None and flow.reason_code is not None:
        understand = _stage("done", f"{flow.reason_code.value} · {round(flow.confidence * 100)}%")
    elif final:
        understand = _stage("stopped", "charge or reason not established")
    else:
        understand = _stage("active", "finding the charge" if flow.txn is None else "asking what happened")
    # Decide: the policy engine ruled on the case
    if policy:
        last = policy[-1].data
        decide = _stage("done" if last["decision"] != "ineligible" else "stopped",
                        f"{last['decision']} · {', '.join(last['rule_ids'])}")
    else:
        decide = _stage("pending")
    # Confirm: chat and alerts ask the customer; a filed written complaint is the customer's consent
    if flow.channel == Channel.PQR:
        confirm = _stage("done", "filed complaint = consent") if actions else _stage("pending")
    elif "confirm_requested" in kinds:
        confirm = _stage("done" if actions else ("stopped" if final else "active"),
                         "customer said yes" if actions else "summary shown to the customer")
    else:
        confirm = _stage("pending")
    act = _stage("done", " + ".join(a.data["action"] for a in actions)) if actions else _stage("pending")
    if actions:
        failed = [a for a in actions if a.data["status"] != "verified"]
        verify = _stage("stopped" if failed else "done",
                        "read back: " + ", ".join(f"{a.data['action']} {a.data['status']}" for a in actions))
    else:
        verify = _stage("pending")

    outcome = OUTCOME.get(flow.state, "in_progress")
    detail = ""
    if outcome == "person":
        detail = ", ".join(handoff["reason_for_handoff"]) if handoff else ""
        if agent:
            outcome = "person_done"
            detail = f"agent: {agent[-1].data.get('action')}"
    elif outcome == "closed":
        closed = next((e.data for e in reversed(events) if e.kind == "closed"), None)
        detail = (closed or {}).get("reason", "") or (", ".join(flow.last_policy.rule_ids) if flow.last_policy else "")

    txn = flow.txn
    return {
        "trace_id": flow.trace_id,
        "channel": flow.channel.value,
        "language": flow.language,
        "customer_id": flow.customer_id,
        "customer_name": customer.first_name if customer else None,
        "country": customer.country if customer else None,
        "started_at": events[0].at.isoformat(),
        "updated_at": events[-1].at.isoformat(),
        "state": flow.state.value,
        "outcome": outcome,
        "outcome_detail": detail,
        "transaction": None if txn is None else {
            "transaction_id": txn.transaction_id, "merchant": txn.merchant_name, "amount": str(txn.amount),
            "currency": txn.currency, "amount_usd": str(txn.amount_usd), "date": txn.transaction_date.isoformat(),
        },
        "reason_code": flow.reason_code.value if flow.reason_code else None,
        "evidence": dict(flow.evidence),
        "reader": reader,
        "customer_turns": customer_turns,
        "case_id": next((a.data.get("ref") for a in actions if a.data["action"] == "open_dispute"), None)
        or next((a.data.get("case_id") for a in agent if a.data.get("case_id")), None),
        "case_ref": handoff["case_ref"] if handoff else None,
        "stages": {"understand": understand, "decide": decide, "confirm": confirm, "act": act, "verify": verify},
    }
