# Data quality report — run `20261001T034257-6618d1`

As of 2026-06-17T12:00:00+00:00 · contracts dictionary-v1.0.0/contracts-v1 · **published** (full run; write-audit-publish, ADR-028)

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

## Quality gates

Gold is staged, audited, then published; a failed **block** gate keeps the previous gold.

| Gate | Severity | Result | Detail |
|---|---|---|---|
| branches: row conservation | block | ✅ pass | bronze 350 = no key 0 + superseded 0 + silver 350 + quarantined 0 |
| branches: quarantine share | warn | ✅ pass | 0.00% of keys quarantined (limit 5%) |
| branches: volume | block | ✅ pass | 350 -> 350 rows (-0.00%) since run 20261001T034152-f4e48c |
| branches: column profile | block | ✅ pass | worst column branch_id: 0.0% null in 350 rows of this run vs 0.0% in run 20261001T034152-f4e48c (+0.0%) |
| branches: column profile drift | warn | ✅ pass | worst column branch_id: 0.0% null in 350 rows of this run vs 0.0% in run 20261001T034152-f4e48c (+0.0%) |
| customers: row conservation | block | ✅ pass | bronze 150,000 = no key 0 + superseded 0 + silver 150,000 + quarantined 0 |
| customers: quarantine share | warn | ✅ pass | 0.00% of keys quarantined (limit 5%) |
| customers: volume | block | ✅ pass | 150,000 -> 150,000 rows (-0.00%) since run 20261001T034152-f4e48c |
| customers: column profile | block | ✅ pass | worst column customer_id: 0.0% null in 150,000 rows of this run vs 0.0% in run 20261001T034152-f4e48c (+0.0%) |
| customers: column profile drift | warn | ✅ pass | worst column customer_id: 0.0% null in 150,000 rows of this run vs 0.0% in run 20261001T034152-f4e48c (+0.0%) |
| products: row conservation | block | ✅ pass | bronze 400,000 = no key 0 + superseded 0 + silver 400,000 + quarantined 0 |
| products: quarantine share | warn | ✅ pass | 0.00% of keys quarantined (limit 5%) |
| products: volume | block | ✅ pass | 400,000 -> 400,000 rows (-0.00%) since run 20261001T034152-f4e48c |
| products: column profile | block | ✅ pass | worst column product_id: 0.0% null in 400,000 rows of this run vs 0.0% in run 20261001T034152-f4e48c (+0.0%) |
| products: column profile drift | warn | ✅ pass | worst column product_id: 0.0% null in 400,000 rows of this run vs 0.0% in run 20261001T034152-f4e48c (+0.0%) |
| transactions: row conservation | block | ✅ pass | bronze 4,425,008 = no key 0 + superseded 0 + silver 4,425,008 + quarantined 0 |
| transactions: quarantine share | warn | ✅ pass | 0.00% of keys quarantined (limit 5%) |
| transactions: volume | block | ✅ pass | 4,425,008 -> 4,425,008 rows (-0.00%) since run 20261001T034152-f4e48c |
| transactions: column profile | block | ✅ pass | worst column transaction_id: 0.0% null in 4,425,008 rows of this run vs 0.0% in run 20261001T034152-f4e48c (+0.0%) |
| transactions: column profile drift | warn | ✅ pass | worst column transaction_id: 0.0% null in 4,425,008 rows of this run vs 0.0% in run 20261001T034152-f4e48c (+0.0%) |
| complaints: row conservation | block | ✅ pass | bronze 67,095 = no key 0 + superseded 0 + silver 67,095 + quarantined 0 |
| complaints: quarantine share | warn | ✅ pass | 0.00% of keys quarantined (limit 5%) |
| complaints: volume | block | ✅ pass | 67,095 -> 67,095 rows (-0.00%) since run 20261001T034152-f4e48c |
| complaints: column profile | block | ✅ pass | worst column complaint_id: 0.0% null in 67,095 rows of this run vs 0.0% in run 20261001T034152-f4e48c (+0.0%) |
| complaints: column profile drift | warn | ✅ pass | worst column complaint_id: 0.0% null in 67,095 rows of this run vs 0.0% in run 20261001T034152-f4e48c (+0.0%) |
| call_center_interactions: row conservation | block | ✅ pass | bronze 686,296 = no key 0 + superseded 0 + silver 686,296 + quarantined 0 |
| call_center_interactions: quarantine share | warn | ✅ pass | 0.00% of keys quarantined (limit 5%) |
| call_center_interactions: volume | block | ✅ pass | 686,296 -> 686,296 rows (-0.00%) since run 20261001T034152-f4e48c |
| call_center_interactions: column profile | block | ✅ pass | worst column interaction_id: 0.0% null in 686,296 rows of this run vs 0.0% in run 20261001T034152-f4e48c (+0.0%) |
| call_center_interactions: column profile drift | warn | ✅ pass | worst column interaction_id: 0.0% null in 686,296 rows of this run vs 0.0% in run 20261001T034152-f4e48c (+0.0%) |
| daily_exchange_rates: row conservation | block | ✅ pass | bronze 13,164 = no key 0 + superseded 0 + silver 13,164 + quarantined 0 |
| daily_exchange_rates: quarantine share | warn | ✅ pass | 0.00% of keys quarantined (limit 5%) |
| daily_exchange_rates: volume | block | ✅ pass | 13,164 -> 13,164 rows (-0.00%) since run 20261001T034152-f4e48c |
| daily_exchange_rates: column profile | block | ✅ pass | worst column date: 0.0% null in 13,164 rows of this run vs 0.0% in run 20261001T034152-f4e48c (+0.0%) |
| daily_exchange_rates: column profile drift | warn | ✅ pass | worst column date: 0.0% null in 13,164 rows of this run vs 0.0% in run 20261001T034152-f4e48c (+0.0%) |
| gold card_transactions: not empty | block | ✅ pass | 1,547,432 rows |
| gold card_products: not empty | block | ✅ pass | 140,040 rows |
| gold customer_dim: not empty | block | ✅ pass | 150,000 rows |
| gold card_transactions: USD amount present | block | ✅ pass | 13 of 1,547,432 without amount_usd (0.00%) |
| gold card_transactions: unique ids | block | ✅ pass | 0 duplicate ids |
| transactions: freshness | warn | ✅ pass | newest 2026-06-17, lag 0 days |
| complaints: freshness | warn | ✅ pass | newest 2026-06-17, lag 0 days |
| call_center_interactions: freshness | warn | ✅ pass | newest 2026-06-17, lag 0 days |

## Run

| Step | Mode | Seconds |
|---|---|---|
| branches | full | 0.02 |
| customers | full | 0.61 |
| products | full | 0.5 |
| transactions | full | 4.86 |
| complaints | full | 0.42 |
| call_center_interactions | full | 0.98 |
| daily_exchange_rates | full | 0.03 |
| gold | - | 0.47 |

## Gold

- card_products: 140,040 rows
- card_transactions: 1,547,432 rows
- customer_dim: 150,000 rows
- dispute_complaints: 13,580 rows
- fraud_alert_candidates: 6 rows

Demo store: {'customers': 323, 'products': 525, 'transactions': 2366}
