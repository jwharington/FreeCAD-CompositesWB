# Execution PRD: General-Shape Mould Synthesis (Two-Piece First)

**Date:** 2026-05-05  
**Status:** Active execution (Slice E complete; Slice F next)  
**Parent PRD:** `docs/superpowers/prds/2026-05-05-general-shape-mould-synthesis-prd.md`  
**Spec reference:** `docs/superpowers/specs/2026-04-29-general-shape-mould-synthesis-design.md`

---

## 1) Objective

Deliver a production-credible `MouldAnalysis` pipeline for general BRep shapes while keeping the existing object interface stable.

**Target behavior:** best-effort two-piece synthesis with explicit `Ready / Warning / Fail` outcomes and deterministic diagnostics.

## 1.1) Progress Snapshot (2026-05-09)

### Completed slices/checkpoints

- **Slice A (P0): completed**
  - normalization confidence contract (`exact` / `approximate` / `fail`),
  - strict finite `Thickness > 0` hint gating,
  - explicit normalization diagnostics in both roll-up (`AnalysisSummary`) and detailed checks (`ValidationChecks`),
  - real-geometry fixture policy enforced (sphere/box/rotated box/lofted shell).

- **Slice B (P0): implemented through b6 checkpoints**
  - `b1` `75aaf39`: geometry-aware candidate risk scoring,
  - `b2` `4fb52a3`: candidate rationale diagnostics payload,
  - `b3` `9e6ae1c`: deterministic winner rationale text,
  - `b4` `cfba203`: rank + margin diagnostics,
  - `b5` `7dc3584`: preferred-score coherence with geometry terms,
  - `b6` `af5a5b3`: preferred-vs-best diagnostics (candidate-match/fallback) in result summary + validation checks.

- **Slice C (P0): completed through c4 checkpoints**
  - `c1` `2669ccd`: deterministic split-strategy planner skeleton with selected strategy diagnostics,
  - `c2` `f0962b3`: deterministic attempt loop with non-aborting fallback behavior and attempt trace payload,
  - `c3` `cfd4b0a`: per-strategy undercut/draft scoring for attempt evaluation and selection,
  - `c4` `f116371`: complete deterministic planner diagnostics including scored alternatives and explicit selection reasoning.

- **Slice D (P0): completed through d5 checkpoints**
  - `d1` `e9756fb`: hard-fail null parting geometry (`test_slice_d_d1_null_parting_surface_forces_fail`),
  - `d2` `ecff2ad`: hard-fail null mould half geometry (`test_slice_d_d2_null_mould_half_forces_fail`),
  - `d3` `e51356a`: degraded-but-usable split classified as `Warning` with explicit warning reason (`test_slice_d_d3_degraded_split_classifies_warning_with_reason`),
  - `d4` `e7e60f6`: structured deterministic validation reason payload (`validation_reasons`, `validation_reason_codes`) (`test_slice_d_d4_structured_reason_codes_are_present_and_stable`),
  - `d5` `bb7b7bc`: preview child coherence across fail→recovery recompute (`test_slice_d_d5_preview_children_remain_coherent_across_fail_and_recovery`).

- **Slice E (P0): completed through e5 checkpoints**
  - `e1` `90bfcd8`: convex baseline general-shape integration coverage (`test_slice_e_e1_convex_baseline_general_shape_is_ready`),
  - `e2` `e105d62`: concave/overhang warning diagnostics with deterministic reason codes (`test_slice_e_e2_concave_overhang_general_shape_is_warning_with_reason_codes`),
  - `e3` `2498290`: internal opening/recess degraded/fail semantics coverage (`test_slice_e_e3_internal_opening_recess_general_shape_can_fail_explicitly`),
  - `e4` `b4cda82`: shell-like normalization/status contract coverage (`test_slice_e_e4_shell_like_source_reports_normalization_and_status_contract`),
  - `e5` `8883449`: status-matrix/property-contract stability across representative fixtures (`test_slice_e_e5_general_shape_status_matrix_keeps_property_contract_stable`).

### Current gate status

- `python -m py_compile` on touched mould analysis + tests: passing.
- FreeCAD integration suite (`run_freecad_integration_tests.py`): passing (**43 tests**).
- Known runtime noise remains non-fatal: TopoShape mapper warnings from OCC/TopoShape expansion.

---

## 2) Current Baseline (Starting Point)

Current implementation is heuristic MVP:
- axis-only draw candidates,
- rectangular mid-plane parting surface,
- box-based split/cut halves,
- heuristic undercut/draft warnings,
- integration coverage for simple + overhang cases.

Key files:
- `freecad/Composites/tools/mould_analysis.py`
- `freecad/Composites/features/MouldAnalysis.py`
- `freecad/Composites/compositestests/test_integration_freecad.py`
- `freecad/Composites/compositestests/test_integration_mould_analysis.py`

---

## 3) In-Scope Deliverables

1. Effective-solid normalization for solids + shell-like inputs.
2. Geometry-aware direction/split analysis.
3. Deterministic bounded candidate synthesis.
4. Robust split generation + validation.
5. Clear diagnostics and stable preview outputs.
6. Expanded tests for hard geometry + degraded paths.

---

## 4) Execution Slices

## Slice A — Normalization Foundation (P0)

### Build
- Add effective-solid normalization layer.
- Handle:
  - solid input passthrough,
  - shell-like input via thickness/laminate-backed envelope,
  - approximation flags + reasons.

### Tests/Gates
- Unit: normalization result for solid input is exact passthrough.
- Unit: shell-like input yields effective solid or explicit approximation status.
- Integration: recompute does not crash when normalization is approximate.

### Exit Criteria
- Normalization result is always explicit (`exact`/`approximate`/`fail`) with diagnostics.

---

## Slice B — Geometry-Aware Analysis (P0)

### Build
- Replace axis-only ranking with shape-aware analysis:
  - face adjacency,
  - normal clustering,
  - draft/visibility hints,
  - undercut grouping.
- Keep deterministic candidate ranking output.

### Tests/Gates
- Unit: candidate ranking stable across repeated runs.
- Unit: non-trivial shapes produce non-empty ranked candidates.
- Integration: existing `MouldAnalysis` object properties remain populated and valid.

### Exit Criteria
- Candidate ranking has geometry rationale and stable ordering.

---

## Slice C — Candidate Synthesis Planner (P0)

### Build
- Generate bounded split strategies per top-ranked directions.
- Deterministic candidate traversal and scoring.
- Preserve failure reasons per candidate attempt.

### Tests/Gates
- Unit: candidate traversal order deterministic.
- Unit: failed candidates do not abort next candidate.
- Integration: best candidate selected consistently on repeated recompute.

### Exit Criteria
- Planner returns selected candidate + scored alternatives + reasons.

---

## Slice D — Split Generation + Validation Hardening (P0)

### Build
- Implement split/cap/closure checks for chosen strategy.
- Harden validation contract:
  - null geometry cannot pass,
  - explicit `Ready / Warning / Fail` semantics,
  - structured warning/fail reasons.
- Keep preview objects coherent on degraded/fail states.

### Tests/Gates
- Unit: null parting surface/half triggers fail.
- Unit: degraded-but-usable cases classify as warning.
- Integration: preview links remain valid; no partial corruption.

### Exit Criteria
- Validation semantics are strict, explicit, and recompute-safe.

---

## Slice E — General-Shape Test Expansion (P0)

### Build
- Add fixture coverage for:
  - convex baseline,
  - concave/overhang,
  - internal opening/recess,
  - shell-like normalized source.
- Add degraded-path expectations and diagnostics assertions.

### Tests/Gates
- New targeted suite green.
- Existing integration suite remains green.

### Exit Criteria
- Success + warning + fail paths are all test-covered.

---

## Slice F — Stabilization + Docs (P1)

### Build
- Finalize diagnostics schema and user-facing summaries.
- Update docs for normalization, analysis, and validation contracts.
- Remove temporary scaffolding/fallback code no longer needed.

### Tests/Gates
- Full native + integration test runs green.
- Repeat-run determinism checks pass on representative fixtures.

### Exit Criteria
- Implementation is stable, documented, and ready for follow-on multipart planning.

---

## 5) Required Acceptance Gates (Global)

A slice can merge only if all apply:
1. Build/recompute path is stable.
2. New targeted tests pass.
3. Existing tests remain green.
4. Determinism preserved for touched selection/scheduling logic.
5. No tolerance loosening and no weakened/deleted tests without explicit approval.

---

## 6) Definition of Done

Done when all are true:
- General BRep solids perform beyond current axis-midplane heuristic baseline.
- Shell-like inputs are normalized or explicitly marked approximate/fail.
- `Ready / Warning / Fail` classification is reliable and test-validated.
- Diagnostics explain candidate choice and failure/degradation causes.
- Existing `MouldAnalysis` interface remains backward compatible.
- Full test gates pass.

---

## 7) Risks to Watch During Execution

- Boolean split fragility on complex topology.
- Ambiguous shell normalization due to missing metadata.
- Non-deterministic candidate ordering from floating-point tie cases.
- Preview-object inconsistency on partial failures.

Mitigation: deterministic ordering rules, explicit fallback policy, strict validation checks, and regression fixtures for known failure modes.

---

## 8) Immediate Next Task

Start **Slice F** by finalizing diagnostics/user-facing summaries and documentation contracts, then run full stabilization gates while preserving current external `MouldAnalysis` property names.
