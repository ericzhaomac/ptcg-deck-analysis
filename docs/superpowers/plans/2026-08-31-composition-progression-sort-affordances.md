# Composition Progression and Sort Affordances Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline in this existing feature worktree. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fourth `Composition Progression` view that interprets Phase 1, Phase 2, and Top Cut composition together, and make every sortable header visibly and accessibly sortable.

**Architecture:** Derive a pure progression view model in `tournament-reports-core.mjs` from the three existing composition modules; the DOM renderer will present stage concentration/diversity summaries, material rises/falls/disappearances, and Top Cut deviations without changing the API contract or PNG modules. Centralize sort-header text, icon, active state, and accessible labels in a second pure helper so matchup and overview tables share one affordance while ordinary headers remain plain `<th>` elements.

**Tech Stack:** Framework-free JavaScript ES modules, DOM/CSS, Node built-in test runner, pytest/FastAPI static asset integration tests.

**Spec:** User-approved change dated 2026-08-31 in the active conversation.

## Global Constraints

- The fourth composition control is named exactly `Composition Progression` and follows Phase 1, Phase 2, and Top Cut.
- Existing Phase 1/Phase 2 boundary semantics and Top Cut small-sample warnings remain unchanged.
- Progression analysis is derived from existing report payloads and labels card representation within the selected archetype accurately.
- Inactive sortable headers show `↕`; active headers show `↑` or `↓`; non-sortable headers have no icon, pointer, or hover treatment.
- Sorting remains immutable, deterministic, keyboard accessible, and display-only; PNG ordering remains canonical.
- Preserve the responsive visual language and do not touch the running 8011 terminal.

---

### Task 1: Pure three-stage composition analysis and fourth tab

**Files:**
- Modify: `app/static/tournament-reports-core.mjs`
- Modify: `app/static/tournament-reports.js`
- Modify: `app/static/styles.css`
- Test: `tests/frontend/tournament-reports-core.test.mjs`

**Interfaces:**
- Produce: `COMPOSITION_TABS`, ordered as Phase 1, Phase 2, Top Cut, Composition Progression.
- Produce: `buildCompositionProgressionModel(report)`, returning stage sample summaries, represented/core card counts, core-slot concentration, per-card stage rates, material risers/fallers/disappearances, and Top Cut deviations.

- [ ] **Step 1: Write failing tests** with literal three-stage fixtures that prove ordering, sample summaries, concentration/diversity calculations, rise/fall/disappearance classification, Top Cut deviations, small-sample disclosure, and source immutability.
- [ ] **Step 2: Run `node --test tests/frontend/tournament-reports-core.test.mjs`** and confirm failures are missing exports/behavior.
- [ ] **Step 3: Implement the minimal pure model** using appearance rate and `appearance_rate * average_when_present` for core-slot concentration; material change is the existing 15 percentage-point threshold.
- [ ] **Step 4: Run the focused Node test to green.**
- [ ] **Step 5: Render the fourth tab** with heading `Deck Composition Progression: Phase 1 → Phase 2 → Top Cut`, analytical summary cards, stage-flow rows, and an explicit Top Cut descriptive warning when applicable.
- [ ] **Step 6: Add responsive CSS** for the stage summary, flow visualization, and callout grid, then rerun the focused test.

### Task 2: Sortable versus ordinary table-header affordances

**Files:**
- Modify: `app/static/tournament-reports-core.mjs`
- Modify: `app/static/tournament-reports.js`
- Modify: `app/static/styles.css`
- Test: `tests/frontend/tournament-reports-core.test.mjs`
- Test: `tests/test_static_app.py`

**Interfaces:**
- Produce: `tableHeaderPresentation(label, sortKey, sort)`, which returns `{sortable: false, label}` for ordinary headers and sortable text/icon/ARIA/next-direction fields otherwise.

- [ ] **Step 1: Write failing tests** proving inactive sortable headers expose `↕`, active headers expose only the current `↑`/`↓`, the accessible action names the next direction, and non-sortable headers expose no icon or sort semantics.
- [ ] **Step 2: Run focused Node/static-asset tests** and confirm the expected missing-helper failures.
- [ ] **Step 3: Make `sortableHeader` consume the shared model**, set `aria-sort`, `aria-label`, active data state, and a hidden-from-assistive-technology icon while leaving ordinary headers untouched.
- [ ] **Step 4: Replace hyperlink styling** with full-cell hover/active/focus-visible treatment and subtle inactive icons.
- [ ] **Step 5: Run focused tests and inspect the 8011 UI** at desktop and narrow widths, including keyboard focus and active/inactive headers.

### Task 3: Review, full verification, and feature commit

**Files:**
- Review only the files changed by Tasks 1–2 and this plan.

- [ ] **Step 1: Run the focused frontend and static integration tests.**
- [ ] **Step 2: Run `PYTHONPATH=. .venv/bin/python -m pytest -q` and `node --test tests/frontend/*.test.mjs` fresh.**
- [ ] **Step 3: Run JavaScript syntax checks, inspect `git diff --check`, diff/stat, and status, and request an independent code review.**
- [ ] **Step 4: Resolve Critical/Important review findings and repeat affected verification.**
- [ ] **Step 5: Commit with `feat: add composition progression analysis` and record the final hash.**
