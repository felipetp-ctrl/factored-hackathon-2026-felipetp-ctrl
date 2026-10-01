# hard-v1 replay after ADR-031 (grounded evidence, corrected summaries) — partial, by design

Replay of `hard-v1-replay-1001` (same customer messages, same cached Claude readings) on the code after ADR-031.
No API calls.

- **66 of 72 conversations replay identically** (36 free reader, 30 Claude path).
- **6 Claude-path conversations diverge**: the cached reading had filled "card in possession" although the customer
  never said where the card was; the system now drops that reading and asks "¿Tiene la tarjeta con usted?". The next
  cached customer message answered a different question (the old summary), so these 6 cannot be scored without a new
  simulated customer turn. They are listed in `pending_nlu.json`; `report.md` is not written on purpose.

Conversation-level effect of ADR-031 needs a new run with simulated customers (API or subagent).
