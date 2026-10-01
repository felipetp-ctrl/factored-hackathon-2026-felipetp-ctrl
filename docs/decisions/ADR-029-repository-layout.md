# ADR-029 — Repository layout and conventions
- **Status:** accepted · **Date:** 2026-09-30

## Context
The repository grew over a 10-day sprint: two deploy targets were tried (Fly.io, then Render + Vercel), evaluation runs
accumulated under mixed names, lint rules lived in the Makefile and in CI separately, and there was no license, no
editor settings and no index for `docs/`, `eval/` or `ml/`. Judges read the repository cold, often from GitHub links
already shared in the submission.

## Decision
Bring the repository to common open-source practice **without moving or renaming any tracked file**:
1. **Standard root files:** `LICENSE` (MIT), `.editorconfig`, `.gitattributes` (binary and generated files; lockfiles,
   generated docs and `eval/results/` collapsed in diffs and left out of language stats), `backend/.python-version`
   (3.12) and `frontend/.nvmrc` + `engines` (Node 22.x, the version CI and the Dockerfile use).
2. **One source for tool settings:** ruff rules in `backend/pyproject.toml`, read by both `make lint` and CI.
3. **Self-documenting commands:** `make` alone lists every target by group; `make check` runs what CI runs.
4. **Indexes instead of moves:** `docs/README.md`, `eval/README.md` (every set and every run, headline runs marked)
   and `ml/README.md`; the README shows the tree.
5. **Remove what is not used:** the Fly.io configs (deploy is Render + Vercel since 2026-09-28).
6. **Local notes stay local:** personal working notes live in a gitignored `notes/` folder.

## Alternatives considered
- **Rename `eval/results/` runs to one scheme and docs to kebab-case.** Cleaner names, but every report, ADR and
  traceability row links to these paths, and links already given to judges would break. An index gives the same
  readability at no risk.
- **Archive invalid and discarded runs** (`*-INVALID-*`, `hard-v1-discarded`). Rejected: keeping failures is part of
  the evaluation method (ADR-009); the index labels them instead.
- **pre-commit hooks, Dependabot, CONTRIBUTING, issue templates.** Usual for a team project; for a solo submission
  they add noise (Dependabot PRs during judging) without changing what a reader can verify. `make check` covers the
  local gate.
- **Monorepo tool (pnpm workspaces / Turborepo).** One Python and one TypeScript app share no code; a Makefile is enough.

## Consequences
- No URL changes; CI runs the same rules as before (`F`, `E9`).
- `engines.node = 22.x` also tells Vercel which Node version to build with, so it no longer depends on the project setting.
- Generated files must stay listed in `.gitattributes` when new ones are added.
