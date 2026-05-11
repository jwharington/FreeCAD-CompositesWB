# Post-Slice-M Next Slice Brief (2026-05-12)

## Proposed next slice
**Slice N — Cavity-First Mould Output Semantics**

## Why this is next
- Current `Mould` feature execution path (`freecad/Composites/features/Mould.py`) sets `fp.Shape = make_moulds(...)`.
- `make_moulds` (`freecad/Composites/tools/mould.py`) currently builds a mould blank/loft envelope and returns it without subtracting the source shape.
- In contrast, `MouldAnalysis` preview halves already apply cavity semantics (`left.cut(shape)` / `right.cut(shape)` in `make_mould_halves` within `freecad/Composites/tools/mould_analysis.py`).
- This creates a user-visible semantic mismatch: generated mould body can intersect the source unless an extra manual boolean cut is applied.

## Slice N objective
Make cavity-first behaviour the default for generated mould geometry (source removed from mould blank), while preserving recompute stability and deterministic outputs.

## Scope (smallest correct increment)
1. **Default cavity subtraction in mould generation**
   - Update `freecad/Composites/tools/mould.py::make_moulds` so the returned shape is the mould blank with source cavity removed by default.
2. **Recompute-safe deterministic fallback**
   - If boolean subtraction fails, keep deterministic fallback behaviour (no crash; explicit, stable fallback path).
   - Prefer fail-closed semantics over silent intersecting output where feasible.
3. **No external `MouldAnalysis` interface changes**
   - Do not add/remove/rename `MouldAnalysisFP` properties.
   - Keep existing analysis payload/property stability tests green.

## Deterministic contract + test implications
Add focused integration coverage (one test per checkpoint style):
1. **Cavity contract test (Mould feature)**
   - Create source solid + mould object.
   - Assert `mould.Shape.common(source.Shape).Volume == 0` (or within tight numeric epsilon) after recompute.
2. **Deterministic repeat-run test**
   - Recompute same document multiple times; assert stable intersection volume and stable non-null output status.
3. **Behaviour parity note/test**
   - Confirm this does not change `MouldAnalysis` external properties or existing status fields.

Recommended test location:
- `freecad/Composites/compositestests/test_integration_freecad.py` for `Mould` command behavior.
- Keep existing `test_integration_mould_analysis.py` property-stability coverage unchanged.

## Acceptance gates
- `python -m py_compile` for touched files.
- FreeCAD integration suite via `run_freecad_integration_tests.py`.
- Fishnet native suite via `run_fishnet_native_tests.py`.
- No tolerance loosening; no weakened/deleted tests.

## Risks and mitigations
- **Boolean fragility on complex topology:** use deterministic fallback and explicit test for non-crash behaviour.
- **Numerical noise in intersection checks:** use strict but realistic epsilon and deterministic assertions.
- **Scope creep into broader reporting polish:** keep this slice narrowly on cavity-first output semantics.

## Classification
**Ready-for-implementation slice** (not just planning-only): scope is concrete, bounded, and directly grounded in current code paths and existing test/gate workflow.
