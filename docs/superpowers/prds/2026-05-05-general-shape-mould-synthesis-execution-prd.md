# Execution PRD: General-Shape Mould Synthesis (Two-Piece First)

**Date:** 2026-05-05  
**Status:** Execution complete (Slices A-M complete)  
**Parent PRD:** `docs/superpowers/prds/2026-05-05-general-shape-mould-synthesis-prd.md`  
**Spec reference:** `docs/superpowers/specs/2026-04-29-general-shape-mould-synthesis-design.md`

---

## 1) Objective

Deliver a production-credible `MouldAnalysis` pipeline for general BRep shapes while keeping the existing object interface stable.

**Target behavior:** best-effort two-piece synthesis with explicit `Ready / Warning / Fail` outcomes and deterministic diagnostics.

## 1.1) Progress Snapshot (2026-05-12)

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

- **Slice F (P1): completed through f4 checkpoints**
  - `f1` `9923cde`: diagnostics schema + external property contract guard (`test_slice_f_f1_diagnostics_schema_and_property_names_are_stable`),
  - `f2` `2ec491e`: user-facing summary/status coherence + reason payload reuse (`test_slice_f_f2_user_facing_summaries_are_concise_and_status_coherent`),
  - `f3` `8b5230f`: representative fixture determinism matrix (`test_slice_f_f3_representative_fixture_determinism_matrix`),
  - `f4` `b692082`: diagnostics/validation contract documentation in spec + PRD.

- **Slice G (P1): completed through g3 checkpoints**
  - `g1` `adcb43e`: decomposition-readiness contract payload (`decomposition_plan_status`, `decomposition_plan_summary`, `decomposition_plan_candidates`, `decomposition_plan_regions`) with interface stability guard (`test_slice_g_g1_decomposition_readiness_contract_is_exposed_and_property_names_stable`),
  - `g2` `74b1760`: concave/overhang multipart recommendation diagnostics with deterministic region signatures (`test_slice_g_g2_concave_warning_recommends_multipart_with_deterministic_regions`),
  - `g3` `184a746`: explicit normalization-fail decomposition contract with validation-code region signatures (`test_slice_g_g3_normalization_fail_decomposition_contract_is_explicit`).

- **Slice H (P1): completed through h3 checkpoints**
  - `h1`: multipart execution contract payload (`multipart_execution_status`, `multipart_execution_summary`, `multipart_execution_attempts`, `multipart_piece_count`) with external property stability guard (`test_slice_h_h1_multipart_execution_contract_is_exposed_and_property_names_stable`),
  - `h2`: bounded multipart prototype execution (max one extra split; max ~3 pieces) for concave warning/fail scenarios with deterministic attempt payload (`test_slice_h_h2_concave_warning_executes_bounded_multipart_prototype_deterministically`),
  - `h3`: explicit normalization-fail multipart execution skip contract (`not_attempted`) (`test_slice_h_h3_normalization_fail_multipart_prototype_is_explicitly_not_attempted`).

- **Slice I (P1): completed through i3 checkpoints**
  - `i1`: two-level bounded multipart attempt payload (`split_offsets`, `split_depth`) with bounded partition count (max ~4 pieces) (`test_slice_i_i1_two_level_multipart_attempts_are_bounded_and_exposed`),
  - `i2`: deterministic two-level multipart attempt ordering/summary contract (`selected_depth`, `selected_offset_count`) (`test_slice_i_i2_two_level_multipart_attempts_are_deterministic`),
  - `i3`: external `MouldAnalysis` property stability guard while internal multipart payload expands (`test_slice_i_i3_external_mouldanalysis_properties_remain_unchanged`).

- **Slice J (P1): completed through j3 checkpoints**
  - `j1`: manufacturability payload contract in `analyze_source_shape` (`manufacturability_status`, `manufacturability_summary`, `manufacturability_metrics`, `manufacturability_overlay_*`, `manufacturability_recommendations`, `manufacturability_score_breakdown`) (`test_slice_j_j1_manufacturability_payload_contract_is_exposed`),
  - `j2`: deterministic manufacturability overlay band ordering and pull-direction summary contract (`test_slice_j_j2_overlay_bands_are_deterministic_and_sorted`),
  - `j3`: manufacturability recommendations + risk score coherence with external property stability guard (`test_slice_j_j3_recommendations_and_property_stability`).

- **Slice K (P1): completed through k3 checkpoints**
  - `k1`: grouped overlay payload contract (`manufacturability_overlay_groups`, `manufacturability_overlay_group_count`, `manufacturability_overlay_group_summary`) and not-applicable defaults (`test_slice_k_k1_overlay_group_contract_is_exposed`),
  - `k2`: deterministic grouped overlay + calibration payloads (`manufacturability_calibration_version`, `manufacturability_calibration_inputs`, `manufacturability_calibration_weights`) (`test_slice_k_k2_grouping_and_calibration_payloads_are_deterministic`),
  - `k3`: external `MouldAnalysis` property stability guard for new grouped/calibration payload fields (`test_slice_k_k3_external_mouldanalysis_properties_remain_unchanged`).

- **Slice L (P1): completed through l3 checkpoints**
  - `l1`: calibration-matrix payload stabilization across representative fixtures with bounded/deterministic score-contract checks,
  - `l2`: cluster-level grouped-overlay reporting payload (`manufacturability_overlay_cluster_summary`, `manufacturability_overlay_top_clusters`) with deterministic summary/top-cluster semantics,
  - `l3`: recommendation/summary alignment with cluster-calibration context plus external `MouldAnalysis` property stability guard.

- **Slice M (P1): completed through m3 checkpoints**
  - `m1` `3d76f69`: rotated convex/off-axis fixture no longer emits false draft/undercut violations (`test_slice_m_m1_rotated_convex_box_avoids_false_draft_and_undercut_flags`),
  - `m2` `3d76f69`: repeat-run determinism checks for rotated-fixture violation diagnostics (`test_slice_m_m2_rotated_box_violation_diagnostics_are_repeat_run_deterministic`),
  - `m3` `3d76f69`: concave/overhang multipart-readiness signal remains explicit after heuristic correction (`test_slice_m_m3_concave_overhang_still_reports_multipart_relevant_signal`),
  - external `MouldAnalysis` interface/property names remain unchanged (internal diagnostics-only refinement).

### Current gate status

- `python -m py_compile` on touched mould analysis + tests: passing.
- FreeCAD integration suite (`run_freecad_integration_tests.py`): passing (**74/74 tests**).
- Fishnet native suite (`run_fishnet_native_tests.py`): passing (**106 tests**).
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

## Slice G — Multipart Readiness Scaffolding (P1)

### Build
- Add advisory decomposition-readiness payload to `analyze_source_shape` while preserving external `MouldAnalysis` properties.
- Emit deterministic multipart recommendation candidates/regions for warning/fail scenarios.
- Thread validation reason codes into decomposition region signatures for explicit fail-path diagnostics.

### Tests/Gates
- Dedicated integration coverage for decomposition payload presence, warning recommendation semantics, and normalization-fail contract.
- Full integration and fishnet native suites remain green.

### Exit Criteria
- Multipart-readiness diagnostics are explicit, deterministic, and backward-compatible with the existing document-object interface.

---

## Slice H — Bounded Multipart Prototype Execution (P1)

### Build
- Add bounded multipart execution payload to `analyze_source_shape` while preserving external `MouldAnalysis` properties.
- Execute at most one additional split plane derived from deterministic violation-region midpoints (max ~3 source partitions).
- Emit deterministic multipart attempt diagnostics and selected prototype summary for warning/fail decomposition scenarios.
- Keep normalization-fail path explicit by marking multipart execution as `not_attempted` with reason text.

### Tests/Gates
- Dedicated integration coverage for multipart execution contract exposure and external property stability.
- Dedicated integration coverage for deterministic bounded multipart attempt execution on concave warning/fail fixtures.
- Dedicated integration coverage for normalization-fail explicit multipart skip semantics.
- Full integration and fishnet native suites remain green.

### Exit Criteria
- Multipart execution prototype diagnostics are explicit, deterministic, bounded, and backward-compatible with the existing document-object interface.

---

## Slice I — Two-Level Bounded Multipart Execution (P1)

### Build
- Expand multipart prototype execution from one extra split to up to two bounded extra split levels using deterministic violation-derived offsets.
- Emit structured per-attempt depth metadata (`split_offsets`, `split_depth`) while preserving existing top-level multipart execution payload fields.
- Keep bounded piece cardinality (`<= 4`) and deterministic attempt IDs/selection summary.
- Preserve external `MouldAnalysis` document-object property names (internal payload-only expansion).

### Tests/Gates
- Dedicated integration coverage for bounded two-level multipart payload shape and piece-count bounds.
- Dedicated integration coverage for deterministic repeat-run multipart attempt/summary payload.
- Dedicated integration coverage for external property stability while internal payload grows.
- Full integration and fishnet native suites remain green.

### Exit Criteria
- Two-level multipart prototype diagnostics are explicit, deterministic, bounded, and backward-compatible with the existing document-object interface.

---

## Slice J — Manufacturability Metrics + Overlay Payloads (P1)

### Build
- Add explicit manufacturability payloads to `analyze_source_shape` while preserving external `MouldAnalysis` properties:
  - status/summary/metrics,
  - overlay status/summary/bands,
  - recommendations and score breakdown.
- Keep manufacturability risk scoring bounded and deterministic (`[0, 1]`) with stable classification (`low` / `medium` / `high`).
- Keep overlay bands deterministic and stably sorted for repeat-run comparisons.

### Tests/Gates
- Dedicated integration coverage for manufacturability contract exposure on ready/waiting paths.
- Dedicated integration coverage for deterministic overlay bands and pull-direction summaries.
- Dedicated integration coverage for recommendation/score consistency and external property stability.
- Full integration and fishnet native suites remain green.

### Exit Criteria
- Manufacturability payloads are explicit, deterministic, and backward-compatible with the existing document-object interface.

---

## Slice K — Grouped Overlay Semantics + Calibration Scaffolding (P1)

### Build
- Add grouped manufacturability overlay payloads:
  - `manufacturability_overlay_groups`,
  - `manufacturability_overlay_group_count`,
  - `manufacturability_overlay_group_summary`.
- Add explicit calibration scaffolding payloads:
  - `manufacturability_calibration_version`,
  - `manufacturability_calibration_inputs`,
  - `manufacturability_calibration_weights`.
- Keep scoring behavior stable by default (`group_density_weight=0.0`) while making calibration inputs/weights inspectable.
- Keep recommendations sorted/deduped and add group-aware recommendations (`target_largest_undercut_group`, `target_largest_draft_group`) when applicable.

### Tests/Gates
- Dedicated integration coverage for grouped-overlay contract and not-applicable defaults.
- Dedicated integration coverage for deterministic grouping/calibration payloads.
- Dedicated integration coverage for external property stability while payload expands.
- Full integration and fishnet native suites remain green.

### Exit Criteria
- Grouped overlay + calibration payloads are explicit, deterministic, and backward-compatible with the existing document-object interface.

---

## Slice L — Calibration Matrix + Clustered Overlay Reporting (P1)

### Build
- Stabilize manufacturability calibration-matrix payload behavior across the representative fixture matrix while preserving external `MouldAnalysis` properties.
- Add cluster-level grouped-overlay reporting payloads (`manufacturability_overlay_cluster_summary`, `manufacturability_overlay_top_clusters`) with deterministic ordering/caps.
- Align recommendations and summary tokens with cluster/calibration context while keeping deterministic internal payload semantics.

### Tests/Gates
- Dedicated integration coverage for calibration payload contract and fixture-matrix bounds/order stability.
- Dedicated integration coverage for deterministic cluster summary/top-cluster reporting semantics.
- Dedicated integration coverage for recommendation/summary alignment and external property stability.
- Full integration and fishnet native suites remain green.

### Exit Criteria
- Calibration + clustered-overlay payloads are explicit, deterministic, bounded, and backward-compatible with the existing document-object interface.

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

Execution PRD scope is complete through **Slice M**. **Immediate next task:** define and approve the post-M slice scope (candidate: cavity-first mould output semantics plus reporting polish continuation) while preserving the stabilized `MouldAnalysis` external interface and diagnostics contract.
