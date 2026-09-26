"""Data contracts for the tables the dispute service uses, from the organizer data dictionary v1.0.0.

A contract states column types, which columns are required, allowed values, numeric ranges, the primary
key, how to pick the surviving row among duplicates, and foreign keys. Violations are measured and
reported; only structural breaks (a required column missing, or an unreadable key) stop the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Col:
    type: str = "VARCHAR"
    required: bool = False
    domain: tuple[str, ...] | None = None
    min: float | None = None
    max: float | None = None


@dataclass(frozen=True)
class Contract:
    name: str
    source: str  # glob relative to the raw directory
    pk: tuple[str, ...]
    columns: dict[str, Col]
    order_by: str  # newest-wins ordering for duplicates
    fks: dict[str, str] = field(default_factory=dict)  # column -> "table.column"


V = Col()
REQ = Col(required=True)

CONTRACTS: dict[str, Contract] = {c.name: c for c in [
    Contract(
        name="customers", source="customers.csv", pk=("customer_id",), order_by="last_updated",
        fks={"registration_branch_id": "branches.branch_id"},
        columns={
            "customer_id": REQ, "document_number": REQ,
            "document_type": Col(required=True, domain=("DNI", "CURP", "CC", "CE", "Passport", "Pasaporte", "INE", "RFC")),
            "first_name": REQ, "last_name": REQ, "date_of_birth": Col("DATE", required=True),
            "gender": Col(domain=("M", "F", "O")), "email": V, "mobile_phone": V, "landline_phone": V, "address": V,
            "city": REQ, "state": REQ, "country": Col(required=True, domain=("Mexico", "Colombia", "Argentina")),
            "postal_code": V,
            "detected_accent": Col(domain=("mexican", "colombian", "argentine", "neutral")),
            "segment": Col(required=True, domain=("Premium", "Plus", "Basic", "Student")),
            "credit_score": Col("DOUBLE", min=300, max=850), "estimated_monthly_income": Col("DOUBLE", min=0),
            "occupation": V, "marital_status": V, "education_level": V,
            "registration_date": Col("TIMESTAMP", required=True), "registration_branch_id": REQ,
            "customer_status": Col(required=True, domain=("Active", "Inactive", "Suspended", "Closed")),
            "last_updated": Col("TIMESTAMP", required=True), "accepts_marketing": Col("BOOLEAN", required=True),
        },
    ),
    Contract(
        name="branches", source="branches.csv", pk=("branch_id",), order_by="branch_opening_date",
        columns={
            "branch_id": REQ, "branch_code": REQ, "branch_name": REQ,
            "branch_type": Col(required=True, domain=("Main", "Express", "Premium", "Corporate")),
            "address": REQ, "city": REQ, "state": REQ,
            "country": Col(required=True, domain=("Mexico", "Colombia", "Argentina")), "postal_code": V,
            "geographic_zone": Col(required=True, domain=("Urban", "Suburban", "Rural")),
            "phone": REQ, "email": V, "opening_time": REQ, "closing_time": REQ,
            "has_atms": Col("BOOLEAN", required=True), "atm_count": Col("DOUBLE", min=0),
            "has_teller_windows": Col("BOOLEAN", required=True), "teller_window_count": Col("DOUBLE", min=0),
            "latitude": Col("DOUBLE", min=-56, max=33), "longitude": Col("DOUBLE", min=-118, max=-53),
            "branch_opening_date": Col("DATE", required=True),
            "branch_status": Col(required=True, domain=("Active", "Temporarily Closed", "Closed")),
        },
    ),
    Contract(
        name="products", source="products.csv", pk=("product_id",), order_by="last_updated",
        fks={"customer_id": "customers.customer_id", "opening_branch_id": "branches.branch_id"},
        columns={
            "product_id": REQ, "customer_id": REQ, "product_type": REQ, "product_number": REQ,
            "currency": Col(required=True, domain=("MXN", "COP", "ARS", "USD")),
            "current_balance": Col("DOUBLE", required=True), "credit_limit": Col("DOUBLE", min=0),
            "interest_rate": Col("DOUBLE", min=0, max=300), "opening_date": Col("DATE", required=True),
            "expiration_date": Col("DATE"), "opening_branch_id": REQ,
            "product_status": Col(required=True, domain=("Active", "Blocked", "Closed", "Suspended")),
            "opening_channel": Col(required=True, domain=("Branch", "Web", "App", "Call Center")),
            "has_linked_app": Col("BOOLEAN", required=True), "days_past_due": Col("DOUBLE", min=0),
            "last_transaction_date": Col("TIMESTAMP"), "last_updated": Col("TIMESTAMP", required=True),
        },
    ),
    Contract(
        name="transactions", source="transactions/**/*.csv", pk=("transaction_id",), order_by="process_date",
        fks={"customer_id": "customers.customer_id", "product_id": "products.product_id"},
        columns={
            "transaction_id": REQ, "transaction_date": Col("TIMESTAMP", required=True),
            "process_date": Col("DATE", required=True), "product_id": REQ, "customer_id": REQ,
            "transaction_type": Col(required=True, domain=("Deposit", "Withdrawal", "Transfer", "Payment", "Purchase", "Adjustment")),
            "transaction_category": V, "amount": Col("DOUBLE", required=True),
            "currency": Col(required=True, domain=("MXN", "COP", "ARS", "USD")), "amount_usd": Col("DOUBLE"),
            "channel": Col(required=True, domain=("ATM", "Branch", "Web", "App", "POS", "Transfer")),
            "branch_id": V, "merchant_name": V, "merchant_category": V, "transaction_country": REQ,
            "transaction_city": V,
            "transaction_status": Col(required=True, domain=("Approved", "Declined", "Pending", "Reversed")),
            "response_code": V, "is_fraud": Col("BOOLEAN", required=True), "fraud_score": Col("DOUBLE", min=0, max=100),
            "latitude": Col("DOUBLE", min=-90, max=90), "longitude": Col("DOUBLE", min=-180, max=180),
        },
    ),
    Contract(
        name="complaints", source="complaints/**/*.csv", pk=("complaint_id",), order_by="process_date",
        fks={"customer_id": "customers.customer_id", "affected_product_id": "products.product_id"},
        columns={
            "complaint_id": REQ, "creation_date": Col("TIMESTAMP", required=True), "process_date": Col("DATE", required=True),
            "customer_id": REQ, "case_type": Col(required=True, domain=("Complaint", "Claim", "Request", "Suggestion")),
            "category": REQ, "subcategory": V,
            "reception_channel": Col(required=True, domain=("Call Center", "Email", "Web", "App", "Branch", "Regulator")),
            "affected_product_id": V, "related_branch_id": V, "origin_interaction_id": V, "description": REQ,
            "claimed_amount": Col("DOUBLE", min=0), "currency": V,
            "priority": Col(required=True, domain=("Low", "Medium", "High", "Critical")),
            "status": Col(required=True, domain=("Open", "In Process", "Escalated", "Resolved", "Closed", "Rejected")),
            "assigned_agent_id": V, "assignment_date": Col("TIMESTAMP"), "first_response_date": Col("TIMESTAMP"),
            "resolution_date": Col("TIMESTAMP"), "closing_date": Col("TIMESTAMP"),
            "sla_breached": Col("BOOLEAN", required=True), "resolution_days": Col("DOUBLE", min=0),
            "resolution": V, "compensation_granted": Col("DOUBLE", min=0),
            "resolution_satisfaction": Col("DOUBLE", min=1, max=5), "is_repeat_complainer": Col("BOOLEAN", required=True),
        },
    ),
    Contract(
        name="call_center_interactions", source="call_center_interactions/**/*.csv", pk=("interaction_id",),
        order_by="process_date", fks={"customer_id": "customers.customer_id"},
        columns={
            "interaction_id": REQ, "interaction_date": Col("TIMESTAMP", required=True),
            "process_date": Col("DATE", required=True), "customer_id": REQ, "agent_id": V,
            "interaction_type": REQ, "channel": REQ, "contact_reason": REQ, "reason_category": REQ,
            "duration_seconds": Col("DOUBLE", min=0), "wait_time_seconds": Col("DOUBLE", min=0),
            "was_resolved": Col("BOOLEAN"), "requires_followup": Col("BOOLEAN", required=True),
            "detected_sentiment": V, "sentiment_score": Col("DOUBLE", min=-1, max=1),
            "customer_detected_accent": V, "agent_used_accent": V, "was_escalated": Col("BOOLEAN", required=True),
            "mentioned_products": V, "has_transcript": Col("BOOLEAN", required=True),
            "has_recording": Col("BOOLEAN", required=True),
        },
    ),
    Contract(
        name="daily_exchange_rates", source="daily_exchange_rates.csv",
        pk=("date", "source_currency", "target_currency"), order_by="date",
        columns={
            "date": Col("DATE", required=True), "source_currency": REQ, "target_currency": REQ,
            "exchange_rate": Col("DOUBLE", required=True, min=0), "buy_rate": Col("DOUBLE", min=0),
            "sell_rate": Col("DOUBLE", min=0), "source": V,
        },
    ),
]}

# Load order respects foreign keys (parents first).
ORDER = ["branches", "customers", "products", "transactions", "complaints", "call_center_interactions", "daily_exchange_rates"]
