# Implementation Plan

## Goal
Define and implement Slice O as a bounded post-N increment that improves cavity-output UX/reporting while preserving deterministic behavior and keeping external `MouldAnalysis` properties unchanged.

## Tasks
1. **Task 1 (O1 contract scaffolding): Add deterministic mould-generation diagnostics for fail-closed behavior.**
   - File: `freecad/Composites/tools/mould.py`
   - Changes:
     - Introduce a diagnostics-oriented helper (e.g., `make_moulds_with_diagnostics(...)`) returning canonical fields: `shape`, `status`, `reason_code`, `summary`.
     - Keep `make_moulds(shape, buffer=...)` signature unchanged and make it delegate to the diagnostics helper, returning only `shape`.
     - Standardize fallback reason codes to deterministic constants (example set): `ok`, `cut_exception`, `cut_invalid_or_null`.
   - Acceptance:
     - Successful cut path returns non-null valid cavity shape with `status="ok"`.
     - Exception/invalid cut paths deterministically return null shape with stable reason codes and summary text.

2. **Task 2 (O1 UX wiring): Surface cavity-fallback status in the Mould FeaturePython object.**
   - File: `freecad/Composites/features/Mould.py`
   - Changes:
     - Add read-only UX properties on `MouldFP` (e.g., `GenerationStatus`, `GenerationSummary`) and populate them in `execute(...)` from diagnostics helper output.
     - On fail-closed fallback, keep `fp.Shape` null and emit deterministic warning text (no variable exception formatting in user-facing summary).
   - Acceptance:
     - Recompute does not crash on boolean failure.
     - Users can inspect deterministic status/summary directly on the `Mould` object.

3. **Task 3 (O1 test): Add one focused integration test for fail-closed Mould UX contract.**
   - File: `freecad/Composites/compositestests/test_integration_freecad.py`
   - Changes:
     - Add test: `test_slice_o_o1_mould_feature_recompute_exposes_fail_closed_status_on_cavity_cut_failure`.
     - Use monkeypatch of `freecad.Composites.tools.mould._cut_source_from_blank` to force failure, then assert:
       - `Mould.Shape` is null,
       - `GenerationStatus` and `GenerationSummary` are set to deterministic values,
       - recompute path remains stable.
   - Acceptance:
     - Test fails without O1 wiring and passes with O1 implementation.

4. **Task 4 (O2 reporting payload): Add cavity-reporting metrics to analysis result payload (internal-only extension).**
   - File: `freecad/Composites/tools/mould_analysis.py`
   - Changes:
     - Add internal result payload keys derived from source/half intersections (example):
       - `cavity_contract_status` (`pass`/`warning`/`fail`),
       - `cavity_contract_summary`,
       - `cavity_source_intersection_volume_half_a`,
       - `cavity_source_intersection_volume_half_b`.
     - Keep all existing external `MouldAnalysis` properties untouched (no add/remove/rename in `MouldAnalysisFP`).
   - Acceptance:
     - Payload keys exist for representative fixtures with bounded finite numeric values.
     - Existing property-stability contracts remain unchanged.

5. **Task 5 (O2 test): Add one focused integration test for cavity-reporting payload contract.**
   - File: `freecad/Composites/compositestests/test_integration_mould_analysis.py`
   - Changes:
     - Add test: `test_slice_o_o2_mould_analysis_cavity_reporting_payload_exposes_intersection_metrics`.
     - Assert payload keys exist, values are finite/bounded, and convex rotated fixture reports `pass` with near-zero intersections.
   - Acceptance:
     - Test validates payload presence + semantics without relying on external property changes.

6. **Task 6 (O3 reporting polish): Consume cavity-reporting payload in the 3D gallery output.**
   - File: `artifacts/reports/generate_mould_3d_gallery.py`
   - Changes:
     - Extend `_status_table(...)` and case text to show cavity-contract status and per-half source-intersection metrics.
     - Keep ordering deterministic in rendered rows/tokens.
   - Acceptance:
     - Generated HTML shows cavity contract fields consistently for every case.

7. **Task 7 (O3 test): Add one focused determinism integration test for cavity-reporting payload.**
   - File: `freecad/Composites/compositestests/test_integration_mould_analysis.py`
   - Changes:
     - Add test: `test_slice_o_o3_mould_analysis_cavity_reporting_payload_is_repeat_run_deterministic`.
     - Run repeated analysis on the same rotated fixture and assert stable cavity status/summary/volumes and stable token ordering.
   - Acceptance:
     - Repeat-run results match deterministically for all new cavity-reporting fields.

8. **Task 8 (validation + slice closeout): Run gates and sync Slice O docs.**
   - File: `docs/superpowers/prds/2026-05-05-general-shape-mould-synthesis-execution-prd.md`
   - Changes: Mark Slice O checkpoints/tests complete and refresh gate counts.
   - File: `docs/superpowers/prds/2026-05-05-general-shape-mould-synthesis-prd.md`
   - Changes: Add Phase 13 Slice O completion note.
   - File: `docs/superpowers/specs/2026-04-29-general-shape-mould-synthesis-design.md`
   - Changes: Update implementation note with Slice O cavity UX/reporting completion while preserving external `MouldAnalysis` interface.
   - Acceptance:
     - `python -m py_compile` passes on touched Python files.
     - FreeCAD integration runner passes.
     - Fishnet native suite passes.

## Files to Modify
- `freecad/Composites/tools/mould.py` - deterministic diagnostics helper + fail-closed reason-code contract behind existing `make_moulds` signature.
- `freecad/Composites/features/Mould.py` - user-visible deterministic generation status/summary wiring for `Mould` recompute UX.
- `freecad/Composites/tools/mould_analysis.py` - internal cavity-reporting payload extension (no external `MouldAnalysis` property changes).
- `freecad/Composites/compositestests/test_integration_freecad.py` - Slice O O1 integration test.
- `freecad/Composites/compositestests/test_integration_mould_analysis.py` - Slice O O2/O3 integration tests.
- `artifacts/reports/generate_mould_3d_gallery.py` - cavity contract reporting polish in HTML status output.
- `docs/superpowers/prds/2026-05-05-general-shape-mould-synthesis-execution-prd.md` - Slice O status/checkpoint updates.
- `docs/superpowers/prds/2026-05-05-general-shape-mould-synthesis-prd.md` - Slice O phase progression update.
- `docs/superpowers/specs/2026-04-29-general-shape-mould-synthesis-design.md` - implementation note update for Slice O.

## New Files
- None required.

## Dependencies
- Task 1 precedes Task 2 (diagnostics contract must exist before Mould object can consume it).
- Task 2 precedes Task 3 (O1 test depends on new Mould status/summary behavior).
- Task 4 precedes Tasks 5 and 7 (payload fields must exist before contract/determinism tests).
- Task 6 depends on Task 4 (report script consumes new payload fields).
- Task 8 depends on Tasks 1–7.

## Risks
- `context.md` is missing at `/home/jmw/opt/FreeCAD-CompositesWB/context.md`; Slice O should proceed using repository state + existing PRD/spec only unless additional context is provided.
- Adding new `Mould` FeaturePython properties may require compatibility checks for pre-existing documents created before Slice O.
- Floating-point noise in intersection volumes can create flaky assertions; tests must use strict but realistic bounded comparisons and deterministic ordering.
- Must explicitly preserve external `MouldAnalysis` interface/property names; any accidental property changes in `MouldAnalysisFP` are out of scope and should fail checkpoint review.
