# ACP Energy Draping Migration — Issue Breakdown

This is an implementation checklist derived from:

- `docs/superpowers/plans/2026-05-04-acp-energy-draping-migration-plan.md`

Local build note: FreeCAD build path for local extension/testing work is `~/opt/FreeCAD/build/pixi-debug`.

---

## Issue 1 — Parameter contract + plumbing

**Title:** Define ACP-style draping parameter contract and wire through model/UI

**Depends on:** none

### Scope

- Introduce/normalize draping parameters in production path:
  - `seed_point`
  - `auto_draping_direction`
  - `draping_direction`
  - `mesh_size`
  - `material_model` (`woven` / `ud`)
  - `ud_coefficient`
  - `thickness_correction`
- Add temporary algorithm selector:
  - `acp_energy_v1`
  - `legacy_fishnet`

### Files

- `freecad/Composites/features/CompositeShell.py`
- `freecad/Composites/tools/fishnet_draper.py`
- `freecad/Composites/taskpanels/task_fishnet_drape.py`
- `freecad/Composites/resources/ui/FishnetDrape.ui`

### Checklist

- [ ] Add document properties for missing ACP-style parameters.
- [ ] Keep current properties backward compatible where possible.
- [ ] Pass parameters from task panel to object properties.
- [ ] Pass properties from object into solver call.
- [ ] Add algorithm mode flag with safe default for transition.
- [ ] Ensure recompute triggered when new properties change.

### Acceptance

- [ ] Parameters are editable in UI and persisted on object.
- [ ] Solver receives the same values configured in UI.
- [ ] Existing adapter methods still work (`get_tex_coords`, `get_boundaries`, `get_lcs`, `strains`).

---

## Issue 2 — Native solver core (ACP energy propagation)

**Title:** Implement `acp_energy_v1` propagation + energy objective in native solver

**Depends on:** Issue 1 (parameter contract)

### Scope

- Add separate ACP-style solve path in native backend.
- Keep legacy path available.
- Enforce deterministic propagation order and explicit termination states.

### Files

- `freecad/Composites/_fishnet.cpp`
- `freecad/Composites/_fishnet.py` (fallback shape only if needed)

### Checklist

- [ ] Add mode dispatch in native `solve` entrypoint.
- [ ] Implement ACP-style propagation ordering (primary, orthogonal, fill).
- [ ] Implement woven objective (shear energy).
- [ ] Implement UD objective (shear + transverse extension penalty via `ud_coefficient`).
- [ ] Add clear convergence/termination reasons (`converged`, `max_iterations`, `infeasible`).
- [ ] Return structured diagnostics for failures/non-convergence.
- [ ] Ensure deterministic run for identical inputs.

### Acceptance

- [ ] `acp_energy_v1` runs end-to-end on supported surfaces.
- [ ] Result includes termination reason and diagnostics.
- [ ] Repeated runs with same inputs are numerically stable/deterministic.

---

## Issue 3 — Integration cutover in adapter + shell execution path

**Title:** Move `CompositeShell` production path to ACP energy mode (with fallback)

**Depends on:** Issue 2

### Scope

- Use ACP mode from `CompositeShell` execute path.
- Remove hardcoded legacy assumptions in adapter.
- Clarify `MaxLength` vs `mesh_size` semantics.

### Files

- `freecad/Composites/features/CompositeShell.py`
- `freecad/Composites/tools/fishnet_draper.py`

### Checklist

- [ ] Replace hardcoded seed/default assumptions in adapter.
- [ ] Ensure all active object parameters flow into solver params.
- [ ] Resolve `MaxLength` ambiguity (map, deprecate, or remove).
- [ ] Set production default mode to new solver only after validation gate.
- [ ] Keep legacy mode explicit and non-default during transition.

### Acceptance

- [ ] Recompute path in `CompositeShell` uses new mode when selected.
- [ ] Legacy mode remains callable for temporary fallback.
- [ ] No consumer API breakage in feature proxy methods.

---

## Issue 4 — Validation suite (canonical + invariants, no legacy parity)

**Title:** Replace parity tests with physics/invariant validation suite

**Depends on:** Issue 2 (core behavior available)

### Scope

- Do not compare to old WIP results.
- Validate by canonical geometry behavior + numerical invariants.

### Files

- `freecad/Composites/compositestests/test_fishnet_native.py`
- `freecad/Composites/compositestests/test_integration_freecad.py`
- (optional plotting helpers already present)

### Checklist

- [ ] Add canonical geometry tests:
  - [ ] plane
  - [ ] cylinder (aligned)
  - [ ] hemisphere/double curvature
  - [ ] trimmed boundary case
- [ ] Add invariants:
  - [ ] no NaN/inf
  - [ ] no invalid/folded cells
  - [ ] edge length error bounded
  - [ ] boundary loops valid
  - [ ] deterministic repeatability
- [ ] Add convergence diagnostics checks.
- [ ] Add sensitivity checks (seed, direction, UD coefficient).
- [ ] Remove/disable tests that assume legacy output is ground truth.

### Acceptance

- [ ] Full suite passes without any legacy baseline dependency.
- [ ] Failures produce actionable diagnostics.

---

## Issue 5 — Default switch + cleanup

**Title:** Promote ACP energy mode to default and deprecate legacy path

**Depends on:** Issue 4 (validation green)

### Scope

- Make `acp_energy_v1` default in production path.
- Keep fallback only as temporary compatibility option.

### Files

- `freecad/Composites/features/CompositeShell.py`
- `freecad/Composites/tools/fishnet_draper.py`
- docs/changelog/handover notes as needed

### Checklist

- [ ] Switch default solver mode to `acp_energy_v1`.
- [ ] Mark legacy mode as deprecated in comments/docs.
- [ ] Add migration note for parameter semantics.
- [ ] Add removal target (version/date) for legacy path.

### Acceptance

- [ ] New mode is default and stable.
- [ ] Legacy path is documented as temporary fallback only.

---

## Suggested PR slicing

### PR 1

- Issue 1 only (parameter contract + UI plumbing)

### PR 2

- Issue 2 core woven path

### PR 3

- Issue 2 UD + thickness correction behavior

### PR 4

- Issue 3 integration cutover

### PR 5

- Issue 4 validation suite

### PR 6

- Issue 5 default switch + cleanup
