# ACP Energy-Algorithm Draping Migration Plan

## Context

The current WIP fishnet draping backend in this repository is not producing acceptable results. We will migrate the production draping path to an ACP-style **energy + propagation** algorithm and explicitly avoid using current WIP outputs as a validation baseline.

### Local build note

- FreeCAD build path for local extension/testing work: `~/opt/FreeCAD/build/pixi-debug`

## Goals

1. Replace legacy heuristic propagation behavior with a deterministic ACP-style draping solve.
2. Expose ACP-like controls in the FreeCAD object model and UI:
   - Seed point
   - Draping direction (auto/user)
   - Mesh size
   - Material model (woven / UD)
   - UD coefficient
   - Thickness correction toggle
3. Keep existing downstream adapters (`get_tex_coords`, `get_boundaries`, `get_lcs`, strains access) stable for workbench consumers.
4. Validate against physics/algorithm invariants instead of legacy parity.

## Non-goals

- Matching old WIP numerical output.
- Full UI redesign beyond necessary parameter exposure.
- Multi-face stitching sophistication beyond stable first implementation.

## Target Algorithm (ACP-style)

### Propagation model

- Build draping lattice from seed point + draping direction.
- Propagate in ordered stages:
  1. primary draping direction
  2. orthogonal direction
  3. remaining fill cells

### Material models

- **Woven**: inextensible warp/weft bars, pin-jointed rotation.
- **UD**: inextensible along fiber, transverse compliance controlled by `ud_coefficient`.

### Solve objective

- Woven: shear-energy minimization.
- UD: weighted objective combining shear + transverse extension penalty.

### Optional correction

- Thickness correction from local area change after draping.

## Implementation Plan

## Phase 1 — Interface and parameter contract

### Tasks

- Add a versioned solver mode:
  - `acp_energy_v1` (new default target)
  - `legacy_fishnet` (temporary fallback)
- Define and normalize solver input schema in native + Python layers:
  - `seed_point`
  - `auto_draping_direction`
  - `draping_direction`
  - `mesh_size`
  - `material_model`
  - `ud_coefficient`
  - `thickness_correction`
- Wire parameters through:
  - `CompositeShell` properties
  - `fishnet_draper.py` adapter
  - task panel UI

### Acceptance criteria

- New parameters are visible, persisted, and passed to solver.
- Existing public adapter methods still function.

## Phase 2 — Native solver migration (core algorithm)

### Tasks

- Implement ACP-style propagation loop in `_fishnet.cpp` under `acp_energy_v1`.
- Separate core drape solve from atlas/chart postprocessing.
- Implement explicit convergence and stop conditions:
  - converged
  - max iterations
  - infeasible constraints
- Return structured diagnostics for non-converged/infeasible cases.

### Acceptance criteria

- Deterministic solve for identical inputs.
- Clear termination reason always returned.
- No silent partial-success states.

## Phase 3 — FreeCAD integration cutover

### Tasks

- Update `fishnet_draper.py` to remove hardcoded solve assumptions.
- Ensure `MaxLength` / mesh-size semantics are consistent (either fully used or removed in favor of mesh size).
- Extend `CompositeShell` draping properties and execute path to use the new contract.
- Update `FishnetDrape.ui` and task panel binding for new controls.

### Acceptance criteria

- User can configure ACP-style controls in UI.
- `CompositeShell` recompute path uses new algorithm mode.
- Legacy mode remains available behind explicit flag during transition.

## Phase 4 — Validation and testing (no legacy parity)

### Validation policy

Do **not** compare against existing WIP results.
Use geometry-based expected behavior + numerical invariants.

### Test suite additions

#### Canonical geometry tests

- Plane face: near-zero shear expectation.
- Cylinder aligned drape: low/structured shear behavior.
- Hemisphere/double curvature: shear increase away from seed.
- Trimmed boundary case: stable completion or explicit infeasible diagnostics.

#### Invariant tests

- No NaN/inf values in outputs.
- No invalid/inside-out cell orientation (unless explicitly marked).
- Edge-length/inextensibility error bounded by tolerance.
- Boundary loops valid and non-self-intersecting.
- Determinism under repeated runs.

#### Convergence diagnostics tests

- Residual trend is non-divergent and termination reason is set.
- Infeasible setups return explicit failure diagnostics.

#### Sensitivity tests

- Seed point perturbation gives smooth field changes.
- Direction rotation produces expected rotation in shear pattern.
- UD coefficient sweep changes transverse behavior monotonically.

### Acceptance criteria

- Tests pass for all canonical geometries and invariants.
- No dependency on old WIP output files/data.

## Phase 5 — Default switch and cleanup

### Tasks

- Switch default mode to `acp_energy_v1` after validation.
- Keep `legacy_fishnet` only as temporary fallback for one transition window.
- Remove dead code paths and outdated UI hints after acceptance.

### Acceptance criteria

- New mode is default in production path.
- Fallback documented and time-boxed for removal.

## File-level Work Plan

- `freecad/Composites/_fishnet.cpp`
- `freecad/Composites/_fishnet.py` (fallback parity behavior only where needed)
- `freecad/Composites/tools/fishnet_draper.py`
- `freecad/Composites/features/CompositeShell.py`
- `freecad/Composites/resources/ui/FishnetDrape.ui`
- `freecad/Composites/taskpanels/task_fishnet_drape.py`
- `freecad/Composites/compositestests/test_fishnet_native.py`
- `freecad/Composites/compositestests/test_integration_freecad.py`

## Risks and Mitigations

- **Trimmed-surface projection instability**
  - Mitigation: strict inside checks, tangent-plane update limiting, robust fallbacks.
- **Numerical folding/shear blow-up on high curvature**
  - Mitigation: hard local guards + infeasible diagnostics.
- **Parameter confusion (`MaxLength` vs mesh size)**
  - Mitigation: consolidate semantics and deprecate ambiguous controls.
- **Regression in downstream consumers**
  - Mitigation: keep adapter API stable and covered by integration tests.

## Deliverables

1. ACP-style draping solver mode in native backend.
2. FreeCAD-facing parameterized draping controls.
3. Updated adapter integration with stable public methods.
4. New test suite based on invariants and canonical behavior.
5. Documented deprecation path for legacy mode.

## Definition of Done

- `CompositeShell` uses ACP-style draping by default.
- Canonical geometry + invariant tests pass.
- No tests rely on old WIP output parity.
- UI and API parameters are coherent and documented.
