# ADR-032 — A column-profile gate: a delivery must look like the history it joins
- **Status:** accepted · **Date:** 2026-10-01 · extends ADR-028

## Context
The gates of ADR-028 count rows (conservation, volume) and check a few gold invariants (USD amount present, unique
ids). Contracts check types, domains and required columns. None of them sees the commonest upstream break in practice:
a source system that keeps sending rows but stops filling a column (a renamed field, a failed join on their side).
Every row passes its contract when the column is optional, the volume is normal, and gold quietly loses the merchant
name the dispute flow searches on.

## Decision
- Each silver step records a **column profile**: the null share of every contracted column in the rows this run
  recomputed, in the rows it kept, and in the whole table (`TableReport.profile`; the table shares go to
  `runs.jsonl` as `null_share`).
- A gate compares the rows this run brought with a reference: the rows kept (incremental run) or, in a full rebuild,
  the last published run. The worst column decides. **Block** at +20 percentage points of nulls (the previous gold
  stays published, exit code 2); **warn** at +5 points. Not judged below 200 rows (too noisy).

## Evidence
- Fixture test: a new day whose merchant names are all empty passes every contract and row count, is **blocked** by
  `transactions: column profile` (detail names `merchant_name`) and the previous gold is byte-identical; an ordinary
  delivery passes.
- Organizer data, the held-back last week delivered incrementally (`make data-proof`): no false alarm. Largest jumps:
  complaints `affected_product_id` +4.5 points (444 rows), transactions `transaction_category` +0.8 (29,159 rows),
  call-center `customer_detected_accent` +0.2 (4,333 rows). A full rebuild compares with the last published run: +0.0.

## Trade-offs
- Null share only; a value-distribution check (new category values, a shifted amount distribution) would catch other
  breaks. Domains already catch new values on contracted enums; amounts are left to the USD-coverage gate.
- Thresholds are fixed numbers, not learned from run history; with daily runs a per-column control chart would be the
  next step.
- One more scan of each silver table per run (`count(col)` per column, twice): +0.1–0.3 s on 4.4M transactions.
