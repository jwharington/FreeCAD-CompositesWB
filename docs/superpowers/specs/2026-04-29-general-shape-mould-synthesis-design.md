# General-Shape Mould Synthesis Design

**Date:** 2026-04-29  
**Repository:** `FreeCAD-CompositesWB`  
**Status:** Draft design for implementation planning

## 1. Problem Statement

The current mould analysis workflow can produce a useful two-piece result for simple shapes, but it relies on lightweight heuristics that do not yet scale well to more general BRep solids. The next step is to improve mould synthesis so it can handle:

- concave and locally complex solids
- shapes with holes, recesses, and overhangs
- general FreeCAD BRep surfaces rather than box-like bodies
- shell-like composite parts when thickness or laminate data makes them behave as solids for moulding purposes

The synthesis system should still be **best-effort two-piece first**. It should try to produce a clean two-half tool whenever possible, and only return warnings or failures when the shape cannot be handled robustly by that approach.

## 2. Goals

### Primary goals

1. Accept general BRep solids as mould synthesis inputs.
2. Treat shells as solids when thickness or laminate properties define an effective mouldable volume.
3. Improve split-direction selection beyond axis-only or bounding-box-only heuristics.
4. Generate a credible parting surface and two mould halves for many non-trivial shapes.
5. Produce explicit validation and diagnostic output when the shape is only partially handled.

### Secondary goals

1. Keep the existing `MouldAnalysis` document object stable.
2. Preserve the current illustrative/prototype mould helpers as a reference boundary.
3. Leave room for later multipart decomposition without forcing that complexity into the first pass.

## 3. Non-Goals

This work does not attempt to solve all composite tooling problems at once. In particular, it does not yet aim to:

- optimize multi-piece tooling globally
- generate flanges, stock allowance, or clamping features
- produce exact manufacturing-ready surfacing for every topology class
- replace the current analysis object model with a new one
- implement a general CAD kernel for arbitrary topology repair

Those topics remain future extensions, not blockers for the two-piece-first synthesis improvement.

## 4. Proposed Approach

### 4.1 Shape normalization

Before synthesis, the input should be normalized into an effective working solid:

- If the source is already a solid, use it directly.
- If the source is a shell with thickness or laminate data, derive a conservative effective solid envelope.
- If the source is incomplete or ambiguous, create a best-effort proxy solid and mark the synthesis as approximate.

This keeps the synthesis pipeline shape-agnostic and avoids special-casing shell sources throughout the rest of the algorithm.

### 4.2 Geometry analysis layer

Replace the current coarse heuristics with a shape-aware analysis layer that builds lightweight structural data from the BRep:

- face adjacency graph
- face normal clustering
- draft estimates by face or face region
- visibility from candidate pull directions
- undercut grouping based on blocking geometry
- boundary/silhouette hints for parting-surface placement

The output of this layer is not yet the final tool. It is a scored geometric description of the shape that can feed candidate synthesis.

### 4.3 Candidate synthesis layer

For each promising draw direction, the synthesis layer should:

1. propose a split region or split surface
2. attempt to split the effective solid
3. cap or close open bodies as needed
4. validate the resulting bodies
5. score the candidate based on robustness and undercut reduction

The system should keep a small set of candidates rather than exploring an unbounded search space. The goal is a practical, testable best-effort result, not exhaustive optimization.

### 4.4 Best-effort result policy

The synthesis result should be classified explicitly:

- **Ready** — a credible two-piece split was generated
- **Warning** — a usable result exists, but one or more regions remain imperfect or approximate
- **Fail** — no credible two-piece result could be produced

A warning or failure must still preserve the best candidate direction and diagnostic details so the user can understand why the shape was difficult.

## 5. Components

### 5.1 Input normalization component

**Responsibility:** Convert source geometry into a consistent effective solid.

**Consumes:**
- `Part::Shape`
- thickness / laminate metadata when present

**Produces:**
- effective moulding shape
- approximation flags
- source-type diagnostics

### 5.2 Mould analysis component

**Responsibility:** Evaluate candidate directions and geometry features.

**Consumes:**
- effective solid
- draw-direction preferences

**Produces:**
- candidate direction ranking
- undercut region summaries
- draft violation summaries
- visibility and boundary hints

### 5.3 Synthesis planner component

**Responsibility:** Choose the best candidate split strategy for the shape.

**Consumes:**
- analysis output
- candidate directions
- source shape bounds and face structure

**Produces:**
- parting surface proposal
- split strategy metadata
- candidate score and rationale

### 5.4 Split generator component

**Responsibility:** Construct the two mould halves.

**Consumes:**
- effective solid
- chosen parting surface

**Produces:**
- first mould half shape
- second mould half shape
- half volumes or related measures
- closure state

### 5.5 Validation component

**Responsibility:** Decide whether the synthesis result is acceptable.

**Consumes:**
- parting surface
- mould halves
- undercut and draft diagnostics

**Produces:**
- validation status
- check list
- summary text
- warning/failure reasons

### 5.6 Implemented `analyze_source_shape` diagnostics contract (Slice F f4)

The current implementation returns a stable, inspectable diagnostics payload with these contract fields:

- `status`: analysis-level outcome (`Ready`, `Warning`, `Fail`).
- `summary`: concise roll-up string including normalization, split strategy, and validation outcome.
- `validation_status`: validation-level outcome (`Pass`, `Warning`, `Fail`).
- `validation_summary`: validation roll-up string (`Validation ...: X pass, Y warning, Z fail`).
- `validation_checks`: ordered check list with `PASS:`, `WARN:`, `FAIL:` prefixes.
- `validation_reasons`: structured warning/fail reasons extracted from checks (`severity`, `code`, `label`, `detail`).
- `validation_reason_codes`: ordered list matching `validation_reasons[*].code`.
- `split_strategy_summary`: selected strategy and attempt roll-up (selected id, rank, score, attempts, failures).
- `split_strategy_diagnostics`: per-strategy diagnostics (planned rank/direction/score + attempt status and selection rationale).
- `split_strategy_attempts`: per-attempt trace in deterministic attempt order (`attempt_index`, strategy id/rank, status, score, summary).
- `normalization_confidence`: normalization confidence (`exact`, `approximate`, `fail`).
- `normalization_source_type`: normalized source class (for example `solid`, `shell`, `compound`, `none`).
- `normalization_summary`: normalization explanation with source-hint summary.
- `normalization_reason_flags`: ordered, de-duplicated normalization reason/hint flags.

### 5.7 Implemented status semantics

- `validation_status` is check-driven:
  - `Pass`: no `WARN:`/`FAIL:` checks.
  - `Warning`: one or more `WARN:` checks and no `FAIL:` checks.
  - `Fail`: at least one `FAIL:` check.
- `status` is derived from `validation_status`:
  - `Pass` -> `Ready`
  - `Warning` -> `Warning`
  - `Fail` -> `Fail`
- Null-geometry hard-fail policy:
  - null/invalid parting surface shape is a validation fail,
  - null mould half A or B is a validation fail,
  - these failures cannot be promoted to `Ready`.
- Degraded-but-usable warning policy:
  - if mould halves are reported as `Degraded` **and** both half geometries are non-null and valid, the result is warning-grade (`validation_status=Warning`, `status=Warning`) rather than fail.
- Residual undercuts/draft violations are warning checks; they do not silently pass.

### 5.8 Determinism expectations (representative fixture re-runs)

For the same fixture geometry and same source hints, repeat runs should keep diagnostics stable for representative fixtures (convex, rotated, concave/overhang, internal opening/recess, shell-like with hints):

- stable `status` / `validation_status`,
- stable `split_strategy_summary`, `split_strategy_diagnostics`, and `split_strategy_attempts` ordering/content,
- stable `validation_reasons` and `validation_reason_codes` ordering/content,
- stable normalization diagnostics (`normalization_confidence`, `normalization_source_type`, `normalization_summary`, `normalization_reason_flags`).

`validation_reason_codes` must always equal `validation_reasons[*].code` in order. Split attempt indices are sequential (`1..N`) in deterministic strategy order.

## 6. Data Flow

1. The user selects a part or shell-like source object.
2. The analysis object normalizes the input into an effective solid representation.
3. The analysis layer scores candidate draw directions and identifies geometric problem areas.
4. The synthesis planner proposes one or more parting strategies from those candidates.
5. The split generator attempts the best candidate first.
6. The validation component checks closure, null shapes, and residual problem regions.
7. The `MouldAnalysis` object stores the chosen result and exposes it through document properties and preview objects.

This flow should remain mostly linear so that it is easy to inspect in tests and easy to debug in FreeCAD.

## 7. Error Handling

### 7.1 Approximate or missing shell thickness

If a shell source cannot be converted into a confident effective solid, the system should:

- continue with a conservative proxy if possible
- set the result to `Warning` or `Fail`
- explain that the output is approximate
- preserve the source object and the chosen direction

### 7.2 Unsupported topology or fragile splits

If a candidate split fails because the topology is too complex or the resulting solids are invalid, the system should:

- try the next-best candidate direction if available
- avoid crashing the document recompute path
- report the failure in the validation summary
- leave preview objects empty rather than partially corrupting them

### 7.3 Null or invalid shapes

Any null shape produced during synthesis must be treated as a failure of that candidate. The system may still return an overall warning if a weaker fallback candidate succeeds, but null geometry must never be marked as a successful result.

### 7.4 Partial success

If the system produces a plausible parting surface and only one mould half is robust, the result should still be surfaced as a warning rather than silently accepted. The user should always be able to see which part of the pipeline degraded.

## 8. Testing Strategy

### 8.1 Unit-level geometry tests

Add focused tests for:
- simple convex solids
- solids with recesses and overhangs
- solids with internal openings or cut-through features
- shell-like inputs normalized by thickness
- a case where the best two-piece split succeeds
- a case where the best two-piece split degrades to warning

### 8.2 Integration tests in FreeCAD

Add real-FreeCAD tests that verify:
- the command creates a `MouldAnalysis` object
- the object recomputes correctly
- the chosen parting surface and mould halves are created when possible
- warning/fail states are exposed when the geometry is too complex
- shell-like sources can be handled via their effective thickness model

### 8.3 Regression checks

Keep the current simple mould analysis tests in place so that the enhanced synthesis does not break the working MVP path while it grows in sophistication.

## 9. Rollout Plan

### Phase 1: shape normalization
Introduce the effective solid abstraction for solids and shell-like sources.

### Phase 2: geometry-aware analysis
Replace box-only heuristics with face and region analysis.

### Phase 3: candidate synthesis
Add split candidate generation and best-effort two-piece selection.

### Phase 4: validation hardening
Strengthen validation, warnings, and fallback reporting for difficult shapes.

### Phase 5: multipart readiness
Add a decomposition-plan model only after the two-piece-first path is robust for general shapes.

**Implementation note (2026-05-12):** advisory decomposition-readiness payloads, bounded/two-level multipart prototype execution payloads, manufacturability diagnostics payloads, grouped-overlay/calibration scaffolding, Slice L calibration-matrix + clustered-overlay reporting semantics, and Slice M rotated/off-axis draft diagnostics hardening are implemented in `analyze_source_shape` (`decomposition_plan_status`, `decomposition_plan_summary`, `decomposition_plan_candidates`, `decomposition_plan_regions`, `multipart_execution_status`, `multipart_execution_summary`, `multipart_execution_attempts`, `multipart_piece_count`, attempt-level `split_offsets` / `split_depth`, plus `manufacturability_*` fields for metrics/overlay/groups/clusters/recommendations/score breakdown/calibration metadata). Slice M also adds deterministic regression coverage that prevents false draft/undercut positives on rotated convex fixtures while preserving concave/overhang multipart-readiness signal and the external `MouldAnalysis` property interface contract. Slice N additionally updates `freecad/Composites/tools/mould.py::make_moulds` to cavity-first output semantics (blank minus source) with deterministic repeat-run and fail-closed null-shape fallback coverage. Slice O adds deterministic cavity-generation UX contracts in `freecad/Composites/tools/mould.py::make_moulds_with_diagnostics` plus `Mould` FeaturePython recompute status fields (`GenerationStatus`, `GenerationSummary`) and repeat-run fail-closed integration coverage, while keeping external `MouldAnalysis` properties/interfaces unchanged.

## 10. Success Criteria

The enhancement is successful when:

- general BRep solids can be synthesized beyond box-like examples
- shell-like composite parts can be treated as solids using thickness or laminate data
- the system still prefers a two-piece result first
- invalid or approximate outputs are clearly labeled
- integration tests cover both success and degraded cases
- the design remains compatible with future multipart decomposition

## 11. Relationship to Existing Work

This design builds on the current `MouldAnalysis` workflow and its existing preview objects. It does not require replacing the current document object model. Instead, it deepens the analysis and synthesis layers underneath that stable interface.

The existing mould-related helpers remain prototype-oriented in the sense that they establish the current working boundary, but this design aims to evolve them into a general-shape synthesis path suitable for real composite tooling work.

## 12. Suggested Implementation Slices

To keep the work incremental, implement this design in small tracer-bullet slices:

1. **Normalize source geometry**
   - add an effective-solid abstraction for shells and laminate-backed parts
   - keep solid inputs unchanged
   - expose approximation status to the analysis object

2. **Add shape-aware analysis**
   - build face adjacency and visibility hints
   - score candidate directions from real geometry features
   - keep the current direction-ranking output stable

3. **Improve two-piece synthesis**
   - generate candidate parting surfaces from the analysis data
   - attempt split-and-cap for each candidate
   - choose the best acceptable two-piece result

4. **Strengthen validation and diagnostics**
   - distinguish ready / warning / fail outcomes
   - report null shapes and fragile splits clearly
   - keep preview objects consistent with recompute state

5. **Expand test coverage**
   - add shape cases that are harder than simple boxes
   - cover shell-like thickness-driven inputs
   - verify warning paths as well as success paths
