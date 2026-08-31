# Tournament Data Visualization Design

## Status

Approved in architectural brainstorming on 2026-08-30. This document authorizes design documentation only. It does not authorize implementation.

## Goal

Add trustworthy, publication-ready tournament reporting to the existing PTCG Deck Analysis service. The primary user is a content creator reviewing completed Regional-level and larger tournaments; the secondary user is a competitive researcher studying past results. The product structure is:

```text
Tournament list → Tournament overview → Archetype family report → Variant report
```

The interactive web report supports exploration, phase switching, linked highlighting, and family-to-variant drill-down. Each publishable analysis module also exports a self-contained 1080×1350 PNG for social-media use. The same normalized facts, metric definitions, and report-module payloads serve both outputs and remain reusable by a future WeChat Mini Program.

## Non-goals

- Predict the next metagame or recommend a deck for a future event.
- Analyze live or unfinished events in the MVP.
- Build a free-form dashboard, BI tool, or arbitrary cross-filter system.
- Cover every long-tail family and variant with a complete report in the MVP.
- Add a separate Mini Program backend or implement the Mini Program in this project.
- Add a database, data warehouse, message queue, scheduled streaming pipeline, or real-time ingestion system.
- Support PDF, full-page export, 16:9 images, square images, or multiple PNG templates in the MVP.
- Treat Limitless Labs' internal JSON endpoints as a guaranteed, versioned public API.

## Selected Direction

Use a normalized tournament fact layer plus modular report APIs. Raw source responses are cached first, normalized into source-independent facts, and then processed by one metric/report layer. The web UI and PNG renderer consume the same report-module objects and do not recalculate metrics.

Two alternatives were rejected:

1. **Browser-side direct calculation.** This has the lowest initial backend cost, but spreads metric semantics into the UI, makes PNG and web results easier to diverge, couples users directly to upstream changes, and provides little reuse for a future Mini Program.
2. **Fully pre-generated reports.** Immutable report artifacts are easy to reproduce, but phase and family/variant combinations multiply artifacts, interactive exploration becomes rigid, and report structure becomes too tightly coupled to the generation pipeline.

The selected hybrid keeps completed-event snapshots reproducible while retaining a stable, reusable API and modest interactive flexibility.

## Data Sources and Provenance

The Limitless Labs adapter collects and caches the following JSON resources for each tournament and division:

- tournament metadata;
- aggregate decks data, including players, `day2s`, total W/L/T, and the source's phase records;
- final standings, including placement, archetype, the source's Phase 2 qualifier flag (raw field `day2`), Top Cut, drop, and disqualification fields;
- every declared pairing round;
- player decklists;
- per-variant matchup aggregates used only as a reconciliation reference.

Every verified snapshot records the tournament ID, division, source provider, source `updated_at` when present, fetch time, declared round count, and schema version owned by this project. Finished-event reports use the latest verified local snapshot and do not depend on a live request during browsing or PNG export. Refreshing a completed event is explicit; a malformed refresh never replaces the last verified snapshot.

Limitless currently exposes machine-readable JSON through its SvelteKit pages and `mew.limitlesstcg.com/labs/data/tcg` endpoints. These endpoints are structured and fetchable but undocumented and unversioned. Their long-term compatibility is therefore unknown and is isolated behind the source adapter.

## Metric Definitions

### Populations and phases

- **Phase 1 population:** players with a known archetype in the tournament deck aggregate. Players without a deck classification are excluded from archetype share denominators and disclosed separately. Late players with a known archetype remain included, matching the Limitless decks view.
- **Phase 2 population:** players marked by the source's raw `day2` qualifier field. Phase 2 share uses all Phase 2 players with a known archetype as its denominator.
- **Top Cut population:** players marked `topcut=1` by the source. This source field may include tied-for-eighth play-in entrants, not only the final Top 8, and is never replaced with a placement threshold.
- **Overall record:** the source-consistent official W/L/T record across the completed event, including unknown and procedural results.
- **Phase 1 and Phase 2 records:** the source's phase records. A pairing-round split is accepted only when one unique boundary reproduces those records across the event. Phase 1 pairings are rounds at or below the boundary; Phase 2 pairings are rounds above it. A Phase 2 round remains Phase 2 even if played on calendar Day 1. If the boundary cannot be resolved uniquely, phase-dependent local matchup calculations are blocked rather than guessed.

For New Orleans 0070, rounds 1–8 reproduce Phase 1 and rounds 9–18 reproduce Phase 2 source records. The pairing payload does not identify elimination rounds, so Top Cut cannot be separated from post-boundary matchups for this snapshot; the report discloses that limitation and does not invent a second boundary. When explicit pairing-stage metadata exists, identified Top Cut pairings are excluded from Phase 2 matchups.

### Shares, performance, and conversion

- Archetype share is `archetype players / known-archetype players` at the current family/variant grain and phase.
- Win rate is `(wins + ties / 3) / (wins + losses + ties)`. A tie is not half a win.
- Archetype conversion is `Phase 2 players / Phase 1 players`.
- Field baseline conversion is `all known-archetype Phase 2 players / all known-archetype Phase 1 players`.
- The product does not label the field baseline as Limitless' “Expected Conversion Rate”; no authoritative definition for that phrase was confirmed.

### Matchups

Matchups are computed from unique pairings with known archetypes on both sides. Family reports map both participants to family IDs before aggregation; variant reports retain variant IDs. The observed matchup win rate uses the same one-third tie formula.

Self-match samples count each unique pairing once, even though an upstream variant matchup aggregate may contain two player-side results. `unknown` opponents and source procedural results are excluded from opponent win-rate bars and disclosed as separate counts. They remain part of the official Overall record when matching the source headline.

The main matchup chart includes only rows with at least 30 unique matches. Rows below 30 display `Insufficient sample (n=…)`; zero matches display `No matches`. Values are labeled observed win rates, not causal or predictive favorable/unfavorable claims.

### Archetype families and variants

The default grain is archetype family; users may drill down to qualifying variants. Source `sup_identifier`/`sup_name` fields seed family membership. Corrections use a versioned, explicit mapping keyed by tournament and variant ID; names are not heuristically merged. All modules follow the selected grain, preventing family populations from being paired with variant performance.

A variant qualifies for a full report shell when it has at least 10 Phase 1 players, matching the existing dataset qualification floor. Individual modules may still be degraded by their own sample or coverage gates.

### Deck composition

Deck composition groups equivalent printings by canonical card name while representative lists preserve set and collector number. For the selected event, grain, and competition stage:

- appearance rate ≥80%: Core;
- appearance rate ≥30% and <80%: Common;
- appearance rate ≥5% and <30%: Tech;
- appearance rate <5%: Rare/Other.

Each row shows appearance rate and average copies when present. Phase 1 and Phase 2 classification requires at least 10 valid decklists and at least 60% decklist coverage, where coverage is `valid decklists / eligible players`. Top Cut has no count or coverage threshold: any non-zero valid-list sample is classified and rendered. Top Cut samples with fewer than 10 valid lists are visibly labeled `Small sample — descriptive only`; zero valid lists remains unavailable. Every stage always shows eligible players, valid lists, and coverage.

Phase 2 rows compare with Phase 1, and Top Cut rows compare with Phase 2. Each card exposes its appearance-rate change in percentage points and its average-copies-when-present change when both stages contain the card. Cards whose absolute appearance-rate change is at least 15 percentage points receive `More common` or `Less common`. Top Cut change tags are explicitly descriptive and never imply statistical significance.

Representative lists are up to three valid lists with the best final placements in the current selection, ordered deterministically by placement, points, then player ID.

## System Architecture and Data Flow

The design has four layers with one-way dependencies:

1. **Source snapshot layer:** the Limitless adapter fetches, validates at the transport/schema boundary, and caches immutable raw JSON plus provenance.
2. **Normalized fact layer:** depends only on verified snapshots and produces tournaments, phases, players, family/variant membership, unique pairings, official outcomes, and decklists with stable project-owned identifiers.
3. **Metric and report layer:** depends only on normalized facts, performs metric calculation and reconciliation, and emits modular report objects containing values, numerators, denominators, sample sizes, grain, phase, provenance, and publication status.
4. **Delivery layer:** FastAPI exposes report objects to the interactive web client and future API consumers. The PNG renderer consumes the same objects and must not contain separate metric logic.

```text
Limitless Labs
  → raw verified snapshots
  → normalized tournament facts
  → metrics and reconciliation
  → modular report API
  → interactive web report or 4:5 PNG renderer
```

The fact and report layers remain file-backed for the MVP. Report results may be cached by snapshot version, event, grain, selection ID, phase, and module without introducing a database.

## Report API Boundaries

The API exposes stable report resources rather than raw source shapes:

- a tournament report index and eligibility/status metadata;
- an event overview resource;
- an archetype family report resource;
- a variant report resource;
- module-specific PNG export using the same selected event, grain, ID, phase, and snapshot version.

An overview or archetype response is composed of independently status-bearing modules. Clients may render ready modules when a sibling is degraded or blocked. Raw upstream field names and endpoint URLs do not leak into client calculations.

## Product Pages and Navigation

Add a Tournament Reports entry with this navigation path:

```text
Tournament list → Tournament overview → Family report → Variant report
```

Breadcrumbs preserve event and selection context and always provide a return to the overview.

### Tournament overview

The overview presents modules in this order:

1. event identity, completion/update status, player counts, and data scope;
2. the Phase 1 Meta Share Top 10;
3. the Phase 2 Meta Share Top 10;
4. an expandable archetype family ranking.

Phase 1 and Phase 2 distributions use their own known-archetype denominators. Source-driven Top Cut membership remains available in composition and is never inferred from placement.

Expanded family rows reveal variants in place. Phase 1 Meta Share Top 10, Phase 2 Meta Share Top 10, and Archetype Family Ranking sort by accessible Share and Win Rate headers, defaulting to Share descending. Top 10 membership is fixed before display sorting; expanded variants follow the active sort with deterministic tie breakers, and expansion is preserved by family ID.

### Family and variant reports

The family report defaults to the combined family grain. A selector exposes qualifying variants and preserves the current event. Switching grain refreshes every module together.

Modules appear in this order:

1. headline performance metrics;
2. phase performance and top finishers;
3. limited matchup analysis;
4. deck composition;
5. representative top-finishing decklists.

Deck composition defaults to Phase 1 and may switch to Phase 2 or Top Cut. Observed Matchups supports Overall, Phase 1, and Phase 2. Matchup tables sort by accessible Opponent, Matches, and Observed Win Rate headers, defaulting to Matches descending. Sorting is immutable and deterministic. Every module visibly states current event, family/variant grain, and stage.

## PNG Output

Each publishable visualization module has its own `Export PNG` action. The MVP supports one canvas only: 1080×1350 pixels (4:5 portrait). It does not export the surrounding page navigation.

Every PNG is self-contained and includes:

- report/module title;
- tournament name and date;
- selected family or variant and phase where applicable;
- the core chart or report content;
- player, match, or decklist sample size;
- concise denominator and tie-handling notes;
- data source, source update/fetch provenance, and project attribution.

The renderer uses the exact report-module payload currently displayed. Export is allowed only for a module in `ready` state and for the snapshot version shown on screen. Font loading, wrapping, legends, and footnotes must fit without clipping at the target dimensions.

## Data Quality Gates

A snapshot becomes verified only after all applicable gates pass:

1. successful upstream responses and required schema/type validation;
2. a completed event with coherent tournament metadata and declared round count;
3. presence of every declared pairing round;
4. pairing-derived event W/L/T exactly matching final standings;
5. local variant W/L/T and phase totals matching the decks aggregate;
6. local per-variant matchup W/L/T, including unknown and procedural buckets, matching the upstream matchup reference;
7. valid family membership with no variant assigned to multiple families;
8. decklist validity and explicit coverage calculation by event, grain, and phase.

Reconciliation occurs at variant grain before family aggregation. This makes family results explainable and prevents two variant-level errors from canceling out in a family total.

New Orleans 0070 is the canonical reconciliation fixture. Required Dragapult values are:

| Metric | Expected value |
| --- | ---: |
| Overall record | 3278–2466–1021 |
| Overall win rate | 53.49% |
| Phase 1 record / win rate | 2611–1873–849 / 54.27% |
| Phase 2 record / win rate | 667–593–172 / 50.58% |
| Phase 1 → Phase 2 | 749 → 240 |
| Conversion | 32.04% |

## Module States and Publication Protection

Every module has one of three states:

- **Ready:** required source data, reconciliation, and module-specific thresholds pass. The module is visible and exportable.
- **Degraded:** the report can state a truthful limited result, such as insufficient matchup sample or insufficient decklist count/coverage. The module shows the reason and available counts but no misleading classification or comparison graphic. It is not exportable.
- **Blocked:** required schema, pairing rounds, phase resolution, or reconciliation failed. The module shows a concise unavailable/validation-failed state and is not exportable.

`unknown` and procedural counts are not themselves failures when they reconcile with the source; they are disclosed exclusions. A schema-incompatible refresh, missing pairing round, or source/local discrepancy blocks only the affected modules and never silently falls back to approximate values. Unaffected ready modules remain available.

## MVP Scope

The MVP is accepted at the following breadth:

- every mounted, completed tournament generates a tournament overview;
- each event's Top 10 families by Phase 1 player count generates a family report;
- variants within those families with at least 10 Phase 1 players generate a report shell;
- all report shells include the agreed module sequence, with module-specific ready/degraded/blocked states;
- every ready visualization module can export a compliant 4:5 PNG;
- long-tail families and non-qualifying variants show an explicit insufficient-sample status rather than disappearing or presenting unstable conclusions.

## Later Scope

Later iterations may extend complete report coverage to every family and variant, add new seasons/divisions, add additional export sizes or formats, support richer statistical uncertainty, and expose the same report API to a WeChat Mini Program. These are not MVP acceptance requirements.

## Verification and Acceptance Criteria

### Metric tests

Unit-level fixtures cover:

- one-third tie weighting and zero-match behavior;
- known-archetype share denominators and missing classifications;
- Phase 2 conversion and field baseline;
- source-driven Top Cut membership;
- family/variant aggregation without double counting;
- self-match unique-pairing counts;
- unknown/procedural separation;
- the 30-match matchup gate;
- decklist coverage and the Core/Common/Tech/Rare thresholds;
- deterministic representative-list selection.

### Golden reconciliation

The 0070 fixture must reproduce the documented Dragapult values. Pairing-derived event, phase, variant, opponent, unknown, and procedural W/L/T must reconcile exactly with the cached source aggregates. An intentional mismatch must produce the defined blocked state.

### Dataset breadth

Every mounted, completed event must render an overview without live upstream access. Each event's Top 10 family reports and qualifying variant reports must expose every module in a valid ready/degraded/blocked state. Long-tail selections must show the expected insufficient-sample treatment.

### Interaction acceptance

- Hover details show the correct players, share, and record.
- Sorting overview tables preserves fixed membership and family expansion state.
- Drill-down uses an explicit action and preserves event context.
- Family/variant switching refreshes all modules to one grain.
- Deck composition and matchup phase controls update only their defined module state and never reuse stale values.

### PNG acceptance

Every ready module exports exactly 1080×1350 pixels. At the target size, titles, values, legends, labels, footnotes, sample sizes, metric definitions, event context, and provenance are readable and unclipped. The exported content must match the displayed event, grain, phase, snapshot version, and metric values.

### Exceptional-state acceptance

Fixtures cover upstream schema changes, missing rounds, unresolved phase boundaries, local/source reconciliation differences, unknown/procedural outcomes, matchup samples below 30, fewer than 10 valid decklists, and decklist coverage below 60%. Each case must produce the specified module state and prevent PNG export unless the module remains `ready`.
