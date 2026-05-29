# FreeCAD Composites Drape Context

This context defines the domain language for drape computation in CompositeShell so rebuild decisions stay precise and comparable across implementations.

## Language

**Drape Contract**:
The stable public `CompositeShell` drape interface consumed by downstream tools.
_Avoid_: backend internals, solver API

**Fishnet Core**:
The internal constructive solver implementation that may change as long as the Drape Contract is preserved.
_Avoid_: public API

**Hard-Fail Production Policy**:
A fishnet gate failure produces explicit invalid output and blocks publication rather than silently degrading.
_Avoid_: auto-fallback, permissive degradation

**Legacy Comparison Mode**:
A user-selectable mode in UI/preferences that runs legacy behavior only when explicitly chosen, never automatically.
_Avoid_: automatic fallback

**Diagnostic Labeling Rule**:
Legacy Comparison Mode must display explicit non-production warnings and cannot be used to claim strict-gate production acceptance.
_Avoid_: equivalence between diagnostic and production validation

**Diagnostic Availability Rule**:
Legacy Comparison Mode is available during normal interactive work but all such runs remain excluded from production gate evidence.
_Avoid_: hidden mode restrictions or evidence commingling

**Legacy Diff Artifact Policy**:
Side-by-side fishnet vs legacy diff artifacts are optional by default, but become mandatory when fishnet fails a strict gate or materially diverges from the established baseline.
_Avoid_: assuming ad-hoc comparisons are gate evidence

**Material Divergence Definition**:
Material divergence means a strict-gate threshold crossing or a percentage delta beyond a fixed tolerance on key metrics versus the prior accepted baseline.
_Avoid_: subjective-only divergence decisions

**Material Delta Tolerance**:
The fixed percentage delta tolerance for material divergence is 5% on key metrics.
_Avoid_: implicit or shifting divergence thresholds

**Baseline Reference Rule**:
The comparison baseline is the latest committed G3/G4-passing revision on the active branch.
_Avoid_: uncommitted local-run baselines

**Canonical Gate Runner Rule**:
All gate evidence must be produced through a single canonical command or script entrypoint.
_Avoid_: ad-hoc equivalent command sets

**Gate Runner Location**:
The canonical runner is `freecad/Composites/scripts/run_fishnet_gates.py`.
_Avoid_: duplicated entrypoints across repo levels

**Stage-Scoped Runner Modes**:
The canonical gate runner supports explicit stage modes (`cs0`, `cs1`, `cs2`, `release`) with defined geometry/test scopes.
_Avoid_: always-full-matrix execution during early-stage gating

**Versioned Stage Scope Config**:
Stage mode scopes for the gate runner are loaded from a versioned configuration file.
_Avoid_: policy changes hidden in script logic

**Stage Scope Config Path**:
The stage-scope config file path is `freecad/Composites/compositestests/gate_profiles/fishnet_gate_stages.yaml`.
_Avoid_: dispersing stage policy across docs-only locations

**Stage Config Approval Rule**:
Any change to `fishnet_gate_stages.yaml` requires explicit user approval before merge.
_Avoid_: silent gate-scope drift

**Gate-Blocking Policy**:
A failed strict quality gate halts stage progression until the underlying cause is corrected.
_Avoid_: temporary waivers, proceed-with-known-failure

**Determinism Envelope**:
Repeated runs with identical inputs are accepted when geometric and metric outputs stay within fixed numeric tolerances.
_Avoid_: bitwise-identity requirement, ad-hoc tolerance changes

**Baseline-First Execution**:
Implementation starts from the current approved PRD/plan set without additional pre-implementation documentation rounds.
_Avoid_: open-ended planning loops

**Harness-First Slice**:
The first implementation stage is strict gate-harness enforcement before solver behavior changes.
_Avoid_: code-first changes without predeclared failing gates

**Root-Cause Triage Order**:
When multiple gates fail, remediation order is support adherence, then solver validity, then output topology/UV, then metrics semantics.
_Avoid_: easiest-test-first sequencing

**Atomic Stage Completion**:
A stage is complete only when implementation changes, tests, and gate-evidence artifacts are delivered together.
_Avoid_: merge-now-document-later

**No-Temporary-Shims Rule**:
No temporary compatibility shim is allowed in production fishnet code to keep short-term tests passing.
_Avoid_: TODO-based temporary patches

**Explicit Exception Authority**:
Only the user may approve exceptions to gate/process rules.
_Avoid_: autonomous orchestrator exceptions

**Primary Harness Anchor**:
`test_drape_backend_fishnet_gates.py` is the first-stage strict-gate anchor test module.
_Avoid_: scattering first-stage gate assertions across unrelated test files

**Incremental Matrix Ramp**:
The harness starts with a minimal deterministic fixture set (2–3 geometries) before expanding to the full required matrix.
_Avoid_: full-matrix-first rollout before harness stability

**CS0 Geometry Triad**:
The initial harness geometries are `ud_plate_basic`, `cylindrical_panel_segment`, and `flat_panel_spline_hole`.
_Avoid_: ad-hoc case selection during CS0

**Flake-Zero Rule**:
Any flakiness in CS0 harness cases blocks progress until determinism is restored.
_Avoid_: dropping flaky anchor cases to keep velocity

**CS1 First Removal Target**:
Support/projection exception masking is removed before other fallback classes.
_Avoid_: downstream-first fallback cleanup

**Fallback Removal Sequence**:
After support/projection cleanup, removal order is solver rescue branches, then output UV/topology synthetic fallbacks, then metrics shims.
_Avoid_: output-first cleanup before solver validity

**CS0.5 Seam-First Bootstrap**:
Before CS1 cleanup, reintroduce backend seam and fishnet skeleton without fallback behavior so strict harness can evaluate an explicit fishnet path.
_Avoid_: attempting fallback-removal sequencing before a concrete fishnet path exists

**Strict Skeleton Semantics**:
The initial fishnet skeleton must return explicit invalid/not-solved statuses rather than synthetic partial outputs.
_Avoid_: permissive placeholder outputs

**Seam Module Boundary**:
The drape backend seam is implemented in `drape_backend.py`, `drape_backend_fishnet.py`, and `drape_backend_legacy.py`, not embedded in `CompositeShell.py`.
_Avoid_: feature-layer seam entanglement

**Bootstrap Backend Default**:
During CS0.5, legacy backend remains default; fishnet backend is enabled only via explicit property/flag.
_Avoid_: premature fishnet-by-default rollout

**Persistent Backend Selector**:
Backend choice is a persisted `CompositeShell` property (e.g., `DrapeBackend = legacy|fishnet`).
_Avoid_: non-persistent runtime-only backend switches

**Bootstrap Failure Signaling**:
When fishnet is selected but not solved, recompute must emit explicit error/status signaling and invalid outputs.
_Avoid_: silent no-op success semantics

**Seam Boundary Test Rule**:
CS0.5 must include FeaturePython tests asserting legacy baseline success and explicit fishnet hard-fail signaling when unsolved.
_Avoid_: relying solely on lower-level harness checks for seam behavior

**Bootstrap Diagnostics Schema**:
CS0.5 includes a minimal structured fishnet diagnostics payload schema from day one.
_Avoid_: deferred ad-hoc diagnostics retrofits

**Diagnostics Persistence Rule**:
Fishnet diagnostics are persisted on `CompositeShell` as a read-only property for inspection and reproducibility.
_Avoid_: transient-only diagnostic state

**Diagnostics Serialization Format**:
Persisted diagnostics use a JSON string property with an explicit schema-version field.
_Avoid_: proliferating many scalar diagnostic properties

**Diagnostics Schema Contract**:
The diagnostics JSON enforces stable required keys: `schema_version`, `backend`, `status`, `failure_reason`, and `timestamp`.
_Avoid_: free-form schema drift

**Failure Reason Enum Rule**:
`failure_reason` uses a constrained enum from the initial schema version onward.
_Avoid_: free-text failure reasons

**Initial Failure Reason Enum**:
The initial enum values are `not_implemented`, `invalid_support`, `projection_failed`, and `solver_unsolved`.
_Avoid_: ad-hoc failure-reason additions without schema update

**Fail-Fast Consumer Behavior**:
During intermediate stages, invalid fishnet states must surface explicit errors instead of returning partial/placeholder outputs.
_Avoid_: partial-data continuity during gate-failing stages
## Relationships

- The **Fishnet Core** must satisfy the **Drape Contract**
- The **Drape Contract** is stable across backend rewrites
- The **Hard-Fail Production Policy** governs release behavior when fishnet gates fail
- **Legacy Comparison Mode** is optional and must be manually enabled by user selection
- The **Diagnostic Labeling Rule** prevents legacy-mode runs from counting as production gate evidence
- The **Gate-Blocking Policy** controls stage advancement during implementation
- The **Determinism Envelope** defines repeatability acceptance for validation runs
- **Baseline-First Execution** means the approved docs are executable, not provisional
- The **Harness-First Slice** precedes all solver/path refactoring work
- The **Root-Cause Triage Order** defines deterministic failure-remediation sequencing
## Example dialogue

> **Dev:** "Can we change output data structures while rebuilding?"
> **Domain expert:** "Only inside the **Fishnet Core**; the **Drape Contract** remains unchanged for consumers."
>
> **Dev:** "Can we bypass a failing gate this once?"
> **Domain expert:** "No — under **Gate-Blocking Policy**, only explicit user-approved exceptions are allowed, and we prefer none."

## Flagged ambiguities

- "recreate from scratch" was ambiguous between full API redesign and internal rebuild — resolved: internal rebuild only, **Drape Contract** stays stable.
- "fallback" was ambiguous between production behavior and diagnostics tooling — resolved: no automatic production fallback; legacy behavior is available only via explicit **Legacy Comparison Mode** selection.