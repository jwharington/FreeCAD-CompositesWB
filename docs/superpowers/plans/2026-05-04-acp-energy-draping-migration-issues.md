# ACP Energy Draping Migration — Issue Breakdown

This checklist tracks actual implementation status against:

- `docs/superpowers/plans/2026-05-04-acp-energy-draping-migration-plan.md`

Local build note: FreeCAD build path for local extension/testing work is `~/opt/FreeCAD/build/pixi-debug`.

### Progress snapshot (current)

- Production algorithm surface is unified to `acp_energy` (+ `acp_strategy`).
- Legacy and alias algorithms are removed from code/UI/tests.
- Solver backend is native-only (pure-Python fallback removed).
- Current-node solver policy is SphereSurface-only.
- v2 spacing+coverage expansion is complete (frontier growth + locked acceptance thresholds).
- `sample_face_impl` is refactored to explicit `init -> grow -> emit` orchestration.
- 🔴 High-priority gap is now **partially addressed**: default growth path is demand-driven (non-adaptive preallocated initialization removed), but variable row/ring cardinality is still missing.
- Validation remains green locally: 42 native tests, 15 integration tests.

---

## Issue 1 — Parameter contract + plumbing

**Title:** Define ACP-style draping parameter contract and wire through model/UI

**Depends on:** none

**Status:** ✅ Complete

### Scope

- Introduce/normalize draping parameters in production path:
  - `seed_point`
  - `auto_draping_direction`
  - `draping_direction`
  - `mesh_size`
  - `material_model` (`woven` / `ud`)
  - `ud_coefficient`
  - `thickness_correction`
- Add algorithm selector/model controls:
  - `acp_energy`
  - `acp_strategy` (`woven` / `surface_spacing`)

### Files

- `freecad/Composites/features/CompositeShell.py`
- `freecad/Composites/tools/fishnet_draper.py`
- `freecad/Composites/taskpanels/task_fishnet_drape.py`
- `freecad/Composites/resources/ui/FishnetDrape.ui`

### Checklist

- [x] Add document properties for missing ACP-style parameters.
- [x] Keep current properties backward compatible where possible.
- [x] Pass parameters from task panel to object properties.
- [x] Pass properties from object into solver call.
- [x] Add algorithm mode flag with safe default for transition.
- [x] Ensure recompute triggered when new properties change.

### Acceptance

- [x] Parameters are editable in UI and persisted on object.
- [x] Solver receives the same values configured in UI.
- [x] Existing adapter methods still work (`get_tex_coords`, `get_boundaries`, `get_lcs`, `strains`).

---

## Issue 2 — Native solver core (ACP energy propagation)

**Title:** Implement `acp_energy` propagation + energy objective in native solver

**Depends on:** Issue 1

**Status:** 🟡 Substantially complete (staged ACP objective), constitutive fidelity still open

### Scope

- Implement ACP-style solve path in native backend as the production path.
- Run native-only solver stack (no pure-Python fallback implementation).
- Enforce deterministic propagation order and explicit termination states.

### Files

- `freecad/Composites/fishnet/fishnet.cpp` (interface entrypoint)
- `freecad/Composites/fishnet/fishnet_algorithm.cpp`
- `freecad/Composites/fishnet/fishnet_algorithm.hpp`
- `freecad/Composites/fishnet/fishnet_algorithm_types.hpp`
- `freecad/Composites/fishnet/fishnet_algorithm_sections.hpp`
- `freecad/Composites/fishnet/fishnet_relaxation_objective.cpp`
- `freecad/Composites/fishnet/fishnet_geometry_sampling.cpp`
- `freecad/Composites/fishnet/fishnet_diagnostics_result.cpp`
- `freecad/Composites/fishnet/fishnet_options.cpp`

### Checklist

- [x] Add mode dispatch in native `solve` entrypoint.
- [x] Implement ACP-style propagation ordering (primary, orthogonal, fill).
- [x] Implement woven objective (staged shear/spacing objective).
- [x] Implement UD objective shaping (`ud_coefficient`).
- [x] Add higher-order constitutive shaping control (`objective_p_norm`) for UD anisotropy response.
- [x] Add pre-shear constitutive hook (`pre_shear_deg`) with signed bias-family target asymmetry.
- [x] Add optional cell-level objective hooks (shear/fiber-angle p-norm terms) with explicit gain/weights.
- [x] Expose objective anisotropy + signed-shear diagnostics (edge orientation buckets, target/weight anisotropy ratios, positive/negative bias-family summaries).
- [x] Expose cell-objective diagnostics (cell counts, mean shear/fiber-angle terms, combined p-norm objective statistics).
- [x] Add clear convergence/termination reasons (`converged`, `max_iterations`, `infeasible`).
- [x] Return structured diagnostics for failures/non-convergence.
- [x] Ensure deterministic run for identical inputs.
- [ ] Complete full physically faithful ACP constitutive objective (material-law fidelity beyond current staged edge/cell surrogate objective shaping).

### Acceptance

- [x] `acp_energy` runs end-to-end on supported surfaces.
- [x] Result includes termination reason and diagnostics.
- [x] Repeated runs with same inputs are numerically stable/deterministic.
- [x] UD anisotropy diagnostics respond monotonically to `ud_coefficient` under fixed geometry/direction.
- [x] Pre-shear sign convention is exercised and consistent across positive/negative bias edge families under fixed geometry/direction.
- [x] Cell-level shear/fiber-angle diagnostics are reported and direction-sensitive on canonical planar grids.
- [ ] Constitutive behavior matches full ACP-fidelity target.

---

## Issue 3 — Integration cutover in adapter + shell execution path

**Title:** Move `CompositeShell` production path to ACP energy mode

**Depends on:** Issue 2

**Status:** ✅ Complete

### Scope

- Use ACP mode from `CompositeShell` execute path.
- Remove hardcoded legacy assumptions in adapter.
- Clarify `MaxLength` vs `mesh_size` semantics.

### Files

- `freecad/Composites/features/CompositeShell.py`
- `freecad/Composites/tools/fishnet_draper.py`

### Checklist

- [x] Replace hardcoded seed/default assumptions in adapter.
- [x] Ensure all active object parameters flow into solver params.
- [x] Resolve `MaxLength` ambiguity in current ACP staging behavior.
- [x] Set production default mode to ACP path (`acp_energy`).
- [x] Remove legacy mode from production path and UI/API contracts.

### Acceptance

- [x] Recompute path in `CompositeShell` uses ACP mode by default.
- [x] Legacy mode is removed from production code paths.
- [x] No consumer API breakage in feature proxy methods.

---

## Issue 4 — Validation suite (canonical + invariants, no legacy parity)

**Title:** Replace parity tests with physics/invariant validation suite

**Depends on:** Issue 2

**Status:** ✅ Complete

### Scope

- Do not compare to old WIP results.
- Validate by canonical geometry behavior + numerical invariants.

### Files

- `freecad/Composites/compositestests/test_fishnet_native.py`
- `freecad/Composites/compositestests/test_integration_freecad.py`
- `freecad/Composites/compositestests/test_shapes.py`
- `freecad/Composites/compositestests/plotting.py`

### Checklist

- [x] Add canonical geometry tests:
  - [x] plane
  - [x] cylinder (aligned)
  - [x] double curvature (Krogh analytical helper + B-spline integration face)
  - [x] trimmed/open boundary case
- [x] Add invariants:
  - [x] no NaN/inf
  - [x] no invalid/folded cells
  - [x] edge-length error bounded by mode/tolerance
  - [x] boundary loops valid for open/closed support geometry
  - [x] deterministic repeatability
- [x] Add convergence diagnostics checks.
- [x] Add sensitivity checks (seed, direction, UD coefficient).
- [x] Remove/disable tests that assume legacy output is ground truth.
- [x] Add explicit v2 tests that jointly enforce spacing quality **and minimum coverage**.

### Acceptance

- [x] Full suite passes without legacy baseline dependency.
- [x] Failures produce actionable diagnostics.
- [x] v2 spacing+coverage acceptance thresholds locked and enforced.

---

## Issue 5 — Default switch + cleanup

**Title:** Promote ACP energy mode to default and remove legacy/fallback paths

**Depends on:** Issue 4

**Status:** ✅ Complete

### Scope

- Make ACP mode (`acp_energy`) default in production path.
- Remove legacy algorithm and fallback-only compatibility paths.

### Files

- `freecad/Composites/features/CompositeShell.py`
- `freecad/Composites/tools/fishnet_draper.py`
- docs/changelog/handover notes as needed

### Checklist

- [x] Switch default solver mode to ACP path (`acp_energy`).
- [x] Remove legacy algorithm (`legacy_fishnet`) from code/UI/tests.
- [x] Remove algorithm aliases (`acp_energy_v1`, `acp_energy_v2_surface_spacing`) in favor of `acp_energy` + `acp_strategy`.
- [x] Remove pure-Python solver fallback (`fishnet/python_solver.py`) and enforce native-only backend.
- [x] Simplify current-node solver policy to SphereSurface-only (remove alternates).

### Acceptance

- [x] New mode is default and stable.
- [x] Legacy/fallback paths are removed from production code.

---

## Issue 6 — ACP v2 on-surface spacing coverage expansion

**Title:** Increase v2 coverage while preserving near-constant 3D/on-surface spacing

**Depends on:** Issues 2 and 4

**Status:** ✅ Complete

### Scope

- Keep `acp_strategy=surface_spacing` strict edge-length behavior.
- Improve frontier growth/activation so v2 does not remain a small strict patch on curved cones.
- Add diagnostics for spacing-vs-coverage tradeoff.

### Files

- `freecad/Composites/fishnet/fishnet_geometry_sampling.cpp`
- `freecad/Composites/fishnet/fishnet_algorithm.cpp`
- `freecad/Composites/fishnet/fishnet_diagnostics_result.cpp`
- `freecad/Composites/compositestests/test_fishnet_native.py`

### Checklist

- [x] Expand frontier/growth logic for v2 on curved supports.
- [x] Add coverage diagnostics (`coverage_point_ratio`, active-node ratio, frontier accept stats, candidate/selected quad stats, `surface_spacing_growth_stall_reason`).
- [x] Add assertions on curved truncated cone: low edge spread + **raised** minimum quad coverage.
- [x] Add equivalent diagnostics/coverage assertions on the double-curved Krogh mesh helper.

### Acceptance

- [x] v2 keeps near-constant 3D edge lengths (current strict mode).
- [x] v2 achieves materially improved coverage over current strict patch behavior.

---

## Issue 7 — 🔴 High-priority flattened-topology growth correction (KinDrape behavior)

**Title:** Replace fixed-cardinality flattened grid with demand-driven adaptive mesh growth

**Depends on:** Issues 2 and 6

**Status:** 🟡 High priority / in progress (default adaptive growth enabled; variable-cardinality topology still open)

### Scope

- Remove fixed regular-grid cardinality assumptions from sampling/layout growth path.
- Implement demand-driven node/cell creation so flattened mesh grows as required by geometry.
- Support variable column counts across rows/rings for cone/frustum-like circumference changes.
- Preserve deterministic behavior and actionable diagnostics.

### Files

- `freecad/Composites/fishnet/fishnet_geometry_sampling.cpp`
- `freecad/Composites/fishnet/fishnet_algorithm.cpp`
- `freecad/Composites/fishnet/fishnet_relaxation_objective.cpp`
- `freecad/Composites/fishnet/fishnet_diagnostics_result.cpp`
- `freecad/Composites/compositestests/test_fishnet_native.py`

### Checklist

- [x] Replace preallocated full-grid initialization with on-demand growth.
- [ ] Allow adaptive row/ring cardinality (variable columns) in flattened mesh topology.
- [ ] Add transition/stitching logic for cardinality changes while preserving valid cells.
- [ ] Add diagnostics for adaptation behavior (per-row/per-ring counts, transition stats).
- [ ] Add canonical cone/frustum tests that assert adaptive growth (not forced equal-count rows).

### Acceptance

- [ ] Flattened drape mesh grows/adapts as required (KinDrape-style behavior).
- [ ] Cone/frustum runs show variable column counts where circumference changes demand it.
- [ ] Determinism and diagnostic quality remain acceptable.

---

## Suggested next slices (updated)

### Slice A (🔴 high priority)

- Issue 7 flattened-topology adaptive growth correction (KinDrape-style behavior)

### Slice B

- ACP constitutive-fidelity deepening (Issue 2 remaining objective physics)

### Slice C

- Documentation/prompt cleanup to remove stale fallback/legacy references
