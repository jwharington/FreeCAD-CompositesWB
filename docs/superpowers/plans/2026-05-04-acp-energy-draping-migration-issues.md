# ACP Energy Draping Migration — Issue Breakdown

This checklist tracks actual implementation status against:

- `docs/superpowers/plans/2026-05-04-acp-energy-draping-migration-plan.md`

Local build note: FreeCAD build path for local extension/testing work is `~/opt/FreeCAD/build/pixi-debug`.

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
- Add algorithm selector:
  - `acp_energy_v1`
  - `acp_energy_v2_surface_spacing` (new staged mode)

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

**Title:** Implement `acp_energy_v1` propagation + energy objective in native solver

**Depends on:** Issue 1

**Status:** 🟡 Substantially complete (staged ACP objective), constitutive fidelity still open

### Scope

- Add separate ACP-style solve path in native backend.
- Keep legacy path available.
- Enforce deterministic propagation order and explicit termination states.

### Files

- `freecad/Composites/_fishnet.cpp` (interface only)
- `freecad/Composites/_fishnet_algorithm.cpp`
- `freecad/Composites/_fishnet_algorithm.hpp`
- `freecad/Composites/_fishnet_algorithm_types.hpp`
- `freecad/Composites/_fishnet_algorithm_sections.hpp`
- `freecad/Composites/_fishnet_relaxation_objective.cpp`
- `freecad/Composites/_fishnet_geometry_sampling.cpp`
- `freecad/Composites/_fishnet_diagnostics_result.cpp`
- `freecad/Composites/_fishnet.py` (fallback parity)

### Checklist

- [x] Add mode dispatch in native `solve` entrypoint.
- [x] Implement ACP-style propagation ordering (primary, orthogonal, fill).
- [x] Implement woven objective (staged shear/spacing objective).
- [x] Implement UD objective shaping (`ud_coefficient`).
- [x] Add clear convergence/termination reasons (`converged`, `max_iterations`, `infeasible`).
- [x] Return structured diagnostics for failures/non-convergence.
- [x] Ensure deterministic run for identical inputs.
- [ ] Complete full physically faithful ACP constitutive objective.

### Acceptance

- [x] `acp_energy_v1` runs end-to-end on supported surfaces.
- [x] Result includes termination reason and diagnostics.
- [x] Repeated runs with same inputs are numerically stable/deterministic.
- [ ] Constitutive behavior matches full ACP-fidelity target.

---

## Issue 3 — Integration cutover in adapter + shell execution path

**Title:** Move `CompositeShell` production path to ACP energy mode (with fallback)

**Depends on:** Issue 2

**Status:** 🟡 Mostly complete; default/deprecation switch pending

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
- [ ] Set production default mode to new solver only after validation gate.
- [x] Keep legacy mode explicit and non-default during transition.

### Acceptance

- [x] Recompute path in `CompositeShell` uses new mode when selected.
- [x] Legacy mode remains callable for temporary fallback.
- [x] No consumer API breakage in feature proxy methods.

---

## Issue 4 — Validation suite (canonical + invariants, no legacy parity)

**Title:** Replace parity tests with physics/invariant validation suite

**Depends on:** Issue 2

**Status:** 🟡 Core done; extend with stronger v2 spacing+coverage assertions

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
- [ ] Add explicit v2 tests that jointly enforce spacing quality **and minimum coverage**.

### Acceptance

- [x] Full suite passes without legacy baseline dependency.
- [x] Failures produce actionable diagnostics.
- [ ] v2 spacing+coverage acceptance thresholds locked and enforced.

---

## Issue 5 — Default switch + cleanup

**Title:** Promote ACP energy mode to default and deprecate legacy path

**Depends on:** Issue 4

**Status:** ⏳ Pending

### Scope

- Make `acp_energy_v1` (or successor) default in production path.
- Keep fallback only as temporary compatibility option.

### Files

- `freecad/Composites/features/CompositeShell.py`
- `freecad/Composites/tools/fishnet_draper.py`
- docs/changelog/handover notes as needed

### Checklist

- [ ] Switch default solver mode to ACP path after final validation gate.
- [ ] Mark legacy mode as deprecated in comments/docs.
- [ ] Add migration note for parameter semantics.
- [ ] Add removal target (version/date) for legacy path.

### Acceptance

- [ ] New mode is default and stable.
- [ ] Legacy path is documented as temporary fallback only.

---

## Issue 6 — ACP v2 on-surface spacing coverage expansion

**Title:** Increase v2 coverage while preserving near-constant 3D/on-surface spacing

**Depends on:** Issues 2 and 4

**Status:** 🚧 Active

### Scope

- Keep `acp_energy_v2_surface_spacing` strict edge-length behavior.
- Improve frontier growth/activation so v2 does not remain a small strict patch on curved cones.
- Add diagnostics for spacing-vs-coverage tradeoff.

### Files

- `freecad/Composites/_fishnet_geometry_sampling.cpp`
- `freecad/Composites/_fishnet_algorithm.cpp`
- `freecad/Composites/_fishnet_diagnostics_result.cpp`
- `freecad/Composites/compositestests/test_fishnet_native.py`

### Checklist

- [ ] Expand frontier/growth logic for v2 on curved supports.
- [x] Add coverage diagnostics (`coverage_point_ratio`, active-node ratio, frontier accept stats, candidate/selected quad stats, `surface_spacing_growth_stall_reason`).
- [ ] Add assertions on curved truncated cone: low edge spread + **raised** minimum quad coverage (currently still small strict patch).
- [x] Add equivalent diagnostics/coverage assertions on the double-curved Krogh mesh helper.

### Acceptance

- [x] v2 keeps near-constant 3D edge lengths (current strict mode).
- [ ] v2 achieves materially improved coverage over current strict patch behavior.

---

## Suggested PR slicing (updated)

### PR A

- Issue 6 spacing-preserving coverage expansion

### PR B

- Issue 6 diagnostics + tests (cone + double-curved)

### PR C

- Issue 5 default switch/deprecation once Issue 6 is green
