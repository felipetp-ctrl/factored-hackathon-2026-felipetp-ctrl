# ADR-018 — Conversation fixes from the v0.0.1 review
- **Status:** accepted · **Date:** 2026-09-27

## Context
Reading the test-v2 transcripts showed behaviour the oracle scored as correct but a customer would not accept:
an out-of-scope customer who said "no, thanks" twice kept getting "which purchase?"; a conversation that started in
Spanish ended in Portuguese after a mixed-language "sim"; amounts were printed as 1,575,714.48 to customers who write
1.575.714,48; and the re-login in the expired-session scenario was invisible in the transcript.

## Decision
- **Language is fixed after the customer's first message.** The chosen language (UI) may be changed by the first
  message only; later mixed-language turns do not flip the replies.
- **Ending politely.** "No, nothing to dispute" before a charge is chosen closes the conversation with a goodbye; a
  second out-of-scope request in a row closes with a redirect to the app or an agent. Messages after the end get
  "this conversation has ended", not the last outcome again. Answers to evidence questions are never read as goodbye.
- **Local formats.** Portuguese readers and ARS/COP amounts use 1.234,56; MXN/USD amounts in Spanish keep 1,234.56;
  dates are dd/mm/yyyy.
- **Visible re-login.** Evaluation transcripts record `[customer signed in again]`; the simulator ignores it. The app
  offers "sign in again and resend".

## Consequences
The eval oracle is unchanged, so these fixes do not move the reported numbers; they change what customers read.
They were found by reading held-out transcripts, so any future run of test-v2 is no longer fully blind for these
behaviours (noted here; test-v1/test-v2 results in the README were produced before the change).
