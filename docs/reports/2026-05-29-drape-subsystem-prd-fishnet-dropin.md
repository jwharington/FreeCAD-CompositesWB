# Product Requirements Document (PRD): Clean-Slate Fishnet Drape Rebuild

**Date:** 2026-05-29  
**Project:** `FreeCAD-CompositesWB`  
**Subsystem:** Composite shell drape mapping (`geometry -> drape state -> flattened map`)  
**Author:** Pi coding agent

---

## 1. Executive Summary

This PRD defines a **clean-slate rebuild** of the drape subsystem.

The target is to recreate fishnet draping from scratch without repeating prior churn patterns: design-by-patching, defect-masking fallbacks, and scaffolding that allows invalid states to appear successful.

Core policy:

1. **Root-cause over workaround** — defects must be fixed at source.
2. **No masked failures** — invalid solve states must be explicit and blocking.
3. **Deterministic quality gates** — output is publishable only when strict gates pass.
4. **Contract stability at boundary only** — external API remains stable; legacy internal behavior is not guaranteed.

---

## 2. Scope

### 2.1 In scope

- Clean-slate fishnet/kinematic backend implementation.
- Stable external contract for downstream consumers.
- Strict diagnostics + gate framework that blocks invalid output.
- Controlled cutover plan from legacy to rebuilt backend.

### 2.2 Out of scope

- UI redesign unrelated to drape correctness.
- Long-term support of dual production backends.
- Runtime compatibility shims that hide solver/geometry defects.

### 2.3 Anti-goals (explicitly prohibited)

- Silent fallback chains (`projection -> synthetic -> bbox -> index defaults`).
- Broad exception swallowing that returns success semantics.
- Metric shims that inflate pass rates (for example synthetic denominator floors).
- “Pass with warning” when mandatory gates fail.

---

## 3. Current System Deep Dive (As-Is)

### 3.1 Current entry path

Primary orchestration is in:
- `freecad/Composites/features/CompositeShell.py` (`CompositeShellFP.execute(...)`)

Current flow:
1. Resolve support geometry.
2. Build drape mesh.
3. Run flattening backend.
4. Publish texture coords, LCS, boundaries, strain-like outputs.

### 3.2 Current failure pattern to avoid

Prior iterations showed repeated communication and implementation churn due to:
- late validation,
- fallback-heavy control flow,
- patch loops over symptoms,
- stale artifact confidence (visual outputs not always fresh/recomputed).

This PRD treats those as process defects to prevent structurally.

---

## 4. Problem Statement

We need a fishnet-native drape implementation that is physically constrained and deterministic, while preserving downstream API expectations.

The old pattern (`triangle unwrap -> patch outputs`) must be replaced with (`constructive fishnet solve -> validated outputs`).

### 4.1 Root-cause policy

Production mode SHALL NOT:
1. auto-switch to legacy backend on fishnet failure,
2. auto-skip drape solve and silently reuse stale/partial outputs,
3. silently clamp/substitute values without diagnostics,
4. publish outputs when hard gates fail.

---

## 5. Product Goals

1. **Correctness-first fishnet backend** in production path.
2. **Stable consumer contract** for existing integrations.
3. **Strict observability** for failure classes and diagnostics.
4. **Hard-gated release discipline** with blocking criteria.
5. **Reproducible outputs** under identical inputs/config.

---

## 6. Functional Requirements (To-Be)

### 6.1 Contract requirements

The rebuilt backend SHALL provide:
- `isValid()`
- `get_lcs(...)`
- `get_lcs_at_point(...)`
- `get_tex_coord_at_point(...)`
- `get_tex_coords(...)`
- `get_boundaries(...)`
- strain-equivalent output (`XX/YY/XY` semantics)

Contract stability applies to **API and semantic behavior**, not to legacy internal fallback mechanics.

### 6.2 Solver requirements

1. Seedable warp/weft lattice growth from `(P, L1, L2)`.
2. Node construction by geometric constraints + on-surface condition.
3. Deterministic branch selection and explicit reject reasons.
4. Shear feasibility/locking enforcement during solve.
5. Optional NCF extensions (asymmetric shear / controlled slip) as explicit modes.
6. Flattened mapping and orientation extraction from solved fishnet state.

### 6.3 Failure behavior requirements

On failure, subsystem SHALL:
1. fail safely (no crash),
2. emit structured diagnostics,
3. mark result invalid,
4. block publication to dependent consumers,
5. allow legacy comparison only via explicit debug switch.

---

## 7. Non-Functional Requirements

1. **Determinism** — repeated runs with same inputs must match within tolerance.
2. **Observability** — explicit status counts and reason taxonomy.
3. **Strict validity** — gate-failing outputs are non-publishable.
4. **Performance** — interactive recompute practical without bypassing gates.
5. **Traceability** — each invalid state reproducible from logged inputs/config.

---

## 8. Target Architecture

### 8.1 Production backend model

- `FishnetKinematicDrapeBackend` is the production backend.
- `UvUnwrapDrapeBackend` may exist only as debug comparison (non-auto).

### 8.2 Architecture invariants

1. No synthetic geometry success paths in core solve.
2. No internal fallback chain that can convert failure into synthetic success.
3. Output topology and UV derive from solved/support-valid state only.
4. Support checks use narrow, typed failure handling.

### 8.3 Minimal data model

Per node/cell state must include:
- lattice index,
- geometry position,
- flatten coordinate,
- validity status,
- explicit failure/reject reason.

---

## 9. Algorithm Requirements (Fishnet/Kinematic)

1. Seed and initialize local frame.
2. Constructive growth with two-neighbor constraints.
3. Deterministic candidate selection.
4. Explicit rejection for invalid/contact/boundary/locking failures.
5. Quad connectivity assembly from solved occupancy.
6. Flatten map and orientation extraction from solved state.

Reference implementation inspiration:
- `/home/jmw/opt/KinDrape/Python implementation/KinDrape_eff_NR.py`

---

## 10. Migration Plan (Root-Cause First)

### Phase 1 — Contract + gate framework
- Freeze external contract.
- Implement strict gate harness and invalid-result blocking.

### Phase 2 — Deterministic solver core
- Implement constructive fishnet solve with explicit failure taxonomy.
- Remove defect-masking branches in solver/support/projection paths.

### Phase 3 — Metrics + consumer integration
- Enforce strict metrics semantics (no compatibility inflation shims).
- Validate consumer integrations (TexturePlan/LCS/FEM).

### Phase 4 — Cutover
- Enable fishnet as production backend.
- Keep legacy backend debug-only during short deprecation window.

### Phase 5 — Legacy retirement
- Remove legacy production wiring after sustained gate-pass window.

---

## 11. Validation and Test Plan

### 11.1 Required geometry matrix

1. `ud_plate_basic`
2. `flat_panel_spline_hole`
3. `tubular_shell`
4. `cylindrical_panel_segment`
5. `conical_panel_segment`

### 11.2 Mandatory gate categories (blocking)

A release candidate fails if any category fails on any required geometry:

1. **Support adherence**
   - `on_support_ratio == 1.0`
   - `outside_node_count == 0`
   - `outside_edge_count == 0`
2. **Coverage**
   - node/cell recall and span coverage over strict profile minima
3. **Duplicate collapse control**
   - unique-point ratio and duplicate ratio within strict bounds
4. **Hole crossing control**
   - hole-crossing cell count within strict limit (target zero)
5. **UV physical-scale consistency**
   - edge scale consistency and p95 error within strict profile

### 11.3 Kill-switch gate policy

If a mandatory gate fails:
- stop stage progression,
- open root-cause fix task,
- prohibit fallback-based waiver.

### 11.4 Artifact trust requirements

Every validation run must produce fresh, traceable artifacts:
- `geometry_3d.html`
- `texture_flat.html`
- `plot_data.json`
- diagnostics payload linked to gate results

No stale/cached artifact acceptance.

---

## 12. Risks and Mitigations

1. **Solver stalls on complex curvature**  
   Mitigation: improve solve math/step control; no masking fallback.
2. **Orientation discontinuities**  
   Mitigation: frame continuity checks + root-cause correction.
3. **Runtime pressure to bypass gates**  
   Mitigation: make gate bypass non-permitted for release.
4. **Reintroduction of patch-loop behavior**  
   Mitigation: enforce stage stop rules + reasoned RCA before retries.

---

## 13. Definition of Done

Done means all are true:

1. Fishnet backend is production path.
2. External consumer contract is met.
3. All strict gates pass on required geometry matrix.
4. Diagnostics/artifacts are fresh, reproducible, and traceable.
5. No production defect-masking fallback/scaffolding remains.
6. Legacy path is debug-only or retired per deprecation plan.

---

## 14. Requirement Traceability (PRD -> Code -> Tests -> Gates)

| Requirement | Implementation Targets | Test Targets | Gate |
|---|---|---|---|
| Constructive fishnet solve with explicit failures | `freecad/Composites/tools/drape_backend_fishnet.py`, `fishnet_geometry.py`, `fishnet_numerics.py` | `test_fishnet_geometry.py`, `test_fishnet_numerics.py`, `test_fishnet_scheduler.py` | Support/Coverage |
| Strict support/projection semantics | `drape_backend_fishnet.py` support/projection helpers | `test_drape_backend_fishnet_support_api.py` | Support adherence |
| Output topology/UV from solved state only | `drape_backend_fishnet.py` output builders | `test_freecad_fp.py`, `test_drape_backend_fishnet_gates.py` | Duplicate + UV scale |
| Strict metrics semantics (no shim inflation) | `freecad/Composites/tools/fishnet_metrics.py` | `test_fishnet_metrics.py`, `test_drape_backend_fishnet_gates.py` | Coverage + UV + hole crossing |
| Consumer contract compatibility | `CompositeShell.py` + backend adapter seam | `test_freecad_fp.py`, `test_drape_laminate_provider.py` | Contract/Release |

---

## 15. Key Files Referenced

- `freecad/Composites/features/CompositeShell.py`
- `freecad/Composites/tools/drape_backend_fishnet.py`
- `freecad/Composites/tools/fishnet_geometry.py`
- `freecad/Composites/tools/fishnet_numerics.py`
- `freecad/Composites/tools/fishnet_metrics.py`
- `freecad/Composites/compositestests/test_drape_backend_fishnet_gates.py`
- `freecad/Composites/compositestests/test_fishnet_metrics.py`
- `freecad/Composites/compositestests/test_freecad_fp.py`
