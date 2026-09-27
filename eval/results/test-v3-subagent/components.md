# test-v3 — component results (fallback NLU, no language-model calls in the system)

Scenario set `test-v3` (42 scenarios, frozen in commit b67fc8e before intent-v2 was trained). Customers played by
Claude Sonnet as a Claude Code subagent that saw only the persona and the transcript (not the code, docs or reports).
One run per variant; both variants received the same customer messages until their replies diverged.

| Component | Rules only | Rules + intent-v2 |
|---|---|---|
| Dispute reason (first reason committed), n = 23 | 22/23 (95.7%, CI 79–99%) | **23/23** (100%, CI 86–100%) |
| Out-of-scope recall (first message) | 4/4 | 4/4 |
| Out-of-scope false positives (first message) | 1/38 | 1/38 |
| Human-request detection | 1/1 | 1/1 |
| Transaction identification | 23/23 | 23/23 |
| End-to-end correct / unsafe | 42/42 · 0/42 | 42/42 · 0/42 |
| Safe automated resolution (in scope) | 25/35 | 25/35 |

**What differed.** `cancelled-sub-00-pt`: the keyword rule for duplicates (`cobrad[oa]s? 2`) matched "fui cobrado
**2**43,12 USD", so the rules-only variant asked "Qual é a outra cobrança idêntica?"; the customer corrected it and the
case still ended right, one turn later. intent-v2 read CANCELLED_RECURRING at p = 0.994.

**What neither caught.** `wrong-amount-01-es`: the merchant name "Super **Ahorro**" (savings) triggered the
out-of-scope keyword on the first message in both variants; the flow recovered (the transaction was identified) and
the case was opened correctly. The keyword precedence of ADR-019 means the classifier cannot overrule it.

**Reading.** With n = 23 the reason difference (23 vs 22) is not statistically significant (one discordant pair);
end-to-end outcomes are identical. The evidence says intent-v2 is at least as good as the rules on independent
messages and fixes a real keyword failure; it does not show a large gain on this set, whose reasons are 65% fraud.

**Simulator caveat.** The original simulator was `claude-sonnet-5` through the API with a fixed system prompt; this
run used Sonnet inside Claude Code with the same rules given as instructions. Same model family, different wrapper.
