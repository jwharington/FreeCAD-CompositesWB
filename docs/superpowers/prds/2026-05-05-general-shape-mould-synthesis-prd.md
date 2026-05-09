# PRD: General-Shape Mould Synthesis (Two-Piece First)

**Date:** 2026-05-05  
**Repository:** `FreeCAD-CompositesWB`  
**Status:** Implemented baseline complete (Slices A-G delivered)  
**Related spec:** `docs/superpowers/specs/2026-04-29-general-shape-mould-synthesis-design.md`

---

## 1) Executive Summary

Upgrade the current `MouldAnalysis` workflow from simple heuristic splitting to a robust, geometry-aware, **best-effort two-piece mould synthesis** pipeline for general BRep shapes.

The system must:
- Prefer a clean two-half tooling result when feasible.
- Handle concavity, overhangs, recesses, and internal openings better than today.
- Support shell-like composite inputs by normalizing to an effective moulding solid when thickness/laminate data exists.
- Return explicit **Ready / Warning / Fail** outcomes with actionable diagnostics.

## 1.1) Implementation Progress Snapshot (2026-05-09)

- **Slice A complete** (normalization confidence contract, strict thickness-hint gating, normalization diagnostics in `AnalysisSummary` and `ValidationChecks`).
- **Slice B advanced through b6** with deterministic geometry-aware ranking diagnostics:
  - `b1`: geometry-aware backface risk scoring,
  - `b2`: structured per-candidate diagnostics payload,
  - `b3`: deterministic winner rationale text,
  - `b4`: rank/margin-to-best diagnostics,
  - `b5`: preferred score coherence with geometry terms,
  - `b6`: preferred-vs-best diagnostics (candidate match vs fallback) rolled into summary + validation checks.
- **Slice C complete through c4**: deterministic candidate planner now returns selected strategy, scored alternatives, attempt diagnostics, and explicit selection rationale.
- **Slice D complete through d5**: strict null-geometry fail contract, degraded-but-usable warning semantics, structured validation reason payload (`validation_reasons` / `validation_reason_codes`), and preview-child coherence across fail→recovery recomputes.
- **Slice E complete through e5**: dedicated general-shape integration coverage for convex baseline, concave/overhang, internal opening/recess, shell-like normalization contract, and cross-fixture status/property contract matrix.
- **Slice F complete through f4**: diagnostics schema/property contract lock, user-facing summary coherence hardening, representative fixture determinism matrix checks, and formal diagnostics/validation contract documentation.
- **Slice G complete through g3**: advisory multipart-readiness decomposition payload contract, deterministic multipart recommendation diagnostics for concave/overhang cases, and explicit normalization-fail decomposition diagnostics based on validation reason-code regions.
- Dedicated mould integration module now covers the required real fixtures:
  - sphere,
  - box,
  - rotated off-axis box,
  - generic lofted shell,
  - concave/overhang composite,
  - internal opening/recess shape.
- Current gate status: FreeCAD integration suite passing (49 tests) and fishnet native suite passing (66 tests), with known non-fatal TopoShape mapper warnings in integration output.

---

## 2) Problem Statement

Current implementation provides a useful MVP for simple shapes but does not satisfy the general-shape goals.

### Current baseline (as implemented)

From:
- `freecad/Composites/tools/mould_analysis.py`
- `freecad/Composites/features/MouldAnalysis.py`
- `freecad/Composites/compositestests/test_integration_freecad.py`

The existing behavior is:
- Axis-only candidate directions (`X/Y/Z`) with bounding-box extent scoring.
- Simple rectangular mid-plane parting surface proposal.
- Box-derived half generation with boolean cut.
- Heuristic undercut/draft warnings via section area profile.
- Working `MouldAnalysis` object wiring and integration tests for simple and overhang cases.

This is still an early heuristic path (`WORK-IN-PROGRESS` in command tooltip), not full general-shape synthesis.

---

## 3) Product Goals

### Primary goals
1. Accept general BRep solids for two-piece-first synthesis.
2. Normalize shell-like inputs into an effective solid (when thickness/laminate supports it).
3. Improve draw/split decision quality beyond axis-only heuristics.
4. Generate credible parting surfaces and two mould halves for non-trivial shapes.
5. Provide explicit, inspectable diagnostics and status classification.

### Secondary goals
1. Keep `MouldAnalysis` object interface stable.
2. Preserve current prototype behavior as fallback where needed.
3. Keep architecture ready for future multipart decomposition.

---

## 4) Non-Goals

- Global optimization of multipart tooling.
- Full manufacturing feature generation (flanges, stock, clamping hardware).
- Universal topology repair for arbitrary broken CAD inputs.
- Full UI redesign.

---

## 5) Users and Jobs-to-be-Done

### Primary users
- Composite tooling engineers using FreeCAD Composites WB.
- Power users validating draft/undercut risk before tooling decisions.

### Jobs-to-be-done
- “Given this part, propose the best practical two-piece mould split.”
- “Tell me clearly if result is approximate or risky, and why.”
- “Keep recompute stable and preview outputs deterministic.”

---

## 6) Scope

### In scope (v1)
- Effective-solid normalization for solid + shell-like sources.
- Geometry-aware analysis (adjacency, normals, visibility/draft/undercut hints).
- Bounded candidate split generation and scoring.
- Split attempt, closure/capping, and robust validation.
- Ready/Warning/Fail result policy with diagnostic payload.
- Unit + integration tests for convex/concave/opening/shell cases.

### Out of scope (v1)
- Multipart global planning.
- Manufacturing-ready surface refinement for all topology classes.

---

## 7) Functional Requirements

### FR-1 Input normalization
- Accept `Part::Shape` solid inputs unchanged.
- For shell-like sources, derive effective moulding solid from thickness/laminate metadata when available.
- If approximation is used, set approximation flags and include diagnostic reason.

### FR-2 Geometry analysis layer
- Build lightweight structural descriptors:
  - face adjacency graph,
  - face-normal clusters,
  - per-face/region draft estimates,
  - visibility/occlusion hints for candidate pull directions,
  - undercut grouping,
  - boundary/silhouette hints.
- Produce ranked candidate draw directions with rationale.

### FR-3 Candidate synthesis planner
- For top candidate directions, propose bounded set of split strategies/surfaces.
- Attempt candidates in deterministic order.
- Score each candidate by split validity + undercut reduction + robustness.

### FR-4 Split generation
- Attempt split of effective solid by selected strategy.
- Cap/close open results as needed.
- Produce two candidate mould halves with closure status and volumes.

### FR-5 Validation + status policy
- Classify output as:
  - `Ready` (credible two-piece result),
  - `Warning` (usable but degraded/approximate),
  - `Fail` (no credible two-piece result).
- Never mark null/invalid geometry as success.
- Preserve best candidate details on warning/fail.

### FR-6 Diagnostics contract
- Persist machine-readable and human-readable diagnostics:
  - chosen direction + ranking,
  - undercut/draft summaries,
  - split candidate outcomes,
  - validation checks,
  - approximation/degradation reasons.
- Current implemented top-level contract from `analyze_source_shape` includes:
  - status/summary: `status`, `summary`,
  - validation: `validation_status`, `validation_summary`, `validation_checks`, `validation_reasons`, `validation_reason_codes`,
  - split planning: `split_strategy_summary`, `split_strategy_diagnostics`, `split_strategy_attempts`,
  - normalization: `normalization_confidence`, `normalization_source_type`, `normalization_summary`, `normalization_reason_flags`.
- Status semantics are strict: null geometry is hard-fail, degraded-but-usable halves are warning-grade; representative fixture re-runs must remain deterministic for the above diagnostics fields.

### FR-7 Interface stability
- Keep `MouldAnalysis` object stable and backward-compatible for existing users/tests.
- Preview children (`PartingSurface`, `MouldHalfA`, `MouldHalfB`) must remain consistent and recompute-safe.

### FR-8 Determinism and recompute safety
- Same input and settings must produce same ranked candidates and selected strategy.
- Recompute path must not crash on failed candidate attempts.

---

## 8) Non-Functional Requirements

- **Reliability:** No document corruption on failed splits.
- **Explainability:** Warnings/failures include clear reasons.
- **Performance:** Candidate search is bounded (no unbounded combinatorics).
- **Testability:** Unit + integration test coverage for major geometry classes.

---

## 9) Success Metrics

1. **Coverage metric:** New tests include at least one passing scenario each for:
   - convex,
   - concave/overhang,
   - internal opening/recess,
   - shell-like normalized input.
2. **Outcome quality metric:** General-shape fixtures produce `Ready` or explicit `Warning` with actionable diagnostics (no silent degradation).
3. **Stability metric:** Existing mould and integration tests remain green.
4. **Determinism metric:** Repeat recompute on identical inputs yields stable selected candidate and status.

---

## 10) Acceptance Criteria

### AC-1 Functional
- System handles non-box-like BRep solids better than axis-midplane heuristic baseline.
- Shell-like inputs can be processed via effective-solid normalization or clearly flagged approximation.
- Ready/Warning/Fail classification is exposed via object properties and summaries.

### AC-2 Validation integrity
- Null half or null parting surface cannot pass validation.
- Warning/fail always includes reason(s) and candidate context.

### AC-3 Backward compatibility
- Existing `MouldAnalysis` command/object integration tests remain green.

### AC-4 Test completeness
- New unit/integration tests cover degraded paths and difficult geometry.
- No test assertions are weakened and no tolerances loosened without explicit approval.

---

## 11) Delivery Plan (Phased)

### Phase 1 — Shape normalization
- Add effective-solid abstraction and approximation flags.

### Phase 2 — Geometry-aware analysis
- Replace axis-only heuristics with face/region-aware scoring.

### Phase 3 — Candidate synthesis
- Add bounded split-strategy generation and deterministic scoring.

### Phase 4 — Validation hardening
- Strengthen warning/fail reporting and preview consistency.

### Phase 5 — Multipart readiness scaffold
- Add decomposition planning hooks only after two-piece path is robust.

---

## 12) Risks and Mitigations

- **Risk:** Split fails on fragile topology.  
  **Mitigation:** deterministic fallback to next candidate + explicit failure diagnostics.

- **Risk:** Shell normalization ambiguity.  
  **Mitigation:** conservative proxy + approximation flags + warning classification.

- **Risk:** Recompute instability.  
  **Mitigation:** strict null checks and non-crashing candidate loop.

- **Risk:** Silent quality regression.  
  **Mitigation:** diagnostics contract + regression test fixtures.

---

## 13) Dependencies

- FreeCAD/Part boolean and surface operations stability.
- Existing `MouldAnalysis` FeaturePython property model.
- Test harness under `freecad/Composites/compositestests`.

---

## 14) Open Questions

1. What minimum laminate/thickness metadata is required to classify shell normalization as non-approximate?
2. What candidate budget (N directions × M split strategies) gives best quality/performance tradeoff?
3. Which geometric score terms should gate candidate ranking for v1 (draft, undercut, closure probability)?
4. Should we expose per-candidate diagnostics as structured JSON-like data in a property, or keep summary strings only?

---

## 15) Traceability to Current Implementation

Current files are suitable starting points but need deeper algorithmic expansion:
- `freecad/Composites/tools/mould_analysis.py` (heuristic baseline)
- `freecad/Composites/features/MouldAnalysis.py` (object interface and previews)
- `freecad/Composites/compositestests/test_integration_freecad.py` (current integration coverage)

This PRD intentionally preserves those interfaces while replacing internals incrementally.
