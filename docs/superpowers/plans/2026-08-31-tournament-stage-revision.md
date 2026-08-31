# Tournament Stage Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline. Do not create another worktree or use subagents for this user-authorized continuation.

**Goal:** Revise tournament reports to use Phase 1/Phase 2 semantics consistently, add stage-aware matchup and composition analysis, and add accessible deterministic table sorting without changing PNG ordering.

**Architecture:** Keep phase semantics and analytical calculations in the Python fact/metric/report layer, returning complete immutable module payloads for all supported stages. Keep transient sorting and expansion state in framework-free frontend helpers, while PNG rendering reads canonical server row order directly.

**Tech Stack:** Python 3.11, Pydantic, pytest, JavaScript ES modules, Node built-in test runner, browser DOM/SVG/Canvas.

**Spec:** User-approved revision dated 2026-08-31, extending `docs/superpowers/specs/2026-08-30-tournament-data-visualization-design.md`.

## Global Constraints

- User-facing and report-contract stage names are exactly Overall, Phase 1, Phase 2, and Top Cut.
- The unique reconciled boundary defines Phase 1 as rounds at or below the boundary and Phase 2 as rounds above it; exclude identifiable Top Cut pairings from Phase 2 but never invent missing round metadata.
- Source `topcut=1` is authoritative and may include play-in entrants tied for eighth; never infer a final Top 8.
- Phase 1 and Phase 2 composition require 10 valid lists and 60% coverage; Top Cut always classifies available valid lists and is labeled descriptive-only below 10 valid lists.
- Sorting is display-only, immutable, deterministic, keyboard accessible, and must not affect PNG canonical ordering.

---

### Task 1: Stage semantics and matchup modules

**Files:**
- Modify: `app/tournament_reports/contracts.py`
- Modify: `app/tournament_reports/metrics.py`
- Modify: `app/tournament_reports/reconciliation.py`
- Modify: `app/tournament_reports/builders.py`
- Test: `tests/test_tournament_metrics.py`
- Test: `tests/test_tournament_reconciliation.py`
- Test: `tests/test_tournament_report_builders.py`
- Test: `tests/test_tournament_report_0070_golden.py`

- [x] Add failing tests for Phase 1/Phase 2 boundary inclusion, Phase 2 Top Cut exclusion where identifiable, all three matchup modules, and New Orleans phase values.
- [x] Run focused tests and confirm failures are caused by missing revised behavior.
- [x] Replace legacy report phase names and implement the minimal stage filtering, reconciliation, payload, and status changes.
- [x] Run the focused Python tests to green and refactor while green.

### Task 2: Composition samples and cross-stage deltas

**Files:**
- Modify: `app/tournament_reports/metrics.py`
- Modify: `app/tournament_reports/reconciliation.py`
- Modify: `app/tournament_reports/builders.py`
- Test: `tests/test_tournament_metrics.py`
- Test: `tests/test_tournament_report_builders.py`

- [x] Add failing tests for Top Cut classification below 10, the deterministic descriptive-only rule, coverage/sample disclosure, and both comparison directions with 15-point tags.
- [x] Run focused tests and confirm expected failures.
- [x] Implement composition rows for Top Cut and attach hand-derived appearance/copy deltas plus descriptive comparison metadata.
- [x] Run focused tests to green and refactor while green.

### Task 3: Accessible immutable frontend sorting and revised composition UI

**Files:**
- Modify: `app/static/tournament-reports-core.mjs`
- Modify: `app/static/tournament-reports.js`
- Modify: `app/static/styles.css`
- Test: `tests/frontend/tournament-reports-core.test.mjs`
- Test: `tests/frontend/tournament-report-png.test.mjs`
- Test: `tests/test_tournament_report_ui_contract.py`

- [x] Add failing frontend tests for matchup and overview sort toggles, deterministic tie-breakers, source immutability, fixed Top 10 membership, expanded-variant ordering, expansion preservation, and canonical PNG order.
- [x] Run focused Node tests and confirm expected failures.
- [x] Implement pure sorting/state helpers and accessible sortable headers; render concise comparison deltas/tags and revised stage controls.
- [x] Run focused frontend and UI-contract tests to green and refactor while green.

### Task 4: Documentation, full verification, and commit

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-30-tournament-data-visualization-design.md`
- Modify: relevant golden fixture expectations only if contract names changed.

- [x] Update terminology, small-sample rule, Top Cut asymmetry, phase limitations, and comparison definitions.
- [x] Run focused tests, then the full Python and frontend suites and record fresh counts.
- [x] Inspect repository scope with Git when metadata is available; otherwise report the exact administrative blocker without rewriting `.git`.
- [x] Commit only the revision on `ericzhaomac/tournament-data-visualization` and record the hash; do not push, merge, deploy, or use port 8010.
