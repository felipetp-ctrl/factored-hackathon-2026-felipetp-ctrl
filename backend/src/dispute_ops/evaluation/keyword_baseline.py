"""Rule baseline for the language-understanding component (kept importable here for the evaluation).

The keyword rules live in `dispute_ops.language.keywords`, where the rule-based fallback NLU reuses them."""

from dispute_ops.language.keywords import (  # noqa: F401
    HUMAN, OUT_OF_SCOPE, REASON_PATTERNS, _norm, classify_reason, is_out_of_scope, wants_human,
)
