# Data quality report — run `20260929T085224-e808a9`

As of 2026-06-17T12:00:00+00:00 · contracts dictionary-v1.0.0/contracts-v1

| Table | new files | bronze rows | rejected lines | duplicates removed | silver rows | quarantined | identity conflicts | nulled FKs |
|---|---|---|---|---|---|---|---|---|
| branches | 0 | 350 | 0 | 0 | 350 | - | - | - |
| customers | 0 | 150,000 | 0 | 0 | 150,000 | - | - | {'registration_branch_id': 149995} |
| products | 0 | 400,000 | 0 | 0 | 400,000 | - | - | - |
| transactions | 0 | 4,425,008 | 0 | 0 | 4,425,008 | - | - | - |
| complaints | 0 | 67,095 | 0 | 0 | 67,095 | - | - | - |
| call_center_interactions | 0 | 686,296 | 0 | 0 | 686,296 | - | - | - |
| daily_exchange_rates | 0 | 13,164 | 0 | 0 | 13,164 | - | - | - |

## Contract findings

**branches**
- domain_violations: `{"country": {"México": 175}, "geographic_zone": {"Urbana": 350}}`
- range_violations: `{"longitude": 167}`

**customers**
- domain_violations: `{"country": {"México": 74907}}`

## Freshness

Policy: daily batch; the newest partition may lag the run by at most 2 days (ADR-012).

| Table | newest process_date | lag (days) | status | rows processed > 1 day after the event |
|---|---|---|---|---|
| transactions | 2026-06-17 | 0 | fresh | 0 |
| complaints | 2026-06-17 | 0 | fresh | 0 |
| call_center_interactions | 2026-06-17 | 0 | fresh | 0 |

## Gold

- card_products: 140,040 rows
- card_transactions: 1,547,432 rows
- customer_dim: 150,000 rows
- dispute_complaints: 13,580 rows
- fraud_alert_candidates: 6 rows

Demo store: {'customers': 323, 'products': 525, 'transactions': 2366}
