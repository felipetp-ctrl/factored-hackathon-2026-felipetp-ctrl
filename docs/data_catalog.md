# Data catalog

Generated from `pipeline/contracts.py` and the last published run (`20261001T034257-6618d1`).

Owner: dispute operations data (hackathon team) · Refresh: daily batch after each `process_date` closes · Freshness SLA: newest partition at most 2 days behind · Publication: write-audit-publish with quality gates (row conservation, volume drop ≤ 1%, USD amount missing ≤ 1%, quarantine ≤ 5% as a warning) · Lineage: [ADR-012](decisions/ADR-012-data-pipeline.md), [ADR-028](decisions/ADR-028-incremental-silver-and-gates.md)

## Gold (what the service reads)

| Table | Grain | Built from | Rules | Used by | Rows |
|---|---|---|---|---|---|
| `card_transactions` | one row per card transaction | silver transactions ⋈ products (card types) ⟕ daily_exchange_rates | `amount_usd` filled from the reported value, the USD identity or the daily FX rate; `amount_usd_source` says which | demo store → bank tools (search, get), evaluation sets | 1,547,432 |
| `card_products` | one row per card product | silver products where the type is a card | — | demo store → `block_card`, card status | 140,040 |
| `customer_dim` | one row per customer | silver customers ⟕ complaints (repeat-complainer flag) | country normalised (México → Mexico) for the policy thresholds | policy (country, repeat complainer) | 150,000 |
| `dispute_complaints` | one row per unrecognised-charge complaint | silver complaints (category Transactions) ⋈ customers | — | problem analysis, PQR backtest, written-complaint channel | 13,580 |
| `fraud_alert_candidates` | one row per transaction to alert on | silver transactions | approved, fraud_score ≥ 35, last 48 h before the run's as-of time | fraud-alert channel (ADR-020) | 6 |

## Silver (typed, contract-checked, one row per key)

### `branches`

Source `branches.csv` · key `branch_id` · newest wins by `branch_opening_date` · 350 rows

| Column | Type | Required | Allowed values / range | References |
|---|---|---|---|---|
| `branch_id` | VARCHAR | yes |  |  |
| `branch_code` | VARCHAR | yes |  |  |
| `branch_name` | VARCHAR | yes |  |  |
| `branch_type` | VARCHAR | yes | Main, Express, Premium, Corporate |  |
| `address` | VARCHAR | yes |  |  |
| `city` | VARCHAR | yes |  |  |
| `state` | VARCHAR | yes |  |  |
| `country` | VARCHAR | yes | Mexico, Colombia, Argentina |  |
| `postal_code` | VARCHAR |  |  |  |
| `geographic_zone` | VARCHAR | yes | Urban, Suburban, Rural |  |
| `phone` | VARCHAR | yes |  |  |
| `email` | VARCHAR |  |  |  |
| `opening_time` | VARCHAR | yes |  |  |
| `closing_time` | VARCHAR | yes |  |  |
| `has_atms` | BOOLEAN | yes |  |  |
| `atm_count` | DOUBLE |  | 0 …  |  |
| `has_teller_windows` | BOOLEAN | yes |  |  |
| `teller_window_count` | DOUBLE |  | 0 …  |  |
| `latitude` | DOUBLE |  | -56 … 33 |  |
| `longitude` | DOUBLE |  | -118 … -53 |  |
| `branch_opening_date` | DATE | yes |  |  |
| `branch_status` | VARCHAR | yes | Active, Temporarily Closed, Closed |  |

### `customers`

Source `customers.csv` · key `customer_id` · newest wins by `last_updated` · 150,000 rows
· identity (never changes on re-delivery): `document_number, date_of_birth`

| Column | Type | Required | Allowed values / range | References |
|---|---|---|---|---|
| `customer_id` | VARCHAR | yes |  |  |
| `document_number` | VARCHAR | yes |  |  |
| `document_type` | VARCHAR | yes | DNI, CURP, CC, CE, Passport, Pasaporte, INE, RFC |  |
| `first_name` | VARCHAR | yes |  |  |
| `last_name` | VARCHAR | yes |  |  |
| `date_of_birth` | DATE | yes |  |  |
| `gender` | VARCHAR |  | M, F, O |  |
| `email` | VARCHAR |  |  |  |
| `mobile_phone` | VARCHAR |  |  |  |
| `landline_phone` | VARCHAR |  |  |  |
| `address` | VARCHAR |  |  |  |
| `city` | VARCHAR | yes |  |  |
| `state` | VARCHAR | yes |  |  |
| `country` | VARCHAR | yes | Mexico, Colombia, Argentina |  |
| `postal_code` | VARCHAR |  |  |  |
| `detected_accent` | VARCHAR |  | mexican, colombian, argentine, neutral |  |
| `segment` | VARCHAR | yes | Premium, Plus, Basic, Student |  |
| `credit_score` | DOUBLE |  | 300 … 850 |  |
| `estimated_monthly_income` | DOUBLE |  | 0 …  |  |
| `occupation` | VARCHAR |  |  |  |
| `marital_status` | VARCHAR |  |  |  |
| `education_level` | VARCHAR |  |  |  |
| `registration_date` | TIMESTAMP | yes |  |  |
| `registration_branch_id` | VARCHAR | yes |  | `branches.branch_id` (optional: orphan nulled) |
| `customer_status` | VARCHAR | yes | Active, Inactive, Suspended, Closed |  |
| `last_updated` | TIMESTAMP | yes |  |  |
| `accepts_marketing` | BOOLEAN | yes |  |  |

### `products`

Source `products.csv` · key `product_id` · newest wins by `last_updated` · 400,000 rows
· identity (never changes on re-delivery): `customer_id, product_number`

| Column | Type | Required | Allowed values / range | References |
|---|---|---|---|---|
| `product_id` | VARCHAR | yes |  |  |
| `customer_id` | VARCHAR | yes |  | `customers.customer_id` (essential: orphan quarantined) |
| `product_type` | VARCHAR | yes |  |  |
| `product_number` | VARCHAR | yes |  |  |
| `currency` | VARCHAR | yes | MXN, COP, ARS, USD |  |
| `current_balance` | DOUBLE | yes |  |  |
| `credit_limit` | DOUBLE |  | 0 …  |  |
| `interest_rate` | DOUBLE |  | 0 … 300 |  |
| `opening_date` | DATE | yes |  |  |
| `expiration_date` | DATE |  |  |  |
| `opening_branch_id` | VARCHAR | yes |  | `branches.branch_id` (optional: orphan nulled) |
| `product_status` | VARCHAR | yes | Active, Blocked, Closed, Suspended |  |
| `opening_channel` | VARCHAR | yes | Branch, Web, App, Call Center |  |
| `has_linked_app` | BOOLEAN | yes |  |  |
| `days_past_due` | DOUBLE |  | 0 …  |  |
| `last_transaction_date` | TIMESTAMP |  |  |  |
| `last_updated` | TIMESTAMP | yes |  |  |

### `transactions`

Source `transactions/**/*.csv` · key `transaction_id` · newest wins by `process_date` · 4,425,008 rows
· identity (never changes on re-delivery): `customer_id, product_id`

| Column | Type | Required | Allowed values / range | References |
|---|---|---|---|---|
| `transaction_id` | VARCHAR | yes |  |  |
| `transaction_date` | TIMESTAMP | yes |  |  |
| `process_date` | DATE | yes |  |  |
| `product_id` | VARCHAR | yes |  | `products.product_id` (essential: orphan quarantined) |
| `customer_id` | VARCHAR | yes |  | `customers.customer_id` (essential: orphan quarantined) |
| `transaction_type` | VARCHAR | yes | Deposit, Withdrawal, Transfer, Payment, Purchase, Adjustment |  |
| `transaction_category` | VARCHAR |  |  |  |
| `amount` | DOUBLE | yes |  |  |
| `currency` | VARCHAR | yes | MXN, COP, ARS, USD |  |
| `amount_usd` | DOUBLE |  |  |  |
| `channel` | VARCHAR | yes | ATM, Branch, Web, App, POS, Transfer |  |
| `branch_id` | VARCHAR |  |  |  |
| `merchant_name` | VARCHAR |  |  |  |
| `merchant_category` | VARCHAR |  |  |  |
| `transaction_country` | VARCHAR | yes |  |  |
| `transaction_city` | VARCHAR |  |  |  |
| `transaction_status` | VARCHAR | yes | Approved, Declined, Pending, Reversed |  |
| `response_code` | VARCHAR |  |  |  |
| `is_fraud` | BOOLEAN | yes |  |  |
| `fraud_score` | DOUBLE |  | 0 … 100 |  |
| `latitude` | DOUBLE |  | -90 … 90 |  |
| `longitude` | DOUBLE |  | -180 … 180 |  |

### `complaints`

Source `complaints/**/*.csv` · key `complaint_id` · newest wins by `process_date` · 67,095 rows
· identity (never changes on re-delivery): `customer_id`

| Column | Type | Required | Allowed values / range | References |
|---|---|---|---|---|
| `complaint_id` | VARCHAR | yes |  |  |
| `creation_date` | TIMESTAMP | yes |  |  |
| `process_date` | DATE | yes |  |  |
| `customer_id` | VARCHAR | yes |  | `customers.customer_id` (essential: orphan quarantined) |
| `case_type` | VARCHAR | yes | Complaint, Claim, Request, Suggestion |  |
| `category` | VARCHAR | yes |  |  |
| `subcategory` | VARCHAR |  |  |  |
| `reception_channel` | VARCHAR | yes | Call Center, Email, Web, App, Branch, Regulator |  |
| `affected_product_id` | VARCHAR |  |  | `products.product_id` (optional: orphan nulled) |
| `related_branch_id` | VARCHAR |  |  |  |
| `origin_interaction_id` | VARCHAR |  |  |  |
| `description` | VARCHAR | yes |  |  |
| `claimed_amount` | DOUBLE |  | 0 …  |  |
| `currency` | VARCHAR |  |  |  |
| `priority` | VARCHAR | yes | Low, Medium, High, Critical |  |
| `status` | VARCHAR | yes | Open, In Process, Escalated, Resolved, Closed, Rejected |  |
| `assigned_agent_id` | VARCHAR |  |  |  |
| `assignment_date` | TIMESTAMP |  |  |  |
| `first_response_date` | TIMESTAMP |  |  |  |
| `resolution_date` | TIMESTAMP |  |  |  |
| `closing_date` | TIMESTAMP |  |  |  |
| `sla_breached` | BOOLEAN | yes |  |  |
| `resolution_days` | DOUBLE |  | 0 …  |  |
| `resolution` | VARCHAR |  |  |  |
| `compensation_granted` | DOUBLE |  | 0 …  |  |
| `resolution_satisfaction` | DOUBLE |  | 1 … 5 |  |
| `is_repeat_complainer` | BOOLEAN | yes |  |  |

### `call_center_interactions`

Source `call_center_interactions/**/*.csv` · key `interaction_id` · newest wins by `process_date` · 686,296 rows

| Column | Type | Required | Allowed values / range | References |
|---|---|---|---|---|
| `interaction_id` | VARCHAR | yes |  |  |
| `interaction_date` | TIMESTAMP | yes |  |  |
| `process_date` | DATE | yes |  |  |
| `customer_id` | VARCHAR | yes |  | `customers.customer_id` (essential: orphan quarantined) |
| `agent_id` | VARCHAR |  |  |  |
| `interaction_type` | VARCHAR | yes |  |  |
| `channel` | VARCHAR | yes |  |  |
| `contact_reason` | VARCHAR | yes |  |  |
| `reason_category` | VARCHAR | yes |  |  |
| `duration_seconds` | DOUBLE |  | 0 …  |  |
| `wait_time_seconds` | DOUBLE |  | 0 …  |  |
| `was_resolved` | BOOLEAN |  |  |  |
| `requires_followup` | BOOLEAN | yes |  |  |
| `detected_sentiment` | VARCHAR |  |  |  |
| `sentiment_score` | DOUBLE |  | -1 … 1 |  |
| `customer_detected_accent` | VARCHAR |  |  |  |
| `agent_used_accent` | VARCHAR |  |  |  |
| `was_escalated` | BOOLEAN | yes |  |  |
| `mentioned_products` | VARCHAR |  |  |  |
| `has_transcript` | BOOLEAN | yes |  |  |
| `has_recording` | BOOLEAN | yes |  |  |

### `daily_exchange_rates`

Source `daily_exchange_rates.csv` · key `date, source_currency, target_currency` · newest wins by `date` · 13,164 rows

| Column | Type | Required | Allowed values / range | References |
|---|---|---|---|---|
| `date` | DATE | yes |  |  |
| `source_currency` | VARCHAR | yes |  |  |
| `target_currency` | VARCHAR | yes |  |  |
| `exchange_rate` | DOUBLE | yes | 0 …  |  |
| `buy_rate` | DOUBLE |  | 0 …  |  |
| `sell_rate` | DOUBLE |  | 0 …  |  |
| `source` | VARCHAR |  |  |  |

