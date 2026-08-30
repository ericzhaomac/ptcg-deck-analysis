# Tournament Data Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add offline, source-reconciled tournament overview and family/variant reports for every mounted completed event, with linked exploration and publication-safe 1080×1350 module PNG exports.

**Architecture:** Extend the existing file-backed tournament datasets with immutable verified Limitless snapshots, normalize those source payloads into typed tournament facts, and build all metrics and status-bearing report modules on the server. FastAPI exposes stable report resources; the framework-free frontend and browser PNG renderer consume the same module payloads and never recalculate tournament metrics.

**Tech Stack:** Python 3.11, FastAPI 0.115, Pydantic 2.11, standard-library `urllib`/`pathlib`/`json`/`hashlib`, pytest 9, framework-free HTML/CSS/ES modules, Node 26 built-in test runner, SVG and browser Canvas 2D.

**Spec:** `docs/superpowers/specs/2026-08-30-tournament-data-visualization-design.md`

## Global Constraints

- Reports cover completed Regional-level and larger events for retrospective analysis; metagame prediction is out of scope.
- The MVP is file-backed. Do not add a database, data warehouse, queue, scheduler, streaming pipeline, frontend build tool, or live report dependency.
- Treat `https://mew.limitlesstcg.com/labs/data/tcg` as undocumented and unversioned; all source URLs, query parameters, and raw fields stay behind the Limitless adapter.
- A failed refresh must preserve the previous verified snapshot; browsing and PNG export use verified local files only.
- The canonical win-rate formula is `(wins + ties / 3) / (wins + losses + ties)`; never count a tie as one-half win.
- First Phase share denominators include players with a known archetype, not `players_r1`; unknown classifications are disclosed separately.
- Top Cut membership comes from the source `topcut` field; never infer a fixed Top 8.
- A phase boundary is valid only when exactly one round split reproduces every source Day 1/Day 2 variant record; otherwise phase-dependent modules are blocked.
- The default grain is family. Family corrections are explicit, versioned mappings keyed by tournament ID and variant ID; never merge names heuristically.
- A variant report shell requires at least 10 First Phase players. The main matchup chart requires at least 30 unique known-opponent matches.
- Deck composition requires at least 10 valid lists and at least 60% coverage. Buckets are Core `>=80%`, Common `>=30% and <80%`, Tech `>=5% and <30%`, and Rare/Other `<5%`.
- Matchup bars exclude unknown opponents and procedural results, disclose both counts separately, and label results as observed rather than predictive.
- Report module states are exactly `ready`, `degraded`, and `blocked`; only `ready` modules are exportable.
- Every PNG is exactly 1080×1350 pixels and contains title, event/date, selection/phase, chart, sample size, metric notes, source provenance, and project attribution.
- The web UI and PNG renderer consume the same `ReportModule` payload; neither may implement independent metric arithmetic.
- Preserve the existing Analysis, Deck Library, and AI Backend behavior while adding Tournament Reports as a dedicated fourth top-level tab.
- Every production behavior starts with a failing focused test, then the smallest passing implementation, then focused regression tests.
- Use `PYTHONPATH=. python3 -m pytest` for Python tests and `node --test tests/frontend/*.test.mjs` for frontend tests.
- Use the isolated Orca feature worktree for implementation. Do not overwrite `main` or run the feature preview on port 8010.

---

## Files and Interfaces Map

### New backend package

- `app/tournament_reports/contracts.py`: Pydantic API contracts, enums, immutable snapshot manifest models, and typed report-module envelope.
- `app/tournament_reports/snapshots.py`: verified-snapshot loading, raw schema validation, hashing, staging promotion, and last-good pointer management.
- `app/tournament_reports/facts.py`: source-independent facts, family override loading, canonical card identity, unique pairing normalization, and phase-boundary resolution.
- `app/tournament_reports/metrics.py`: pure share, record, conversion, matchup, deck-composition, and representative-list calculations.
- `app/tournament_reports/reconciliation.py`: source/local comparisons, validation issues, and module-state decisions.
- `app/tournament_reports/builders.py`: event overview and archetype report-module construction.
- `app/services/tournament_report_service.py`: dataset resolution, snapshot/fact caching, eligibility checks, and public report service methods.
- `app/api/tournament_reports.py`: thin `/api/v1/tournament-reports` routes and HTTP error translation.

### Operational ingestion

- `scripts/tools/limitless_tournament_snapshot.py`: network adapter and CLI that fetches all raw resources into staging and promotes only a verified snapshot.
- `scripts/tools/limitless_tournament_analysis.py`: delegates shared HTTP/cache primitives to the new adapter while preserving its existing CLI contract.
- `data/config/archetype_family_overrides.json`: versioned explicit family corrections.
- `data/{year}/{event}/{division}/cache/snapshots/{snapshot_version}/`: immutable raw tournament, decks, standings, per-round pairings, decklists, matchup references, and manifest; braces denote runtime values calculated by the adapter.
- `data/{year}/{event}/{division}/cache/verified-snapshot.json`: atomic pointer to the last verified snapshot version.

### Existing application integration

- `app/main.py`: composes `TournamentReportService` and includes the new router.
- `app/static/tournament-reports-core.mjs`: pure navigation, selection, chart-layout, module-state, and export-document helpers.
- `app/static/tournament-reports.js`: report API orchestration and DOM rendering.
- `app/static/app.js`: initializes the report controller and preserves existing three feature controllers.
- `app/static/index.html`: fourth top-level tab and report view containers.
- `app/static/styles.css`: responsive report, chart, state, and export styling.

### Stable interfaces used across tasks

```python
SnapshotStore.load(dataset_dir: Path) -> RawTournamentSnapshot
SnapshotStore.load_candidate(staged_dir: Path, manifest: SnapshotManifest) -> RawTournamentSnapshot
SnapshotStore.promote(dataset_dir: Path, staged_dir: Path, manifest: SnapshotManifest, verification: SnapshotVerification) -> Path
LimitlessSnapshotAdapter.collect(ref: TournamentRef, dataset_dir: Path) -> StagedSnapshot
VerifiedSnapshotRefresher.refresh(ref: TournamentRef, dataset_dir: Path) -> SnapshotManifest
load_family_overrides(path: Path) -> FamilyOverrideSet
normalize_snapshot(snapshot: RawTournamentSnapshot, overrides: FamilyOverrideSet) -> TournamentFacts
resolve_phase_boundary(facts: TournamentFacts) -> int | None
reconcile_tournament(facts: TournamentFacts) -> ReconciliationResult
build_event_overview(facts: TournamentFacts, reconciliation: ReconciliationResult, dataset_id: str) -> EventOverviewResponse
build_archetype_report(facts: TournamentFacts, reconciliation: ReconciliationResult, dataset_id: str, selection: ReportSelection) -> ArchetypeReportResponse
TournamentReportService.list_reports(mounted_dataset_ids: list[str]) -> TournamentReportIndexResponse
TournamentReportService.get_overview(dataset_id: str) -> EventOverviewResponse
TournamentReportService.get_archetype_report(dataset_id: str, selection: ReportSelection) -> ArchetypeReportResponse
```

```javascript
createReportRoute(view, datasetId, grain = null, selectionId = null)
reduceReportSelection(state, action)
buildOverviewChartModel(module, selectedFamilyId)
buildModuleSvg(module, context)
assertExportable(module, context)
exportModulePng(moduleElement, module, context)
```

---

### Task 1: Report contracts and verified snapshot store

**Files:**
- Create: `app/tournament_reports/__init__.py`
- Create: `app/tournament_reports/contracts.py`
- Create: `app/tournament_reports/snapshots.py`
- Create: `tests/test_tournament_snapshots.py`

**Interfaces:**
- Produces: `ReportState`, `ReportGrain`, `ReportPhase`, `Record`, `ReportSelection`, `SourceProvenance`, `ModuleStatus`, `ReportModule`, `SnapshotManifest`, `SnapshotVerification`, and `RawTournamentSnapshot`.
- Produces: `EventIdentity`, `ReportSelectionOption`, `TournamentReportIndexItem`, `TournamentReportIndexResponse`, `EventOverviewResponse`, and `ArchetypeReportResponse` API contracts.
- Produces: `SnapshotValidationError(code: str, message: str)`.
- Produces: `SnapshotStore.load(dataset_dir: Path) -> RawTournamentSnapshot`, `SnapshotStore.load_candidate(staged_dir: Path, manifest: SnapshotManifest) -> RawTournamentSnapshot`, and `SnapshotStore.promote(dataset_dir: Path, staged_dir: Path, manifest: SnapshotManifest, verification: SnapshotVerification) -> Path`.
- `SnapshotManifest.resources` maps stable resource keys such as `pairings/round-01` to `{path, sha256}` records relative to its snapshot directory.

- [ ] **Step 1: Write failing snapshot contract and last-good tests**

```python
def test_promote_writes_immutable_snapshot_and_atomic_pointer(tmp_path):
    dataset_dir, staged_dir = staged_snapshot(tmp_path, snapshot_version="0070-ma-20260614T193759Z")
    manifest = valid_manifest(snapshot_version="0070-ma-20260614T193759Z")

    promoted = SnapshotStore().promote(dataset_dir, staged_dir, manifest, passing_verification())

    assert promoted == dataset_dir / "cache/snapshots/0070-ma-20260614T193759Z"
    assert json.loads((dataset_dir / "cache/verified-snapshot.json").read_text())["snapshot_version"] == manifest.snapshot_version
    assert SnapshotStore().load(dataset_dir).manifest.snapshot_version == manifest.snapshot_version


def test_invalid_refresh_cannot_replace_last_verified_snapshot(tmp_path):
    dataset_dir = install_verified_snapshot(tmp_path, version="good")
    staged_dir = build_staging_dir(tmp_path, missing="pairings/round-02.json")

    with pytest.raises(SnapshotValidationError, match="missing resource"):
        SnapshotStore().promote(dataset_dir, staged_dir, valid_manifest(snapshot_version="bad"), passing_verification())

    assert json.loads((dataset_dir / "cache/verified-snapshot.json").read_text())["snapshot_version"] == "good"
```

- [ ] **Step 2: Run the focused test and observe the missing package failure**

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_snapshots.py -q`

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'app.tournament_reports'`.

- [ ] **Step 3: Define exact report and snapshot contracts**

```python
class ReportState(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class ReportGrain(str, Enum):
    FAMILY = "family"
    VARIANT = "variant"


class ReportPhase(str, Enum):
    FIRST_PHASE = "first_phase"
    DAY1 = "day1"
    DAY2 = "day2"
    TOP_CUT = "top_cut"
    OVERALL = "overall"


class Record(BaseModel):
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    ties: int = Field(ge=0)


class ModuleStatus(BaseModel):
    state: ReportState
    reason_code: str | None = None
    message: str | None = None
    exportable: bool


class SnapshotVerification(BaseModel):
    blocking_issue_codes: tuple[str, ...] = ()


class ReportModule(BaseModel):
    module_id: str
    title: str
    status: ModuleStatus
    grain: ReportGrain | None = None
    phase: ReportPhase
    selection_id: str | None = None
    sample_size: int
    metric_notes: list[str]
    provenance: SourceProvenance
    data: dict[str, Any]
```

- [ ] **Step 4: Implement hash/schema validation and promotion ordering**

Implement `SnapshotStore.promote` so it first requires `SnapshotVerification.blocking_issue_codes == ()`, then validates manifest version `1`, required singleton files, all declared rounds `1..declared_rounds`, every resource SHA-256, and Pydantic raw shapes before moving staging to the manifest-named snapshot directory. Write `verified-snapshot.json.tmp`, call `Path.replace`, and update the pointer only after the immutable directory is complete. Treat an existing byte-identical target as an idempotent success; reject the same version with different hashes rather than mutating it. Add a test proving a structurally valid candidate with a blocking verification issue cannot update the pointer.

```python
def promote(self, dataset_dir: Path, staged_dir: Path, manifest: SnapshotManifest, verification: SnapshotVerification) -> Path:
    if verification.blocking_issue_codes:
        raise SnapshotValidationError("verification_blocked", ",".join(verification.blocking_issue_codes))
    self._validate_staged(staged_dir, manifest)
    target = dataset_dir / "cache" / "snapshots" / manifest.snapshot_version
    self._install_idempotently(staged_dir, target, manifest)
    pointer = dataset_dir / "cache" / "verified-snapshot.json"
    atomic_write_json(pointer, {"snapshot_version": manifest.snapshot_version})
    return target
```

- [ ] **Step 5: Run snapshot tests to green**

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_snapshots.py -q`

Expected: PASS with tests covering missing pointer, malformed JSON, schema mismatch, hash mismatch, missing round, immutable-version collision, successful load, and last-good preservation.

- [ ] **Step 6: Commit the contracts and snapshot store**

```bash
git add app/tournament_reports tests/test_tournament_snapshots.py
git commit -m "feat: add verified tournament snapshot store"
```

---

### Task 2: Limitless raw snapshot collection adapter

**Files:**
- Create: `scripts/tools/limitless_tournament_snapshot.py`
- Create: `scripts/tools/test_limitless_tournament_snapshot.py`
- Modify: `scripts/tools/limitless_tournament_analysis.py`
- Modify: `scripts/tools/test_limitless_tournament_analysis.py`

**Interfaces:**
- Consumes: raw snapshot contracts from Task 1; it does not call `SnapshotStore.promote` before reconciliation exists.
- Produces: `TournamentRef(tournament_id: str, division: str = "MA")`.
- Produces: `LimitlessClient.fetch(endpoint: str, params: dict[str, str | int]) -> dict[str, Any]`.
- Produces: `StagedSnapshot(path: Path, manifest: SnapshotManifest, raw: RawTournamentSnapshot)`.
- Produces: `LimitlessSnapshotAdapter(client: LimitlessClient).collect(ref: TournamentRef, dataset_dir: Path) -> StagedSnapshot`.
- Preserves: the existing `scripts/tools/limitless_tournament_analysis.py` arguments and flat-cache output.

- [ ] **Step 1: Write failing request-shape and complete-resource tests**

```python
def test_collect_fetches_every_declared_round_decklist_and_variant_matchup(tmp_path):
    client = RecordingClient(source_payloads(rounds=3, decklist_player_ids=["11", "12"], variant_ids=["dragapult-ex", "dragapult-dusknoir"]))
    adapter = LimitlessSnapshotAdapter(client=client, clock=fixed_clock)

    staged = adapter.collect(TournamentRef("0070", "MA"), tmp_path / "2026/New_Orleans/MA")

    assert ("pairings", {"tournamentId": "0070", "division": "MA", "round": 1}) in client.calls
    assert ("pairings", {"tournamentId": "0070", "division": "MA", "round": 3}) in client.calls
    assert ("decklist", {"tournamentId": "0070", "playerId": "11"}) in client.calls
    assert ("matchups", {"tournamentId": "0070", "division": "MA", "deckId": "dragapult-ex"}) in client.calls
    assert staged.manifest.declared_rounds == 3
    assert not (tmp_path / "2026/New_Orleans/MA/cache/verified-snapshot.json").exists()
```

- [ ] **Step 2: Run the adapter test and observe the missing module failure**

Run: `PYTHONPATH=. python3 -m pytest scripts/tools/test_limitless_tournament_snapshot.py -q`

Expected: FAIL during collection because `scripts.tools.limitless_tournament_snapshot` does not exist.

- [ ] **Step 3: Implement the six endpoint calls with explicit parameters**

Use these exact endpoint contracts under `https://mew.limitlesstcg.com/labs/data/tcg`:

```python
RESOURCE_REQUESTS = {
    "tournament": ("tournament", lambda ref: {"id": ref.tournament_id, "division": ref.division}),
    "decks": ("decks", lambda ref: {"tournamentId": ref.tournament_id, "division": ref.division}),
    "standings": ("standings", lambda ref: {"tournamentId": ref.tournament_id, "division": ref.division}),
}

pairing_params = {"tournamentId": ref.tournament_id, "division": ref.division, "round": round_number}
decklist_params = {"tournamentId": ref.tournament_id, "playerId": tp_id}
matchup_params = {"tournamentId": ref.tournament_id, "division": ref.division, "deckId": variant_id}
```

Fetch tournament/decks/standings first, derive declared rounds from `tournament.message.round`, decklist IDs from standings rows with `decklist == 1`, and matchup IDs from every non-empty decks `identifier`. Store successful envelopes without flattening their `ok/message` shape.

- [ ] **Step 4: Implement isolated staging and deterministic manifest generation**

Write into a uniquely named directory under `cache/` using atomic per-file replacements. After every resource is present, hash a canonical sorted resource index and generate version `"{tournament_id}-{division_lower}-{content_hash_12}"`, where `content_hash_12` is the first 12 lowercase SHA-256 characters. Record source `updated_at`, UTC fetch time, schema version `1`, resource hashes, and declared round count, then return `StagedSnapshot` without creating or updating `verified-snapshot.json`. On any request or schema failure, remove only that staging directory and leave the verified pointer unchanged.

```python
def collect(self, ref: TournamentRef, dataset_dir: Path) -> StagedSnapshot:
    staged_dir = Path(tempfile.mkdtemp(prefix="snapshot-candidate-", dir=dataset_dir / "cache"))
    try:
        self._fetch_all_resources(ref, staged_dir)
        manifest = build_manifest(ref, staged_dir, fetched_at=self.clock())
        raw = SnapshotStore().load_candidate(staged_dir, manifest)
        return StagedSnapshot(path=staged_dir, manifest=manifest, raw=raw)
    except Exception:
        shutil.rmtree(staged_dir)
        raise
```

- [ ] **Step 5: Reuse the HTTP retry primitive from the adapter in the legacy generator**

Keep `_fetch_json(endpoint, params, cache_path)` as a compatibility wrapper in `limitless_tournament_analysis.py`, but delegate transport/retry validation to `LimitlessClient`. Preserve the current three attempts, exponential delays `1.0`, `2.0`, and atomic cache writes so existing script tests remain meaningful.

```python
def _fetch_json(endpoint: str, params: dict[str, Any], cache_path: Path) -> dict[str, Any]:
    return LimitlessClient(attempts=3, retry_delay_seconds=1.0).fetch_cached(
        endpoint=endpoint,
        params=params,
        cache_path=cache_path,
    )
```

- [ ] **Step 6: Run focused script tests**

Run: `PYTHONPATH=. python3 -m pytest scripts/tools/test_limitless_tournament_snapshot.py scripts/tools/test_limitless_tournament_analysis.py -q`

Expected: PASS, including unsuccessful payload, transient retry, exact query parameters, all declared resources, no premature verified pointer, failed collection cleanup, and legacy CLI compatibility.

- [ ] **Step 7: Commit the adapter slice**

```bash
git add scripts/tools/limitless_tournament_snapshot.py scripts/tools/test_limitless_tournament_snapshot.py scripts/tools/limitless_tournament_analysis.py scripts/tools/test_limitless_tournament_analysis.py
git commit -m "feat: fetch complete Limitless tournament snapshots"
```

---

### Task 3: Normalized tournament fact layer and family mapping

**Files:**
- Create: `app/tournament_reports/facts.py`
- Create: `data/config/archetype_family_overrides.json`
- Create: `tests/test_tournament_facts.py`
- Create: `tests/fixtures/tournament_reports/minimal_verified_snapshot/manifest.json`
- Create: `tests/fixtures/tournament_reports/minimal_verified_snapshot/tournament.json`
- Create: `tests/fixtures/tournament_reports/minimal_verified_snapshot/decks.json`
- Create: `tests/fixtures/tournament_reports/minimal_verified_snapshot/standings.json`
- Create: `tests/fixtures/tournament_reports/minimal_verified_snapshot/pairings/round-01.json`
- Create: `tests/fixtures/tournament_reports/minimal_verified_snapshot/pairings/round-02.json`
- Create: `tests/fixtures/tournament_reports/minimal_verified_snapshot/decklists/11.json`
- Create: `tests/fixtures/tournament_reports/minimal_verified_snapshot/matchups/dragapult-ex.json`

**Interfaces:**
- Consumes: `RawTournamentSnapshot` from Task 1.
- Produces frozen dataclasses `TournamentFact`, `VariantFact`, `PlayerFact`, `PairingFact`, `CardFact`, `DecklistFact`, `MatchupReference`, and `TournamentFacts`; `CardFact` exposes normalized `card_name`, source `display_name`, `set_code`, `collector_number`, and `count`.
- Produces: `FamilyIdentity(family_id: str, family_name: str)` and `FamilyOverrideSet(version: int, mappings: dict[tuple[str, str], FamilyIdentity])`.
- Produces: `load_family_overrides(path: Path) -> FamilyOverrideSet`.
- Produces: `normalize_snapshot(snapshot: RawTournamentSnapshot, overrides: FamilyOverrideSet) -> TournamentFacts`.
- Produces: `resolve_phase_boundary(facts: TournamentFacts) -> int | None`.

- [ ] **Step 1: Write failing normalization and phase-boundary tests**

```python
def test_normalize_uses_source_family_and_unique_pairings(raw_snapshot, empty_overrides):
    facts = normalize_snapshot(raw_snapshot, empty_overrides)

    assert facts.variants["dragapult-dusknoir"].family_id == "dragapult-ex"
    assert facts.players["11"].top_cut is True
    assert facts.pairings[0].pairing_id == "round-01-table-1"
    assert facts.pairings[0].player1_tp_id == "11"


def test_phase_boundary_requires_one_split_matching_every_variant(raw_snapshot, empty_overrides):
    facts = normalize_snapshot(raw_snapshot, empty_overrides)

    assert resolve_phase_boundary(facts) == 1
    assert resolve_phase_boundary(replace(facts, source_phase_records=ambiguous_records())) is None
```

- [ ] **Step 2: Run fact tests and observe missing symbols**

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_facts.py -q`

Expected: FAIL importing `normalize_snapshot` and the fact dataclasses.

- [ ] **Step 3: Implement source-independent immutable fact types**

```python
@dataclass(frozen=True)
class PairingFact:
    pairing_id: str
    round_number: int
    table_number: int
    player1_tp_id: str | None
    player2_tp_id: str | None
    player1_variant_id: str | None
    player2_variant_id: str | None
    outcome: Literal["player1", "player2", "tie", "procedural"]


@dataclass(frozen=True)
class TournamentFacts:
    tournament: TournamentFact
    variants: Mapping[str, VariantFact]
    players: Mapping[str, PlayerFact]
    pairings: tuple[PairingFact, ...]
    decklists: Mapping[str, DecklistFact]
    matchup_references: Mapping[str, MatchupReference]
    source_phase_records: Mapping[str, Mapping[int, Record]]
    provenance: SourceProvenance
```

Normalize pairing `winner == -1` as procedural, `winner == 0` as a tie, and a winner matching either participant as that participant's win. Reject duplicate `(round, table)` identities and a winner that matches neither participant.

- [ ] **Step 4: Implement family and card identity rules**

Seed `family_id/family_name` from `sup_identifier/sup_name`; apply only exact override keys formatted as `"{tournament_id}:{variant_id}"`. Validate that one variant resolves to exactly one family. Group equivalent printings by trimmed, case-folded canonical card name for composition, while retaining original name, set, collector number, and count in each representative decklist entry.

```python
def family_for(tournament_id: str, raw_variant: dict[str, Any], overrides: FamilyOverrideSet) -> FamilyIdentity:
    variant_id = str(raw_variant["identifier"])
    source = FamilyIdentity(
        family_id=str(raw_variant["sup_identifier"]),
        family_name=str(raw_variant["sup_name"]),
    )
    return overrides.mappings.get((tournament_id, variant_id), source)


def canonical_card_name(name: str) -> str:
    return " ".join(name.split()).casefold()


card = CardFact(
    card_name=canonical_card_name(raw_card["name"]),
    display_name=str(raw_card["name"]).strip(),
    set_code=str(raw_card["set"]).strip(),
    collector_number=str(raw_card["number"]).strip(),
    count=int(raw_card["count"]),
)
```

The committed configuration starts as:

```json
{
  "version": 1,
  "mappings": {}
}
```

- [ ] **Step 5: Implement unique phase-boundary search**

For every candidate split `1..declared_rounds-1`, aggregate player-side W/L/T by variant for rounds at or below the split and above the split. Return the split only when all variants exactly reproduce parsed source `records["1"]` and `records["2"]` and exactly one candidate passes; otherwise return `None`.

```python
def resolve_phase_boundary(facts: TournamentFacts) -> int | None:
    matches = [
        split
        for split in range(1, facts.tournament.declared_rounds)
        if phase_records_for_split(facts, split) == facts.source_phase_records
    ]
    return matches[0] if len(matches) == 1 else None
```

- [ ] **Step 6: Run normalization tests to green**

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_facts.py -q`

Expected: PASS for family source fields, exact override, duplicate mapping rejection, pairing identities/outcomes, canonical cards, one valid boundary, no valid boundary, and multiple valid boundaries.

- [ ] **Step 7: Commit normalized facts**

```bash
git add app/tournament_reports/facts.py data/config/archetype_family_overrides.json tests/test_tournament_facts.py tests/fixtures/tournament_reports/minimal_verified_snapshot
git commit -m "feat: normalize tournament facts and families"
```

---

### Task 4: Pure tournament metrics

**Files:**
- Create: `app/tournament_reports/metrics.py`
- Create: `tests/test_tournament_metrics.py`

**Interfaces:**
- Consumes: `TournamentFacts`, `ReportGrain`, `ReportPhase`, and `Record`.
- Produces: `win_rate(record: Record) -> float | None`.
- Produces typed results `DistributionMetric`, `ConversionMetric`, `MatchupMetric`, `DeckCompositionMetric`, and `RepresentativeList`.
- Produces: `distribution(facts: TournamentFacts, grain: ReportGrain, phase: ReportPhase) -> DistributionMetric`.
- Produces: `conversion(facts: TournamentFacts, grain: ReportGrain) -> ConversionMetric`.
- Produces: `matchups(facts: TournamentFacts, selection: ReportSelection, phase: ReportPhase) -> MatchupMetric`.
- Produces: `deck_composition(facts: TournamentFacts, selection: ReportSelection, phase: ReportPhase) -> DeckCompositionMetric`.
- Produces: `representative_lists(facts: TournamentFacts, selection: ReportSelection, phase: ReportPhase, limit: int = 3) -> tuple[RepresentativeList, ...]`.

- [ ] **Step 1: Write failing formula and denominator tests**

```python
def test_win_rate_weights_ties_as_one_third():
    assert win_rate(Record(wins=3278, losses=2466, ties=1021)) == pytest.approx(0.5349, abs=0.00005)
    assert win_rate(Record(wins=0, losses=0, ties=0)) is None


def test_first_phase_distribution_uses_known_archetype_players(facts):
    metric = distribution(facts, ReportGrain.FAMILY, ReportPhase.FIRST_PHASE)

    assert metric.known_players == 12
    assert metric.unknown_players == 1
    assert metric.rows[0].share == pytest.approx(metric.rows[0].players / 12)
```

- [ ] **Step 2: Run formula tests and observe the missing module failure**

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_metrics.py -q`

Expected: FAIL during collection because `app.tournament_reports.metrics` does not exist.

- [ ] **Step 3: Implement distributions, official records, and conversion**

Aggregate by family or variant consistently. First Phase includes every known-classification deck aggregate row; Day 2 and Top Cut use source player flags; field conversion is `known Day 2 players / known First Phase players`. Return numerators, denominators, raw W/L/T, and unrounded floats; round only at API serialization/display boundaries.

```python
def win_rate(record: Record) -> float | None:
    matches = record.wins + record.losses + record.ties
    return None if matches == 0 else (record.wins + record.ties / 3) / matches


def conversion(facts: TournamentFacts, grain: ReportGrain) -> ConversionMetric:
    first_phase = population_counts(facts, grain, ReportPhase.FIRST_PHASE)
    day2 = population_counts(facts, grain, ReportPhase.DAY2)
    return ConversionMetric.from_counts(first_phase=first_phase, day2=day2)
```

- [ ] **Step 4: Write failing matchup tests**

```python
def test_matchups_count_each_pairing_once_and_separate_exclusions(facts):
    metric = matchups(facts, ReportSelection(ReportGrain.FAMILY, "dragapult-ex"), ReportPhase.OVERALL)

    assert metric.rows_by_id["dragapult-ex"].matches == 1
    assert metric.rows_by_id["dragapult-ex"].player_side_record == Record(wins=1, losses=1, ties=0)
    assert metric.unknown_count == 2
    assert metric.procedural_count == 1
    assert metric.rows_by_id["small-deck"].sample_state == "insufficient"
```

- [ ] **Step 5: Implement matchup aggregation and thresholds**

Select each unique `PairingFact` once. At family grain map both variants before grouping, including self-matchups. `MatchupRow.matches` is the unique-pairing sample; `MatchupRow.player_side_record` retains both sides for a self-match, so one decisive self-match is one sample with one win and one loss, while one tied self-match is one sample with two ties. Calculate observed win rate from `player_side_record`, matching the upstream player-side W/L/T semantics without doubling the displayed sample. Exclude unknown/procedural rows from opponent bars; mark rows `ready` at 30 unique matches, `insufficient` from 1 through 29, and `none` at zero. Permit only `overall` and `day2`; Day 2 requires the resolved boundary and uses rounds above it.

```python
def matchup_sample_state(matches: int) -> Literal["ready", "insufficient", "none"]:
    if matches == 0:
        return "none"
    return "ready" if matches >= 30 else "insufficient"


def pairing_in_phase(pairing: PairingFact, phase: ReportPhase, boundary: int | None) -> bool:
    if phase is ReportPhase.OVERALL:
        return True
    if phase is ReportPhase.DAY2 and boundary is not None:
        return pairing.round_number > boundary
    return False
```

- [ ] **Step 6: Write failing deck-composition and representative-list tests**

```python
@pytest.mark.parametrize((appearance, expected), [(0.80, "core"), (0.30, "common"), (0.05, "tech"), (0.049, "rare")])
def test_composition_bucket_boundaries(appearance, expected):
    assert composition_bucket(appearance) == expected


def test_representative_lists_are_deterministic(facts):
    selection = ReportSelection(ReportGrain.FAMILY, "dragapult-ex")
    rows = representative_lists(facts, selection, ReportPhase.FIRST_PHASE)
    assert [row.player_tp_id for row in rows] == ["11", "15", "14"]
```

- [ ] **Step 7: Implement coverage-aware card metrics and list selection**

Compute `coverage = valid_list_count / eligible_player_count`, appearance rate over valid lists, and average copies only among lists containing the card. Return classification rows only when valid lists are at least 10 and coverage is at least `0.60`; otherwise return counts and coverage with an empty classified-row collection. Sort representatives by placement ascending, points descending, then `tp_id` ascending and cap at three.

```python
def composition_bucket(appearance_rate: float) -> Literal["core", "common", "tech", "rare"]:
    if appearance_rate >= 0.80:
        return "core"
    if appearance_rate >= 0.30:
        return "common"
    if appearance_rate >= 0.05:
        return "tech"
    return "rare"


eligible_for_classification = valid_list_count >= 10 and coverage >= 0.60
classified_rows = tuple(rows) if eligible_for_classification else ()
```

- [ ] **Step 8: Run all metric tests to green**

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_metrics.py -q`

Expected: PASS for tie weighting, zero matches, phase populations, missing classifications, conversion, Top Cut flags, family aggregation, self-matchups, exclusions, 30-match gate, composition thresholds, coverage gates, and deterministic lists.

- [ ] **Step 9: Commit metrics**

```bash
git add app/tournament_reports/metrics.py tests/test_tournament_metrics.py
git commit -m "feat: calculate tournament report metrics"
```

---

### Task 5: Reconciliation, quality gates, and module-state policy

**Files:**
- Create: `app/tournament_reports/reconciliation.py`
- Create: `tests/test_tournament_reconciliation.py`
- Modify: `scripts/tools/limitless_tournament_snapshot.py`
- Modify: `scripts/tools/test_limitless_tournament_snapshot.py`

**Interfaces:**
- Consumes: normalized facts and metric primitives from Tasks 3–4.
- Produces: `ValidationIssue(code: str, message: str, affected_modules: frozenset[str], blocks_publication: bool)`.
- Produces: `ReconciliationResult(phase_boundary: int | None, issues: tuple[ValidationIssue, ...], variant_records: Mapping[str, Record])`.
- Produces: `reconcile_tournament(facts: TournamentFacts) -> ReconciliationResult`.
- Produces: `module_status(module_id: str, reconciliation: ReconciliationResult, *, sample_size: int, valid_lists: int | None = None, coverage: float | None = None) -> ModuleStatus`.
- Produces: `verify_candidate_snapshot(snapshot: RawTournamentSnapshot, overrides: FamilyOverrideSet) -> SnapshotVerification`.
- Produces: `VerifiedSnapshotRefresher(adapter: LimitlessSnapshotAdapter, store: SnapshotStore, family_overrides: FamilyOverrideSet).refresh(ref: TournamentRef, dataset_dir: Path) -> SnapshotManifest`, which collects, normalizes, reconciles, and promotes only when verification has no blocking issue.

- [ ] **Step 1: Write failing exact-reconciliation tests**

```python
def test_reconciliation_happens_at_variant_grain_before_family_rollup(facts):
    result = reconcile_tournament(facts)

    assert result.issues == ()
    assert result.variant_records["dragapult-ex"] == Record(wins=8, losses=3, ties=1)


def test_equal_and_opposite_variant_errors_do_not_cancel(facts):
    corrupted = corrupt_variant_records(facts, first_delta=1, second_delta=-1)
    result = reconcile_tournament(corrupted)

    assert {issue.code for issue in result.issues} == {"variant_record_mismatch"}
```

- [ ] **Step 2: Run reconciliation tests and observe missing symbols**

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_reconciliation.py -q`

Expected: FAIL importing `reconcile_tournament`.

- [ ] **Step 3: Implement ordered quality gates**

Check completed metadata, coherent declared rounds, all round facts present, pairing-derived player records against standings, variant overall and phase totals against decks, local opponent/unknown/procedural rows against each source matchup reference, single family membership, and decklist validity/coverage. Record issues per affected module rather than throwing after the snapshot schema boundary.

```python
def reconcile_tournament(facts: TournamentFacts) -> ReconciliationResult:
    issues: list[ValidationIssue] = []
    phase_boundary = resolve_phase_boundary(facts)
    issues.extend(check_completed_and_rounds(facts))
    issues.extend(check_standings_records(facts))
    issues.extend(check_variant_records(facts, phase_boundary))
    issues.extend(check_matchup_references(facts, phase_boundary))
    issues.extend(check_family_membership(facts))
    issues.extend(check_decklists(facts))
    return ReconciliationResult(
        phase_boundary=phase_boundary,
        issues=tuple(issues),
        variant_records=pairing_records_by_variant(facts),
    )


def verify_candidate_snapshot(snapshot: RawTournamentSnapshot, overrides: FamilyOverrideSet) -> SnapshotVerification:
    result = reconcile_tournament(normalize_snapshot(snapshot, overrides))
    return SnapshotVerification(
        blocking_issue_codes=tuple(issue.code for issue in result.issues if issue.blocks_publication)
    )
```

- [ ] **Step 4: Write failing module-state matrix tests**

```python
@pytest.mark.parametrize(
    (issue_code, module_id, expected_state),
    [
        ("phase_boundary_unresolved", "matchups_day2", ReportState.BLOCKED),
        ("matchup_sample_below_30", "matchups_overall", ReportState.DEGRADED),
        ("decklist_coverage_below_60", "deck_composition", ReportState.DEGRADED),
        ("variant_record_mismatch", "performance", ReportState.BLOCKED),
    ],
)
def test_module_state_policy(issue_code, module_id, expected_state):
    status = module_status(module_id, reconciliation_with(issue_code), sample_size=12, valid_lists=8, coverage=0.50)
    assert status.state is expected_state
    assert status.exportable is (expected_state is ReportState.READY)
```

- [ ] **Step 5: Implement ready/degraded/blocked publication policy**

Use stable reason codes including `matchup_sample_below_30`, `no_matches`, `decklist_count_below_10`, `decklist_coverage_below_60`, `phase_boundary_unresolved`, `missing_pairing_round`, `variant_record_mismatch`, `matchup_reference_mismatch`, and `source_schema_incompatible`. Set `exportable=True` only when state is `ready`; disclose reconciled unknown/procedural counts without degrading solely because they are non-zero.

```python
def status_for(state: ReportState, reason_code: str | None = None, message: str | None = None) -> ModuleStatus:
    return ModuleStatus(
        state=state,
        reason_code=reason_code,
        message=message,
        exportable=state is ReportState.READY,
    )
```

- [ ] **Step 6: Compose collection, verification, and promotion into refresh**

`VerifiedSnapshotRefresher.refresh` must call the adapter's `collect`, load the staged raw candidate, call `verify_candidate_snapshot`, and pass its `SnapshotVerification` to `SnapshotStore.promote`. A blocked result removes only the staged candidate and raises `SnapshotValidationError` with stable issue codes; a clean result promotes and returns the manifest. Add the CLI `--dataset-dir` path and make its normal mode invoke this final refresh path.

```python
def refresh(self, ref: TournamentRef, dataset_dir: Path) -> SnapshotManifest:
    staged = self.adapter.collect(ref, dataset_dir)
    verification = verify_candidate_snapshot(staged.raw, self.family_overrides)
    self.store.promote(dataset_dir, staged.path, staged.manifest, verification)
    return staged.manifest
```

- [ ] **Step 7: Run reconciliation and adapter tests to green**

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_reconciliation.py scripts/tools/test_limitless_tournament_snapshot.py -q`

Expected: PASS for all gates, variant-before-family comparison, unresolved phases, source mismatch, non-failing exclusions, module-local degradation, exportability, and last-good preservation when candidate verification blocks promotion.

- [ ] **Step 8: Commit quality gates and verified refresh**

```bash
git add app/tournament_reports/reconciliation.py tests/test_tournament_reconciliation.py scripts/tools/limitless_tournament_snapshot.py scripts/tools/test_limitless_tournament_snapshot.py
git commit -m "feat: reconcile tournament facts and gate modules"
```

---

### Task 6: Modular overview and archetype report builders

**Files:**
- Create: `app/tournament_reports/builders.py`
- Create: `tests/test_tournament_report_builders.py`

**Interfaces:**
- Consumes: `TournamentFacts`, `ReconciliationResult`, and all metric functions.
- Consumes: `ReportSelection(grain: ReportGrain, selection_id: str)` and response contracts from Task 1.
- Produces: `EventOverviewResponse(dataset_id: str, event: EventIdentity, snapshot_version: str, families: list[ReportSelectionOption], modules: list[ReportModule])`.
- Produces: `ArchetypeReportResponse(dataset_id: str, event: EventIdentity, selection: ReportSelection, variants: list[ReportSelectionOption], snapshot_version: str, modules: list[ReportModule])`.
- Produces: `build_event_overview(facts: TournamentFacts, reconciliation: ReconciliationResult, dataset_id: str) -> EventOverviewResponse`.
- Produces: `build_archetype_report(facts: TournamentFacts, reconciliation: ReconciliationResult, dataset_id: str, selection: ReportSelection) -> ArchetypeReportResponse`.

- [ ] **Step 1: Write failing overview module-order and payload tests**

```python
def test_overview_has_layered_distribution_then_conversion_then_ranking(facts, reconciliation):
    report = build_event_overview(facts, reconciliation, "2026-new-orleans-ma")

    assert [module.module_id for module in report.modules] == [
        "event_identity",
        "phase_topcut_distribution",
        "day2_conversion",
        "family_ranking",
    ]
    assert report.modules[1].data["first_phase"][0]["family_id"] == "dragapult-ex"
    assert report.modules[1].data["top_cut"][0]["family_id"] == "dragapult-ex"
```

- [ ] **Step 2: Run builder tests and observe the missing module failure**

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_report_builders.py -q`

Expected: FAIL importing `build_event_overview`.

- [ ] **Step 3: Implement the overview builder without metric arithmetic**

Call metric functions, attach numerator/denominator/sample fields, official record, metric notes, provenance, and state to each `ReportModule`. Sort families by First Phase players descending then family ID. Put Top 10 report eligibility in each selection option while retaining long-tail rows with `eligible=False` and reason `outside_top_10_families`.

```python
def build_event_overview(facts: TournamentFacts, reconciliation: ReconciliationResult, dataset_id: str) -> EventOverviewResponse:
    first_phase = distribution(facts, ReportGrain.FAMILY, ReportPhase.FIRST_PHASE)
    top_cut = distribution(facts, ReportGrain.FAMILY, ReportPhase.TOP_CUT)
    day2 = conversion(facts, ReportGrain.FAMILY)
    modules = build_overview_modules(facts, reconciliation, first_phase, top_cut, day2)
    return EventOverviewResponse(
        dataset_id=dataset_id,
        event=event_identity(facts),
        snapshot_version=facts.provenance.snapshot_version,
        families=family_options(first_phase.rows, limit=10),
        modules=modules,
    )
```

- [ ] **Step 4: Write failing family/variant module-order and grain tests**

```python
def test_archetype_report_keeps_one_grain_across_every_module(facts, reconciliation):
    selection = ReportSelection(grain=ReportGrain.VARIANT, selection_id="dragapult-dusknoir")
    report = build_archetype_report(facts, reconciliation, "2026-new-orleans-ma", selection)

    assert [module.module_id for module in report.modules] == [
        "headline_performance",
        "phase_performance",
        "top_finishers",
        "matchups_overall",
        "matchups_day2",
        "deck_composition_first_phase",
        "deck_composition_day2",
        "deck_composition_top_cut",
        "representative_lists",
    ]
    assert {module.grain for module in report.modules} == {ReportGrain.VARIANT}
    assert {module.selection_id for module in report.modules} == {"dragapult-dusknoir"}
```

- [ ] **Step 5: Implement family/variant eligibility and module assembly**

Default family reports to combined family facts. Return every member variant in `variants`; mark only variants with at least 10 First Phase players as `eligible=True` and selectable full-report variants, and retain smaller variants with counts plus reason `variant_players_below_10`. Build Overall and Day 2 matchup modules, three independent composition phase modules, top finishers, and up to three representative lists. Return a structured not-eligible error for direct long-tail family reports and variant report requests below 10 while preserving their counts for the UI message.

```python
MODULE_BUILDERS = (
    build_headline_performance,
    build_phase_performance,
    build_top_finishers,
    build_matchups_overall,
    build_matchups_day2,
    build_composition_first_phase,
    build_composition_day2,
    build_composition_top_cut,
    build_representative_lists,
)

modules = [builder(facts, reconciliation, selection) for builder in MODULE_BUILDERS]
```

- [ ] **Step 6: Assert every module is self-describing**

Add a parameterized test that verifies every ready/degraded/blocked module includes event-linked provenance, snapshot version, phase, current grain/selection when applicable, sample size, metric notes, non-empty reason for non-ready states, and `status.exportable == (status.state == ready)`.

```python
@pytest.mark.parametrize("report_factory", [build_ready_report, build_degraded_report, build_blocked_report])
def test_every_module_is_self_describing(report_factory, facts, reconciliation):
    report = report_factory(facts, reconciliation)
    for module in report.modules:
        assert module.provenance.snapshot_version
        assert module.phase
        assert module.sample_size >= 0
        assert module.metric_notes
        assert module.status.exportable is (module.status.state is ReportState.READY)
        if module.status.state is not ReportState.READY:
            assert module.status.reason_code and module.status.message
```

- [ ] **Step 7: Run builders and upstream unit suites**

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_report_builders.py tests/test_tournament_metrics.py tests/test_tournament_reconciliation.py -q`

Expected: PASS with exact module ordering, family default, qualifying variants, long-tail status, phase modules, and self-describing payloads.

- [ ] **Step 8: Commit report builders**

```bash
git add app/tournament_reports/builders.py tests/test_tournament_report_builders.py
git commit -m "feat: build modular tournament reports"
```

---

### Task 7: File-backed report service and FastAPI resources

**Files:**
- Create: `app/services/tournament_report_service.py`
- Create: `app/api/tournament_reports.py`
- Create: `tests/test_tournament_report_service.py`
- Create: `tests/test_tournament_report_api.py`
- Modify: `app/main.py`

**Interfaces:**
- Consumes: `DatasetRegistryService`, `DatasetStateStore`, `SnapshotStore`, fact normalization, reconciliation, and builders.
- Produces: `TournamentReportService(dataset_registry: DatasetRegistryService, dataset_state_store: DatasetStateStore, snapshot_store: SnapshotStore, family_overrides_path: Path)`.
- Produces: `TournamentReportNotFound`, `TournamentReportNotEligible`, and `TournamentSnapshotUnavailable` service exceptions.
- Produces: `TournamentReportService.list_reports(mounted_dataset_ids: list[str]) -> TournamentReportIndexResponse`.
- Produces: `TournamentReportService.get_overview(dataset_id: str) -> EventOverviewResponse`.
- Produces: `TournamentReportService.get_archetype_report(dataset_id: str, selection: ReportSelection) -> ArchetypeReportResponse`.
- Produces endpoints:
  - `GET /api/v1/tournament-reports`
  - `GET /api/v1/tournament-reports/{dataset_id}`
  - `GET /api/v1/tournament-reports/{dataset_id}/families/{family_id}`
  - `GET /api/v1/tournament-reports/{dataset_id}/variants/{variant_id}`

- [ ] **Step 1: Write failing service cache and mounted-index tests**

```python
def test_index_contains_only_mounted_completed_events(report_service):
    response = report_service.list_reports(["completed", "unfinished", "unmounted"])
    assert [item.dataset_id for item in response.events] == ["completed"]


def test_fact_cache_is_keyed_by_dataset_and_snapshot_version(report_service, normalizer_spy):
    report_service.get_overview("completed")
    report_service.get_overview("completed")
    assert normalizer_spy.call_count == 1
```

- [ ] **Step 2: Run service tests and observe the missing service failure**

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_report_service.py -q`

Expected: FAIL importing `TournamentReportService`.

- [ ] **Step 3: Implement offline service loading and versioned in-memory caching**

Resolve `DatasetRecord.dataset_dir`, require a verified local snapshot, normalize with `data/config/archetype_family_overrides.json`, reconcile once, and cache `(facts, reconciliation)` by `(dataset_id, snapshot_version, override_version)`. Do not perform HTTP requests. The index receives the reconciled mounted IDs from the existing state store and filters incomplete events.

```python
def _load(self, dataset_id: str) -> tuple[TournamentFacts, ReconciliationResult]:
    record = self._require_dataset(dataset_id)
    snapshot = self.snapshot_store.load(Path(record.dataset_dir))
    overrides = load_family_overrides(self.family_overrides_path)
    key = (dataset_id, snapshot.manifest.snapshot_version, overrides.version)
    if key not in self._cache:
        facts = normalize_snapshot(snapshot, overrides)
        self._cache[key] = (facts, reconcile_tournament(facts))
    return self._cache[key]
```

- [ ] **Step 4: Write failing API contract tests**

```python
def test_family_and_variant_routes_preserve_grain(client):
    family = client.get("/api/v1/tournament-reports/2026-new-orleans-ma/families/dragapult-ex")
    variant = client.get("/api/v1/tournament-reports/2026-new-orleans-ma/variants/dragapult-dusknoir")

    assert family.status_code == 200
    assert family.json()["selection"] == {"grain": "family", "selection_id": "dragapult-ex"}
    assert variant.status_code == 200
    assert variant.json()["selection"] == {"grain": "variant", "selection_id": "dragapult-dusknoir"}
```

- [ ] **Step 5: Implement thin report router and exception mapping**

Map unknown dataset/selection to 404, non-mounted or unfinished reports to 409, missing verified snapshot to 503, and ineligible long-tail selections to 422 with `{detail, reason_code, sample_size}`. Keep module-level degraded/blocked states inside successful 200 responses.

Compose `TournamentReportService` in `create_app`, pass the existing registry/state store, and include the new router without changing existing analysis/deck/provider route behavior.

```python
@router.get("/{dataset_id}/families/{family_id}", response_model=ArchetypeReportResponse)
def get_family_report(dataset_id: str, family_id: str) -> ArchetypeReportResponse:
    return translate_report_errors(
        lambda: service.get_archetype_report(
            dataset_id,
            ReportSelection(grain=ReportGrain.FAMILY, selection_id=family_id),
        )
    )
```

- [ ] **Step 6: Run report and regression API tests**

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_report_service.py tests/test_tournament_report_api.py tests/test_dataset_api.py tests/test_deck_api.py tests/test_provider_api.py -q`

Expected: PASS for index/overview/family/variant contracts, mounted/completed filtering, 404/409/422/503 mappings, cache invalidation by version, and existing APIs.

- [ ] **Step 7: Commit service and API**

```bash
git add app/services/tournament_report_service.py app/api/tournament_reports.py app/main.py tests/test_tournament_report_service.py tests/test_tournament_report_api.py
git commit -m "feat: expose modular tournament report API"
```

---

### Task 8: Pure frontend report navigation, selection, and chart models

**Files:**
- Create: `app/static/tournament-reports-core.mjs`
- Create: `tests/frontend/tournament-reports-core.test.mjs`

**Interfaces:**
- Produces: `createReportRoute(view: "index" | "overview" | "family" | "variant", datasetId: string | null, grain?: "family" | "variant" | null, selectionId?: string | null) -> string`.
- Produces: `reduceReportSelection(state: ReportUiState, action: ReportUiAction) -> ReportUiState`.
- Produces: `buildOverviewChartModel(module: ReportModule, selectedFamilyId: string | null) -> OverviewChartModel`.
- Produces: `moduleAvailability(module: ReportModule) -> {kind: string, message: string, canExport: boolean}`.
- Produces: `formatObservedWinRate(value: number | null) -> string`.
- Produces JSDoc types `ReportUiState`, `ReportUiAction`, and `OverviewChartModel` in the same module.

- [ ] **Step 1: Write failing navigation and synchronized-selection tests**

```javascript
test('selecting a family synchronizes overview highlights without filtering rows', () => {
  const next = reduceReportSelection(INITIAL_STATE, {type: 'select-family', familyId: 'dragapult-ex'});

  assert.equal(next.selectedFamilyId, 'dragapult-ex');
  assert.equal(next.visibleFamilyIds.length, INITIAL_STATE.visibleFamilyIds.length);
  assert.equal(next.familyReportAction, '/tournament-reports/2026-new-orleans-ma/families/dragapult-ex');
});


test('grain change clears stale module phases and carries event context', () => {
  const next = reduceReportSelection(FAMILY_STATE, {type: 'select-variant', variantId: 'dragapult-dusknoir'});
  assert.deepEqual(next.selection, {grain: 'variant', selectionId: 'dragapult-dusknoir'});
  assert.deepEqual(next.modulePhases, {matchups: 'overall', composition: 'first_phase'});
});
```

- [ ] **Step 2: Run the Node test and observe the missing module failure**

Run: `node --test tests/frontend/tournament-reports-core.test.mjs`

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `tournament-reports-core.mjs`.

- [ ] **Step 3: Implement deterministic route and reducer functions**

Use encoded path segments and these route shapes:

```javascript
createReportRoute('index', null) === '/tournament-reports'
createReportRoute('overview', '2026-new-orleans-ma') === '/tournament-reports/2026-new-orleans-ma'
createReportRoute('family', '2026-new-orleans-ma', 'family', 'dragapult-ex') === '/tournament-reports/2026-new-orleans-ma/families/dragapult-ex'
createReportRoute('variant', '2026-new-orleans-ma', 'variant', 'dragapult-dusknoir') === '/tournament-reports/2026-new-orleans-ma/variants/dragapult-dusknoir'
```

The reducer owns selected family, report selection, matchup phase, composition phase, request generation, and last applied generation. A response may update state only when its generation equals the latest request generation.

```javascript
case 'request-report':
  return {...state, requestGeneration: state.requestGeneration + 1};
case 'receive-report':
  return action.generation === state.requestGeneration
    ? {...state, report: action.report, appliedGeneration: action.generation}
    : state;
```

- [ ] **Step 4: Implement chart and state view models without metric recomputation**

Convert server-provided rows to SVG layout coordinates, labels, colors, tooltip text, and `selected` flags. Do not calculate share, win rate, conversion, or sample thresholds. Map `ready/degraded/blocked` directly to view state and expose export only when both `status.exportable` and `state === "ready"` are true.

```javascript
export function moduleAvailability(module) {
  return {
    kind: module.status.state,
    message: module.status.message || '',
    canExport: module.status.state === 'ready' && module.status.exportable === true,
  };
}
```

- [ ] **Step 5: Run pure frontend tests to green**

Run: `node --test tests/frontend/tournament-reports-core.test.mjs`

Expected: PASS for URL encoding, breadcrumb routes, synchronized highlighting, explicit report action, grain reset, phase isolation, stale-response rejection, tooltip fields, and module availability.

- [ ] **Step 6: Commit frontend core**

```bash
git add app/static/tournament-reports-core.mjs tests/frontend/tournament-reports-core.test.mjs
git commit -m "feat: add tournament report UI state model"
```

---

### Task 9: Tournament report shell and overview interaction

**Files:**
- Create: `app/static/tournament-reports.js`
- Modify: `app/main.py`
- Modify: `app/static/app.js`
- Modify: `app/static/index.html`
- Modify: `app/static/styles.css`
- Modify: `tests/test_static_app.py`
- Modify: `tests/frontend/tournament-reports-core.test.mjs`

**Interfaces:**
- Consumes: report index/overview APIs and Task 8 helpers.
- Produces: `createTournamentReportsController({requestJson, root, navigate})` with `initialize()`, `showIndex()`, `showOverview(datasetId)`, and `dispose()`.
- Produces: a fourth accessible top tab labeled `Tournament Reports`.
- Produces: event list → overview navigation and overview family selection → explicit family-report action.

- [ ] **Step 1: Write failing static shell tests**

```python
def test_root_has_tournament_reports_tab_and_module_script(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/")
    parser = AppShellParser()
    parser.feed(response.text)

    assert parser.tab_text == ["Analysis", "Deck Library", "AI Backend", "Tournament Reports"]
    assert parser.tab_panels == ["analysis-panel", "deck-library-panel", "ai-backend-panel", "tournament-reports-panel"]
    assert "./tournament-reports.js" in client.get("/static/app.js").text
    assert client.get("/tournament-reports/2026-new-orleans-ma/families/dragapult-ex").status_code == 200
```

- [ ] **Step 2: Run static tests and observe the missing fourth tab failure**

Run: `PYTHONPATH=. python3 -m pytest tests/test_static_app.py -q`

Expected: FAIL because the shell currently exposes only three tabs.

- [ ] **Step 3: Add the report shell and controller lifecycle**

Add a report panel containing breadcrumbs, report heading/status, index container, overview container, archetype container, and an ARIA-live notification region. Instantiate the controller in `app.js`; initialize it only when the reports tab is first activated. Use `history.pushState` for report routes and restore the matching view on `popstate` without a full reload.

Add explicit `GET /tournament-reports` and `GET /tournament-reports/{report_path:path}` shell routes in `app/main.py` so direct links and browser refresh return `index.html`; define them without intercepting `/api` or `/static`.

```python
@app.get("/tournament-reports", include_in_schema=False)
@app.get("/tournament-reports/{report_path:path}", include_in_schema=False)
def tournament_report_shell(report_path: str = ""):
    return FileResponse(str(static_dir / "index.html"))
```

```javascript
const tournamentReports = createTournamentReportsController({
  requestJson,
  root: element('tournament-reports-panel'),
  navigate: (path) => history.pushState({path}, '', path),
});

window.addEventListener('popstate', () => tournamentReports.showLocation(window.location.pathname));
```

- [ ] **Step 4: Render the event index and ordered overview modules**

Render completed mounted events from `GET /api/v1/tournament-reports`. For an overview render event identity, First Phase versus Top Cut distribution, separate First Phase → Day 2 conversion, and family ranking in the response order. Render charts as accessible inline SVG plus a compact data table so values do not depend on color alone.

```javascript
const OVERVIEW_RENDERERS = {
  event_identity: renderEventIdentity,
  phase_topcut_distribution: renderDistributionComparison,
  day2_conversion: renderConversion,
  family_ranking: renderFamilyRanking,
};

report.modules.forEach((module) => overview.append(OVERVIEW_RENDERERS[module.module_id](module)));
```

- [ ] **Step 5: Wire hover, click, and explicit drill-down**

On hover/focus, show server-provided players, share, and official record. On click/Enter, dispatch one `select-family` action and update selected styling in First Phase, Top Cut, and Conversion without removing rows. Reveal `View family report` only after selection; activate it to request the family API and preserve the dataset breadcrumb.

```javascript
function selectOverviewFamily(familyId) {
  state = reduceReportSelection(state, {type: 'select-family', familyId});
  root.querySelectorAll('[data-family-id]').forEach((node) => {
    node.classList.toggle('selected', node.dataset.familyId === familyId);
  });
  renderFamilyReportAction(state.familyReportAction);
}
```

- [ ] **Step 6: Add responsive and state styling**

Add `.tournament-report-*` rules for wide paired charts, stacked mobile layout, visible keyboard focus, selected-family emphasis, tooltip positioning, data tables, breadcrumb overflow, and `ready/degraded/blocked` panels. Keep existing Analysis, Deck Library, and AI Backend selectors unchanged.

```css
.tournament-report-comparison { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.tournament-report-mark.selected { stroke: var(--blue-dark); stroke-width: 4; }
.tournament-report-state[data-state="degraded"] { border-color: #f59e0b; }
.tournament-report-state[data-state="blocked"] { border-color: var(--red); }
@media (max-width: 720px) { .tournament-report-comparison { grid-template-columns: 1fr; } }
```

- [ ] **Step 7: Run static and pure interaction tests**

Run: `PYTHONPATH=. python3 -m pytest tests/test_static_app.py -q && node --test tests/frontend/tournament-reports-core.test.mjs tests/frontend/core.test.mjs`

Expected: PASS for four accessible tabs, split assets, event/overview structure, keyboard selection model, route restoration, and all existing frontend helpers.

- [ ] **Step 8: Commit overview UI**

```bash
git add app/main.py app/static/tournament-reports.js app/static/app.js app/static/index.html app/static/styles.css tests/test_static_app.py tests/frontend/tournament-reports-core.test.mjs
git commit -m "feat: add interactive tournament overview"
```

---

### Task 10: Family and variant report UI with phase controls

**Files:**
- Modify: `app/static/tournament-reports.js`
- Modify: `app/static/tournament-reports-core.mjs`
- Modify: `app/static/styles.css`
- Modify: `tests/frontend/tournament-reports-core.test.mjs`
- Create: `tests/test_tournament_report_ui_contract.py`

**Interfaces:**
- Consumes: family/variant API responses and their ordered `ReportModule` arrays.
- Produces: family report default, qualifying variant selector, headline/phase/finishers/matchups/composition/representative-list sections.
- Produces: matchup phase values `overall|day2` and composition phase values `first_phase|day2|top_cut`.

- [ ] **Step 1: Write failing module-order, grain, and phase-control contract tests**

```javascript
test('phase actions update only their owning module', () => {
  const matchup = reduceReportSelection(FAMILY_STATE, {type: 'set-matchup-phase', phase: 'day2'});
  assert.equal(matchup.modulePhases.matchups, 'day2');
  assert.equal(matchup.modulePhases.composition, 'first_phase');

  const composition = reduceReportSelection(matchup, {type: 'set-composition-phase', phase: 'top_cut'});
  assert.equal(composition.modulePhases.matchups, 'day2');
  assert.equal(composition.modulePhases.composition, 'top_cut');
});
```

Add Python API/UI contract assertions that every family and variant response supplies the exact module IDs the DOM renderer recognizes and that each selectable variant has `first_phase_players >= 10`.

- [ ] **Step 2: Run focused tests and observe missing renderer contracts**

Run: `node --test tests/frontend/tournament-reports-core.test.mjs && PYTHONPATH=. python3 -m pytest tests/test_tournament_report_ui_contract.py -q`

Expected: FAIL for missing family/variant module mappings and phase actions.

- [ ] **Step 3: Render the report in the approved module sequence**

Render headline performance, phase performance, top finishers, limited matchup, deck composition, and representative lists. Every section must show event, current family/variant, phase, sample size, metric notes, source update/fetch time, and its module state. Use observed win-rate wording and disclose unknown/procedural exclusions beside matchups.

```javascript
const ARCHETYPE_RENDERERS = {
  headline_performance: renderHeadlinePerformance,
  phase_performance: renderPhasePerformance,
  top_finishers: renderTopFinishers,
  matchups_overall: renderMatchups,
  matchups_day2: renderMatchups,
  deck_composition_first_phase: renderDeckComposition,
  deck_composition_day2: renderDeckComposition,
  deck_composition_top_cut: renderDeckComposition,
  representative_lists: renderRepresentativeLists,
};
```

- [ ] **Step 4: Implement one-grain variant switching with stale-response protection**

Populate the variant selector only from API eligibility options. On selection, increment request generation, fetch the variant route, and replace all modules together only if the response generation is current. Reset matchup to Overall and composition to First Phase so no family-grain or prior-phase values remain visible.

```javascript
async function selectVariant(variantId) {
  state = reduceReportSelection(state, {type: 'select-variant', variantId});
  const generation = ++state.requestGeneration;
  const report = await requestJson(`/api/v1/tournament-reports/${encodeURIComponent(state.datasetId)}/variants/${encodeURIComponent(variantId)}`);
  state = reduceReportSelection(state, {type: 'receive-report', generation, report});
  renderArchetypeReport(state.report);
}
```

- [ ] **Step 5: Implement independent phase controls and insufficient-data views**

Matchup buttons select only `matchups_overall` or `matchups_day2`. Composition buttons select only `deck_composition_first_phase`, `deck_composition_day2`, or `deck_composition_top_cut`. For degraded composition show valid-list count and coverage but no Core/Common/Tech buckets; for sub-30 matchups render `Insufficient sample (n=${sampleSize})`; for zero show `No matches`.

```javascript
function moduleForPhase(report, owner, phase) {
  const id = owner === 'matchups' ? `matchups_${phase}` : `deck_composition_${phase}`;
  return report.modules.find((module) => module.module_id === id);
}
```

- [ ] **Step 6: Render composition and representative lists exactly from payloads**

Show appearance rate and average copies when present for Core, Common, Tech, and Rare/Other rows. Preserve set and collector number in representative lists, and render at most the three server-selected lists in returned order.

```javascript
function renderCompositionRow(row) {
  return textRow([
    row.card_name,
    `${formatPercent(row.appearance_rate)} appearance`,
    `${formatNumber(row.average_when_present)} copies when present`,
  ]);
}
```

- [ ] **Step 7: Run report UI and regression suites**

Run: `node --test tests/frontend/*.test.mjs && PYTHONPATH=. python3 -m pytest tests/test_tournament_report_ui_contract.py tests/test_static_app.py -q`

Expected: PASS for module order, one-grain refresh, phase isolation, insufficient messages, exclusion disclosure, card fields, representative order, and existing UI behavior.

- [ ] **Step 8: Commit archetype report UI**

```bash
git add app/static/tournament-reports.js app/static/tournament-reports-core.mjs app/static/styles.css tests/frontend/tournament-reports-core.test.mjs tests/test_tournament_report_ui_contract.py
git commit -m "feat: add family and variant tournament reports"
```

---

### Task 11: Publication-safe 1080×1350 module PNG export

**Files:**
- Modify: `app/static/tournament-reports-core.mjs`
- Modify: `app/static/tournament-reports.js`
- Modify: `app/static/styles.css`
- Create: `tests/frontend/tournament-report-png.test.mjs`
- Create: `tests/test_tournament_report_export_contract.py`

**Interfaces:**
- Produces: `buildModuleSvg(module: ReportModule, context: ExportContext) -> string`.
- Produces: `assertExportable(module: ReportModule, context: ExportContext) -> void`.
- Produces: `exportModulePng(moduleElement: HTMLElement, module: ReportModule, context: ExportContext) -> Promise<void>`.
- `ExportContext` contains `eventName`, `eventDate`, `selectionLabel`, `phaseLabel`, `snapshotVersion`, `sourceProvider`, `sourceUpdatedAt`, `fetchedAt`, and `projectAttribution`.
- Output is a browser-generated `image/png` Blob with canvas dimensions exactly `1080` by `1350`.

- [ ] **Step 1: Write failing deterministic SVG-document tests**

```javascript
test('export document contains required publication context', () => {
  const svg = buildModuleSvg(READY_MATCHUP_MODULE, EXPORT_CONTEXT);

  assert.match(svg, /width="1080" height="1350"/);
  assert.match(svg, /International Championship New Orleans/);
  assert.match(svg, /Dragapult/);
  assert.match(svg, /Observed win rate/);
  assert.match(svg, /n=705/);
  assert.match(svg, /Limitless Labs/);
  assert.match(svg, /PTCG Deck Analysis/);
});
```

- [ ] **Step 2: Run PNG tests and observe the missing export functions**

Run: `node --test tests/frontend/tournament-report-png.test.mjs`

Expected: FAIL importing `buildModuleSvg`.

- [ ] **Step 3: Build a fixed-layout SVG from the displayed module payload**

Use a 1080×1350 `viewBox`, embedded system-font stack, fixed safe margins, escaped text, explicit wrapping limits, chart/table area, sample and semantics footer, provenance line, and project attribution. Select module-specific body renderers by exact `module_id`; consume only server values and the currently displayed phase/grain context.

```javascript
export function buildModuleSvg(module, context) {
  const body = EXPORT_BODY_RENDERERS[module.module_id](module);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1350" viewBox="0 0 1080 1350">
    ${renderExportHeader(module, context)}
    ${body}
    ${renderExportFooter(module, context)}
  </svg>`;
}
```

- [ ] **Step 4: Convert SVG to PNG and reject stale or non-ready exports**

Serialize the SVG to a Blob, load it into an `Image`, draw to a canvas whose `width=1080` and `height=1350`, and call `canvas.toBlob(..., "image/png")`. Before rendering, require `module.status.state === "ready"`, `module.status.exportable === true`, and `module.provenance.snapshot_version === context.snapshotVersion`; show a non-destructive error if any check fails.

```javascript
export async function exportModulePng(moduleElement, module, context) {
  assertExportable(module, context);
  const canvas = document.createElement('canvas');
  canvas.width = 1080;
  canvas.height = 1350;
  const image = await loadSvgImage(buildModuleSvg(module, context));
  canvas.getContext('2d').drawImage(image, 0, 0, 1080, 1350);
  const blob = await canvasBlob(canvas, 'image/png');
  downloadBlob(blob, exportFilename(module, context));
}
```

- [ ] **Step 5: Add per-module export actions and filename contract**

Render `Export PNG` only on ready visualization modules. Build the lowercased ASCII-safe filename with `` `${datasetId}-${moduleId}-${grainOrEvent}-${selectionOrOverview}-${phase}.png` ``. Do not export navigation, adjacent modules, degraded messages, or blocked messages.

```javascript
if (moduleAvailability(module).canExport) {
  actions.append(button('Export PNG', () => exportModulePng(section, module, exportContext(report, module))));
}
```

- [ ] **Step 6: Add server/client export contract tests**

Assert every ready visualization API module contains title, sample size, notes, source provider, source timestamps, and snapshot version; assert every non-ready module has `exportable=false`. Add Node tests for 1080×1350 dimensions, XML escaping, long-title wrapping, required footer fields, stale-version rejection, and disabled exports.

```python
def test_ready_modules_have_complete_export_context(report_response):
    for module in report_response.modules:
        if module.status.state is ReportState.READY:
            assert module.title and module.metric_notes
            assert module.sample_size >= 0
            assert module.provenance.source_provider == "Limitless Labs"
            assert module.provenance.fetched_at and module.provenance.snapshot_version
        else:
            assert module.status.exportable is False
```

```javascript
test('stale snapshot versions cannot export', () => {
  assert.throws(
    () => assertExportable(READY_MATCHUP_MODULE, {...EXPORT_CONTEXT, snapshotVersion: 'stale'}),
    /snapshot version/i,
  );
});
```

- [ ] **Step 7: Run export and report suites**

Run: `node --test tests/frontend/tournament-report-png.test.mjs tests/frontend/tournament-reports-core.test.mjs && PYTHONPATH=. python3 -m pytest tests/test_tournament_report_export_contract.py tests/test_tournament_report_api.py -q`

Expected: PASS for fixed dimensions, complete self-contained content, matching payload/version, safe text layout, and publication blocking.

- [ ] **Step 8: Commit PNG export**

```bash
git add app/static/tournament-reports-core.mjs app/static/tournament-reports.js app/static/styles.css tests/frontend/tournament-report-png.test.mjs tests/test_tournament_report_export_contract.py
git commit -m "feat: export tournament modules as portrait PNG"
```

---

### Task 12: New Orleans 0070 golden reconciliation fixture

**Files:**
- Create: `data/2026/New_Orleans/MA/cache/snapshots/`
- Create: `data/2026/New_Orleans/MA/cache/verified-snapshot.json`
- Create: `tests/fixtures/tournament_reports/0070-golden/expected.json`
- Create: `tests/test_tournament_report_0070_golden.py`
- Modify: `scripts/tools/limitless_tournament_snapshot.py`
- Modify: `scripts/tools/test_limitless_tournament_snapshot.py`

**Interfaces:**
- Consumes: the complete adapter, fact, reconciliation, and report pipeline from Tasks 1–11.
- Produces: the verified `data/2026/New_Orleans/MA` snapshot; its concrete child directory is named by the adapter as `0070-ma-{content_hash_12}` from the canonical manifest resource index.
- Produces: a deterministic golden assertion for tournament `0070`, division `MA`, variant `dragapult-ex`; the family with the same ID is asserted separately as the sum of its reconciled variants.
- The expected fixture contains immutable scalars and round boundary only; raw source records remain in the verified production snapshot.

- [ ] **Step 1: Add the exact golden expectation file and failing test**

```json
{
  "dataset_id": "2026-new-orleans-ma",
  "tournament_id": "0070",
  "division": "MA",
  "selection": {"grain": "variant", "selection_id": "dragapult-ex"},
  "phase_boundary": 8,
  "overall": {"wins": 3278, "losses": 2466, "ties": 1021, "win_rate": 0.5349},
  "day1": {"wins": 2611, "losses": 1873, "ties": 849, "win_rate": 0.5427},
  "day2": {"wins": 667, "losses": 593, "ties": 172, "win_rate": 0.5058},
  "conversion": {"first_phase_players": 749, "day2_players": 240, "rate": 0.3204}
}
```

The listed values apply only to the `dragapult-ex` variant. The test must also assert exact local/source opponent, unknown, and procedural W/L/T reconciliation for every variant whose family ID is `dragapult-ex`, then assert the family record equals the sum of those already-reconciled variant records.

- [ ] **Step 2: Run the golden test before installing the new snapshot**

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_report_0070_golden.py -q`

Expected: FAIL with `TournamentSnapshotUnavailable` because the current 0070 cache has no verified snapshot pointer or pairings.

- [ ] **Step 3: Add a deterministic verification-only CLI mode**

Add `--verify-only` to `limitless_tournament_snapshot.py`. It must load the current verified snapshot, normalize/reconcile it, print JSON containing snapshot version, phase boundary, issue codes, and eligible family/variant counts, perform no HTTP calls, and exit `0` only when no blocking issue exists.

```python
def verify_only(dataset_dir: Path, overrides_path: Path) -> int:
    snapshot = SnapshotStore().load(dataset_dir)
    facts = normalize_snapshot(snapshot, load_family_overrides(overrides_path))
    result = reconcile_tournament(facts)
    print(json.dumps(verification_summary(snapshot, facts, result), sort_keys=True))
    return 1 if any(issue.blocks_publication for issue in result.issues) else 0
```

- [ ] **Step 4: Test the verification command with an injected offline client**

Run: `PYTHONPATH=. python3 -m pytest scripts/tools/test_limitless_tournament_snapshot.py -q`

Expected: PASS and prove `--verify-only` never invokes `LimitlessClient.fetch`.

- [ ] **Step 5: Fetch and promote the complete 0070 snapshot**

Run: `PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0070 --division MA --dataset-dir data/2026/New_Orleans/MA`

Expected: exit `0`, a new immutable snapshot under `cache/snapshots/` whose name begins `0070-ma-`, an atomically updated `verified-snapshot.json`, and zero blocking reconciliation issues. The adapter prints the concrete full promoted path.

- [ ] **Step 6: Run the 0070 offline verifier and golden test to green**

Run: `PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0070 --division MA --dataset-dir data/2026/New_Orleans/MA --verify-only`

Expected: exit `0` without an HTTP call, with phase boundary `8` and no blocking issue codes.

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_report_0070_golden.py -q`

Expected: PASS with boundary 8, every expected Dragapult scalar, and exact opponent/unknown/procedural reconciliation.

- [ ] **Step 7: Commit the 0070 snapshot, golden oracle, and offline verifier**

```bash
git add data/2026/New_Orleans/MA/cache/snapshots data/2026/New_Orleans/MA/cache/verified-snapshot.json tests/fixtures/tournament_reports/0070-golden/expected.json tests/test_tournament_report_0070_golden.py scripts/tools/limitless_tournament_snapshot.py scripts/tools/test_limitless_tournament_snapshot.py
git commit -m "test: add New Orleans tournament golden oracle"
```

---

### Task 13: Materialize all mounted completed snapshots and enforce dataset breadth

**Files:**
- Create: `data/2026/Campinas/MA/cache/snapshots/`
- Create: `data/2026/Campinas/MA/cache/verified-snapshot.json`
- Create: `data/2026/Indianapolis/MA/cache/snapshots/`
- Create: `data/2026/Indianapolis/MA/cache/verified-snapshot.json`
- Create: `data/2026/Lima/MA/cache/snapshots/`
- Create: `data/2026/Lima/MA/cache/verified-snapshot.json`
- Create: `data/2026/Los_Angeles/MA/cache/snapshots/`
- Create: `data/2026/Los_Angeles/MA/cache/verified-snapshot.json`
- Create: `data/2026/Melbourne/MA/cache/snapshots/`
- Create: `data/2026/Melbourne/MA/cache/verified-snapshot.json`
- Create: `data/2026/Prague/MA/cache/snapshots/`
- Create: `data/2026/Prague/MA/cache/verified-snapshot.json`
- Create: `data/2026/Turin/MA/cache/snapshots/`
- Create: `data/2026/Turin/MA/cache/verified-snapshot.json`
- Create: `data/2026/Utrecht/MA/cache/snapshots/`
- Create: `data/2026/Utrecht/MA/cache/verified-snapshot.json`
- Create: `tests/test_tournament_report_dataset_coverage.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: all ingestion, fact, reconciliation, builder, service, API, UI, and export behavior from Tasks 1–12.
- Consumes: the verified New Orleans 0070 snapshot from Task 12.
- Produces: verified offline report coverage for all nine IDs in `data/config/dataset_state.json` by adding the remaining eight snapshots.
- Produces: Top 10 family report coverage and every qualifying variant report shell for each mounted completed event.

- [ ] **Step 1: Write the failing mounted-dataset breadth test**

```python
def production_report_service(data_root: Path) -> TournamentReportService:
    registry = DatasetRegistryService(data_root)
    return TournamentReportService(
        dataset_registry=registry,
        dataset_state_store=DatasetStateStore(data_root / "config/dataset_state.json"),
        snapshot_store=SnapshotStore(),
        family_overrides_path=data_root / "config/archetype_family_overrides.json",
    )


def test_every_mounted_completed_event_has_mvp_report_coverage():
    state = DatasetState(**json.loads(Path("data/config/dataset_state.json").read_text()))
    service = production_report_service(Path("data"))

    index = service.list_reports(state.mounted_dataset_ids)
    assert {event.dataset_id for event in index.events} == set(state.mounted_dataset_ids)

    for event in index.events:
        overview = service.get_overview(event.dataset_id)
        top_ten = [family for family in overview.families if family.eligible]
        assert len(top_ten) == min(10, len(overview.families))
        for family in top_ten:
            family_report = service.get_archetype_report(event.dataset_id, ReportSelection(ReportGrain.FAMILY, family.selection_id))
            assert all(module.status.state in set(ReportState) for module in family_report.modules)
            ineligible_variants = [variant for variant in family_report.variants if not variant.eligible]
            assert all(variant.reason_code == "variant_players_below_10" for variant in ineligible_variants)
            for variant in [row for row in family_report.variants if row.eligible]:
                variant_report = service.get_archetype_report(event.dataset_id, ReportSelection(ReportGrain.VARIANT, variant.selection_id))
                assert variant.first_phase_players >= 10
                assert all(module.status.state in set(ReportState) for module in variant_report.modules)
```

- [ ] **Step 2: Run coverage and golden tests before generation**

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_report_dataset_coverage.py tests/test_tournament_report_0070_golden.py -q`

Expected: FAIL for the eight events other than New Orleans because their flat caches do not contain verified snapshot pointers, per-round pairings, or matchup references; the 0070 golden assertion remains green.

- [ ] **Step 3: Refresh each mounted completed dataset through the adapter**

Run these exact commands from the repository root in the visible Orca shell:

```bash
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0062 --division MA --dataset-dir data/2026/Prague/MA
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0063 --division MA --dataset-dir data/2026/Los_Angeles/MA
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0064 --division MA --dataset-dir data/2026/Utrecht/MA
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0065 --division MA --dataset-dir data/2026/Campinas/MA
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0066 --division MA --dataset-dir data/2026/Melbourne/MA
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0067 --division MA --dataset-dir data/2026/Lima/MA
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0068 --division MA --dataset-dir data/2026/Indianapolis/MA
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0069 --division MA --dataset-dir data/2026/Turin/MA
```

Each command must print the promoted snapshot version and zero blocking issues. If an event cannot reconcile, preserve its prior verified pointer, commit no partial staging directory, and fix the adapter/normalizer with a focused failing fixture before rerunning that event.

- [ ] **Step 4: Verify every snapshot without network access**

Run these exact commands; all nine must exit `0`:

```bash
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0062 --division MA --dataset-dir data/2026/Prague/MA --verify-only
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0063 --division MA --dataset-dir data/2026/Los_Angeles/MA --verify-only
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0064 --division MA --dataset-dir data/2026/Utrecht/MA --verify-only
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0065 --division MA --dataset-dir data/2026/Campinas/MA --verify-only
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0066 --division MA --dataset-dir data/2026/Melbourne/MA --verify-only
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0067 --division MA --dataset-dir data/2026/Lima/MA --verify-only
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0068 --division MA --dataset-dir data/2026/Indianapolis/MA --verify-only
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0069 --division MA --dataset-dir data/2026/Turin/MA --verify-only
PYTHONPATH=. python3 scripts/tools/limitless_tournament_snapshot.py --tournament-id 0070 --division MA --dataset-dir data/2026/New_Orleans/MA --verify-only
```

Then monkeypatch `LimitlessClient.fetch` to raise in the coverage test and prove every report still builds from local files.

- [ ] **Step 5: Run golden, breadth, exceptional-state, and API tests**

Run: `PYTHONPATH=. python3 -m pytest tests/test_tournament_report_0070_golden.py tests/test_tournament_report_dataset_coverage.py tests/test_tournament_reconciliation.py tests/test_tournament_report_api.py -q`

Expected: PASS. The golden test reproduces 0070 Dragapult values; every mounted completed event has an overview; every Top 10 family and qualifying variant has all modules in a valid state; long-tail rows remain visible with explicit ineligibility.

- [ ] **Step 6: Document snapshot refresh, verification, API, and UI commands**

Update README dataset layout with `cache/snapshots` and `verified-snapshot.json`; document the refresh and `--verify-only` commands, four report API shapes, Tournament Reports navigation, 30-match/10-list/60%-coverage gates, one-third tie formula, and 1080×1350 export restriction.

- [ ] **Step 7: Run complete automated verification**

Run: `PYTHONPATH=. python3 -m pytest`

Expected: PASS with zero failures.

Run: `node --test tests/frontend/*.test.mjs`

Expected: PASS with zero failures.

Run: `git diff --check`

Expected: no output.

- [ ] **Step 8: Run local application and publication smoke checks**

Start: `PYTHONPATH=. uvicorn app.main:app --host 127.0.0.1 --port 8011`

Verify `GET /health`, the four report API shapes for `2026-new-orleans-ma`, family/variant navigation, synchronized overview highlight, each phase switch, degraded/blocked messages, and one ready module PNG. Save that export as `/tmp/2026-new-orleans-ma-matchups-overall-family-dragapult-ex-overall.png`, run `sips -g pixelWidth -g pixelHeight /tmp/2026-new-orleans-ma-matchups-overall-family-dragapult-ex-overall.png`, and require `1080` by `1350`; inspect title, chart, sample/semantics, source, and attribution for clipping. Stop the preview after the check and remove only that named `/tmp` PNG.

- [ ] **Step 9: Commit verified snapshots, breadth test, and documentation**

```bash
git add data/2026 data/config/archetype_family_overrides.json tests/test_tournament_report_dataset_coverage.py README.md
git commit -m "data: add verified tournament report snapshots"
```

---

## Final Review Gate

- [ ] Run `PYTHONPATH=. python3 -m pytest` and record the passing test count.
- [ ] Run `node --test tests/frontend/*.test.mjs` and record the passing test count.
- [ ] Run all nine `--verify-only` commands and confirm zero blocking reconciliation issues.
- [ ] Run `git diff --check` and confirm no whitespace errors.
- [ ] Run `git status --short` and confirm only intentional implementation commits exist.
- [ ] Review `git log --oneline` and confirm Tasks 1–13 each ended in its named focused commit.
- [ ] Confirm no staging directories, runtime secrets, downloaded PNGs, `.venv`, database files, or port-8010 process are included.
- [ ] Update the Orca worktree comment to `赛事数据可视化 implementation 待用户验收` only after all automated and manual checks pass.
