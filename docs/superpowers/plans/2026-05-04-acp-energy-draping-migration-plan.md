# ACP Energy-Algorithm Draping Migration Plan

## Context

The current WIP fishnet draping backend in this repository is not producing acceptable results. We will migrate the production draping path to an ACP-style **energy + propagation** algorithm and explicitly avoid using current WIP outputs as a validation baseline.

This plan is updated using details extracted from:
- Krogh et al. (2021), *A simple MATLAB draping code for fiber-reinforced composites with application to optimization of manufacturing process parameters*, DOI: `10.1007/s00158-021-02925-z`.

### Local build note

- FreeCAD build path for local extension/testing work: `~/opt/FreeCAD/build/pixi-debug`

## Status update (2026-05-04, post-v2 spacing report)

### Completed since initial draft

- ACP parameter contract/plumbing landed in model, adapter, and UI.
- Native solver architecture is now split into interface + multiple algorithm translation units (no `.inc` implementation fragments).
- `acp_energy_v1` staged propagation/objective path is integrated with deterministic diagnostics and explicit stop reasons.
- Curved-only truncated half-cone geometry (small radius = 80% of large radius) is now the main cone validation shape.
- `acp_energy_v2_surface_spacing` mode is implemented and now enforces near-constant 3D edge lengths on the truncated curved cone test scenario (with reduced patch coverage tradeoff).
- Added v2 coverage diagnostics (`coverage_point_ratio`, active-node ratio, frontier acceptance, candidate-vs-selected quad ratios) in native + fallback metadata.
- Added native test assertions for v2 diagnostics on truncated cone and the Krogh double-curved mesh helper.
- Native/integration suites are green locally (`FreeCADCmd`), and plots/report were regenerated under:
  - `artifacts/acp-v2-spacing-report-2026-05-04/`

### Important test-asset note

There is now explicit **double-curved mesh coverage** for validation:

- Analytical mesh helper: `freecad/Composites/compositestests/test_shapes.py::make_krogh_double_curved_mesh`
- Integration-shape helper: `freecad/Composites/compositestests/test_shapes.py::make_krogh_double_curved_bspline_face`
- Native usage: `test_fishnet_native.py::test_krogh_double_curved_analytical_mesh_helper_solves`
- Integration usage: `test_integration_freecad.py::test_composite_shell_fishnet_krogh_double_curved_bspline_creates_ready_shell`

### Current gap

- v2 achieves strong spacing uniformity but currently grows a smaller strict patch than desired.
- Next implementation step is improving **coverage expansion while preserving near-constant on-surface spacing**.

## Goals

1. Replace legacy heuristic propagation behavior with a deterministic ACP-style draping solve.
2. Expose ACP-like controls in the FreeCAD object model and UI:
   - Seed point
   - Draping direction (auto/user)
   - Mesh size
   - Material model (woven / UD)
   - UD coefficient
   - Thickness correction toggle
   - **Pre-shear** (new, from Krogh et al. extension)
3. Keep existing downstream adapters (`get_tex_coords`, `get_boundaries`, `get_lcs`, strains access) stable for workbench consumers.
4. Validate against physics/algorithm invariants instead of legacy parity.

## Non-goals

- Matching old WIP numerical output.
- Full UI redesign beyond necessary parameter exposure.
- Multi-face stitching sophistication beyond stable first implementation.

## Paper-derived algorithm details to adopt

### Core kinematic model

Represent cloth as a pin-jointed cell lattice with:
- Inextensible edges (edge length fixed to discretization `d`)
- Free in-plane rotation at nodes
- No tow slip in baseline model

This gives a constrained geometric solve where fabric deformation is mainly captured as **shear angle** at cell corners.

### 3-step propagation structure (explicit)

1. **Step 1 (seed + initial heading):**
   - Place origin node at seed point.
   - Solve for second node at distance `d` along initial draping angle.
2. **Step 2 (generator arms):**
   - For each generator cell, with vertices `V1,V2` known and `V3,V4` unknown, solve:
     - Objective: minimize cell shear metric (or deviation from target pre-shear)
     - Constraints: all three unknown edges satisfy length `d`
   - This approximates geodesic-like generator paths by minimizing tangential distortion.
3. **Step 3 (constrained fill):**
   - For remaining cells, solve `V3` from two distance equations (`|V3-V2|=d`, `|V4-V3|=d`) using good initial guess from opposite edge.

### Shear conventions

- Baseline woven objective: minimize sum of absolute corner shear in generator cells.
- Add signed shear bookkeeping (quadrant-aware) so pre-shear and asymmetric materials are possible.
- Keep both signed and absolute shear available in diagnostics.

### Optimization-ready objective hooks

From the paper’s process optimization setup:
- Support p-norm aggregation (high `p`, e.g., 12) over field quantities.
- Default objective components to support:
  - Shear magnitude
  - Fiber-angle deviation from nominal direction
- Keep this objective framework optional (for process parameter optimization mode, not baseline deterministic drape call).

### Material behavior mapping guidance

- **Woven:** pin-jointed kinematic shear-dominated behavior.
- **UD/NCF path:** keep ACP energy penalty terms (`ud_coefficient`) and allow future extension where positive/negative shear asymmetry can matter.

## Implementation Plan

## Phase 1 — Interface and parameter contract

### Tasks

- Add a versioned solver mode:
  - `acp_energy_v1` (new default target)
- Define and normalize solver input schema in native + Python layers:
  - `seed_point`
  - `auto_draping_direction`
  - `draping_direction`
  - `mesh_size`
  - `material_model`
  - `ud_coefficient`
  - `thickness_correction`
  - `pre_shear_deg` (new)
- Define output/diagnostic schema:
  - per-cell shear (signed + absolute)
  - edge-length residual stats
  - termination reason
  - iteration/evaluation counters
- Wire parameters through:
  - `CompositeShell` properties
  - `fishnet_draper.py` adapter
  - task panel UI

### Acceptance criteria

- New parameters are visible, persisted, and passed to solver.
- Existing public adapter methods still function.
- Diagnostics object is always present for success/failure.

## Phase 2 — Native solver migration (core algorithm)

### Tasks

- Implement explicit Step 1/2/3 propagation loop in `_fishnet.cpp` under `acp_energy_v1`.
- Implement Step 2 constrained local objective:
  - Woven baseline objective: minimize corner shear sum in generator cells.
  - If `pre_shear_deg != 0`, minimize deviation from target pre-shear in generator cells.
- Implement Step 3 two-constraint placement with robust initial guess strategy.
- Separate core drape solve from atlas/chart postprocessing.
- Implement explicit convergence and stop conditions:
  - converged
  - max iterations/evaluations
  - infeasible constraints

### Acceptance criteria

- Deterministic solve for identical inputs.
- Clear termination reason always returned.
- No silent partial-success states.

## Phase 3 — Surface/geodesic handling and robustness

### Tasks

- Replace paper’s simplified `z = F(x,y)` assumption with FreeCAD-native surface evaluation/projection path.
- Add robust projection/inside checks for trimmed faces.
- Keep tangent-based local direction updates bounded to avoid foldovers.
- Add hard guards for impossible cells (infeasible geometry) and bubble up explicit diagnostics.

### Acceptance criteria

- Solver works on general FreeCAD faces (not only graph surfaces).
- Trimmed boundaries either complete stably or fail explicitly with actionable diagnostics.

## Phase 4 — FreeCAD integration cutover

### Tasks

- Update `fishnet_draper.py` to remove hardcoded solve assumptions.
- Ensure `MaxLength` / mesh-size semantics are consistent (either fully used or removed in favor of mesh size).
- Extend `CompositeShell` draping properties and execute path to use the new contract.
- Update `FishnetDrape.ui` and task panel binding for new controls (including pre-shear).

### Acceptance criteria

- User can configure ACP-style controls in UI.
- `CompositeShell` recompute path uses new algorithm mode.
- Legacy mode remains available behind explicit flag during transition.

## Phase 5 — Validation and testing (no legacy parity)

### Validation policy

Do **not** compare against existing WIP results.
Use geometry-based expected behavior + numerical invariants.

### Test suite additions

#### Canonical geometry tests

- Plane face: near-zero shear expectation.
- Single-curved surface (paper analog): near-zero shear across field.
- Cylinder aligned drape: low/structured shear behavior.
- Hemisphere centered seed: symmetric pattern and geodesic-consistent generator trend.
- Hemisphere off-center seed: generator paths remain geodesic-like and asymmetry is physical.
- Double curvature: shear increase away from favorable seed/direction combinations.
  - Implemented helpers/tests now include Krogh analytical double-curved mesh and B-spline face integration coverage.
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

#### Sensitivity and optimization-hook tests

- Seed point perturbation gives smooth field changes.
- Direction rotation produces expected rotation in shear pattern.
- UD coefficient sweep changes transverse behavior monotonically.
- Pre-shear sign convention is consistent across quadrants.
- p-norm objective hook returns consistent ranking across known scenarios.

### Acceptance criteria

- Tests pass for all canonical geometries and invariants.
- No dependency on old WIP output files/data.

## Phase 6 — Default switch and cleanup

## Phase 7 — ACP v2 on-surface spacing coverage expansion

### Tasks

- Improve frontier growth/activation in `acp_energy_v2_surface_spacing` so coverage expands beyond the current strict seed patch.
- Keep near-constant 3D/on-surface edge-length objective active while growing coverage.
- Add diagnostics for coverage quality (coverage ratio, growth stall reason, spacing error summary).
- Add targeted tests that assert both spacing quality and minimum coverage on curved-only truncated cone and double-curved meshes.

### Acceptance criteria

- v2 keeps low 3D edge-length spread while producing materially higher quad coverage than current strict patch behavior.
- Diagnostics clearly report spacing-vs-coverage tradeoffs.


### Tasks

- Switch default mode to `acp_energy_v1` after validation.
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
- **Signed-shear bookkeeping errors**
  - Mitigation: dedicated quadrant/sign tests and invariant checks.

## Deliverables

1. ACP-style draping solver mode in native backend.
2. FreeCAD-facing parameterized draping controls (including pre-shear).
3. Updated adapter integration with stable public methods.
4. New test suite based on invariants and canonical behavior.
5. Documented deprecation path for legacy mode.

## Definition of Done

- `CompositeShell` uses ACP-style draping by default.
- Canonical geometry + invariant tests pass.
- No tests rely on old WIP output parity.
- UI and API parameters are coherent and documented.
- Diagnostic contract is present and consumed by integration tests.
