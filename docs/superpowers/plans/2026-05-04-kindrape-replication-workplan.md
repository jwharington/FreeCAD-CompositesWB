# KinDrape Replication Completion Workplan

## Objective

Finish replication of KinDrape-style behavior in the native `acp_energy` production path, with validation against algorithmic/physical invariants and explicit KinDrape reference behavior on canonical geometries.

## Scope

### In scope
- Full Step 1/2/3 KinDrape-style propagation semantics.
- Generator-cell Newton-Raphson (NR) local shear minimization.
- Pre-shear integration in propagation (not only edge-weight shaping).
- True variable-cardinality topology (row/ring split/merge with stitching transitions).
- Per-cell and per-iteration diagnostics needed to inspect/verify KinDrape behavior.
- Canonical validation suite including KinDrape reference comparison harness.

### Out of scope (for this plan)
- New UI redesign beyond required parameter exposure.
- Multi-layer laminate physics beyond current single-layer drape scope.
- GPU acceleration/performance tuning as a primary goal.

## Current gaps to close

1. Propagation is still UV-grid growth, not explicit Step 1/2/3 arm/quadrant sequencing.
2. No generator NR solve minimizing local shear objective during on-surface placement.
3. `pre_shear_deg` is currently objective-shaping in ACP edge/cell terms, not a Step-2 kinematic target in propagation.
4. Topology is still fundamentally fixed `divisions x divisions` with pruning; variable-cardinality transitions are not represented as first-class topology events.
5. Limited diagnostic observability for transition events and per-cell history.
6. No reference-equivalence harness against KinDrape canonical cases.
7. Frontier/node growth behavior is undefined when only one neighbor is available (current update path generally requires two).
8. Boundary/hole dead-zone recovery behavior is not specified or validated.
9. Cross-face seam continuity is not yet encoded as an explicit contract/invariant for adaptive scheduling.
10. Determinism checks are not explicit in the KinDrape reference harness (same input -> same stage trace/topology transitions).

## Success criteria (Definition of Done)

- Cone/frustum runs exhibit explicit variable ring/row cardinality with valid split/merge stitching transitions.
- Propagation path executes deterministic Step 1/2/3 scheduling.
- Generator NR local objective converges robustly and decreases per-cell target mismatch.
- Pre-shear materially changes generator/shear outcomes in signed-consistent way.
- Diagnostics include per-iteration and per-transition histories sufficient for debugging.
- One-neighbor frontier policy is explicit and tested (wait/defer vs fallback placement), with no silent topology corruption.
- Boundary/hole regions do not silently stall: dead-zones are either recovered or explicitly diagnosed.
- Cross-face seam continuity invariants hold (orientation + layout continuity across adjacent faces).
- Canonical KinDrape reference-comparison suite passes agreed thresholds.
- Reference harness includes determinism checks for stage traces and transition events.
- Existing acceptance remains green (native + integration), with no tolerance loosening.

---

## Work breakdown

## Phase 1 — Topology kernel for variable-cardinality growth (P0)

### Deliverable
A topology model that can represent changing column counts between adjacent rows/rings and emit valid quads/triangles with explicit transition metadata.

### Tasks
- Introduce adaptive topology primitives:
  - `NodeId`, `RowId/RingId`, `CellId`, and neighbor connectivity independent of UV matrix indexing.
- Replace fixed-grid-only emit path:
  - decouple topology emission from `append_grid_topology(...)` style rectangular assumptions.
- Implement split/merge transition templates:
  - `N -> N+1`, `N -> N-1`, and equivalent seam-safe stitching rules.
- Preserve deterministic ordering for reproducibility.
- Add transition-aware boundary loop generation.

### Candidate files
- `freecad/Composites/fishnet/fishnet_geometry_sampling.cpp`
- `freecad/Composites/fishnet/fishnet_sampling_api.hpp`
- `freecad/Composites/fishnet/fishnet_result_builder.cpp`
- New: `fishnet_kindrape_topology.{hpp,cpp}`

### Acceptance
- Cones/frusta produce variable per-ring counts without invalid cells.
- No self-overlap/foldback regressions on current strict tests.
- New diagnostics expose transition counts and per-ring counts.

---

## Phase 2 — Explicit KinDrape Step 1/2/3 propagation scheduler (P0)

### Deliverable
Dedicated propagation orchestrator matching KinDrape sequencing.

### Tasks
- Implement Step 1:
  - seed node + second node from draping direction/initial angle.
- Implement Step 2:
  - generator-arm traversal in four directions from seed cell.
- Implement Step 3:
  - constrained quadrant fill between arms.
- Define and implement explicit one-neighbor policy for frontier updates:
  - allowed actions must be deterministic (defer/wait, stage-specific extrapolation, or explicit infeasible event),
  - no silent insertion that bypasses geometric constraints.
- Add boundary/hole dead-zone recovery strategy:
  - bounded retry/alternate expansion order,
  - explicit dead-zone diagnostics when recovery fails.
- Add seam continuity contract enforcement for multi-face propagation:
  - continuity checks on orientation/layout transfer at face boundaries,
  - explicit seam-break diagnostics on violation.
- Make scheduler operate on Phase-1 adaptive topology, not UV rectangular scans.

### Candidate files
- `freecad/Composites/fishnet/fishnet_algorithm.cpp`
- `freecad/Composites/fishnet/fishnet_sampling_node_update.cpp`
- New: `fishnet_kindrape_propagation.{hpp,cpp}`

### Acceptance
- Reproducible arm-first growth with explicit stage diagnostics.
- Stage transitions visible in result diagnostics (`step1`, `step2`, `step3`).
- One-neighbor frontier handling is deterministic and test-covered.
- Boundary/hole dead-zone handling is test-covered with explicit diagnostics for unrecovered regions.
- Multi-face seam continuity invariants are enforced and reported.

---

## Phase 3 — Generator-cell NR shear solver (P0)

### Deliverable
A robust local NR solver for Step-2 cells minimizing shear target error under edge-length constraints.

### Tasks
- Implement local objective equivalent to KinDrape Step-2 objective:
  - minimize shear deviation from target pre-shear.
- Add bounded Newton iterations with guarded fallback (line search / bisection hybrid).
- Preserve branch continuity for circle/surface intersection candidate selection.
- Integrate strict infeasibility reporting (no silent fallback success).

### Candidate files
- `freecad/Composites/fishnet/fishnet_sampling_node_update.cpp`
- `freecad/Composites/fishnet/fishnet_surface_queries.cpp`
- New: `fishnet_kindrape_nr.{hpp,cpp}`

### Acceptance
- Per-generator objective decreases across NR iterations in canonical cases.
- Solver remains stable on curved trimmed faces.

---

## Phase 4 — Pre-shear as propagation-time kinematic target (P0)

### Deliverable
`pre_shear_deg` directly influences Step-2/Step-3 geometric placement, aligned with KinDrape behavior.

### Tasks
- Move pre-shear influence into propagation solver inputs (not only ACP edge objective shaping).
- Keep existing constitutive diagnostics, but split:
  - `propagation_pre_shear_*` vs `objective_pre_shear_*`.
- Ensure signed bias-family conventions remain consistent.

### Candidate files
- `freecad/Composites/fishnet/fishnet_algorithm.cpp`
- `freecad/Composites/fishnet/fishnet_sampling_node_update.cpp`
- `freecad/Composites/fishnet/fishnet_diagnostics_result.cpp`

### Acceptance
- Pre-shear sweeps produce expected signed asymmetry in generator-cell shear fields.

---

## Phase 5 — Diagnostics + observability hardening (P1)

### Deliverable
Complete telemetry for replication confidence and debugging.

### Tasks
- Emit histories:
  - `generator_objective_history`
  - `generator_shear_history`
  - `transition_event_history`
  - per-stage counts (`step1/step2/step3`).
- Emit per-ring statistics:
  - ring index, active nodes, transitions in/out.
- Keep `combined_objective_history` and `residual_history` in sync with performed iterations.

### Candidate files
- `freecad/Composites/fishnet/fishnet_diagnostics_api.hpp`
- `freecad/Composites/fishnet/fishnet_diagnostics_result.cpp`
- `freecad/Composites/fishnet/fishnet_result_builder.cpp`

### Acceptance
- One-run diagnostics are sufficient to explain any stall, split/merge, or infeasible event.

---

## Phase 6 — Validation suite for KinDrape replication (P0)

### Deliverable
A focused replication test suite with canonical cases and reference harness checks.

### Tasks
- Add canonical tests for:
  - hemisphere (center/off-center seed),
  - cone/frustum with strong taper,
  - double-curved analytical surface.
- Add topology tests:
  - variable ring cardinality,
  - legal split/merge stitching,
  - no invalid overlaps/foldback.
- Add frontier/dead-zone behavior tests:
  - one-neighbor frontier handling (defer/fallback/infeasible) is deterministic and explicit,
  - boundary and internal-hole dead-zone recovery or explicit failure diagnostics.
- Add seam continuity tests:
  - cross-face orientation/layout continuity preserved,
  - seam-break conditions are surfaced in diagnostics.
- Add NR/pre-shear behavior tests:
  - monotonic objective decrease in Step-2 locals,
  - signed pre-shear conventions.
- Add reference harness:
  - run matched canonical scenarios against KinDrape reference script and compare structural metrics,
  - add determinism checks for repeated identical runs (stage traces, transition counts, and key metrics stable).

### Candidate files
- `freecad/Composites/compositestests/test_fishnet_native.py`
- `freecad/Composites/compositestests/test_shapes.py`
- new helper under `freecad/Composites/compositestests/` for KinDrape reference comparison

### Acceptance
- New replication suite passes.
- Determinism checks pass for repeated identical runs in the reference harness.
- Existing `42 native + 15 integration` remains green.

---

## Execution slices (safe order)

1. **Slice A (P0):** Phase 1 minimal topology kernel + diagnostics hooks.
2. **Slice B (P0):** Phase 2 scheduler skeleton (step traces only) on new topology.
3. **Slice C (P0):** Phase 3 NR core integration for Step-2 generator cells.
4. **Slice D (P0):** Phase 4 pre-shear kinematic integration + sign tests.
5. **Slice E (P1):** Phase 5 full diagnostics coverage.
6. **Slice F (P0):** Phase 6 reference-harness validation and final stabilization.

At each slice:
- Build native extension.
- Run targeted tests + full native suite.
- Run targeted integration + full integration before final merge.
- Commit only after each defined check/gate passes (no mixed pre-gate WIP commits on main branch).
- Use checkpoint commit prefixes: `kindrape/<slice>/<stage>` (example: `kindrape/slice-a/a3`).

## Slice A (Phase 1) — commit-sized implementation checklist

### Goal for Slice A
Land a minimal adaptive-topology kernel and diagnostics plumbing **without** changing solver physics yet, then switch emission from fixed-grid rectangles to adaptive connectivity in a controlled way.

### Slice A status (2026-05-05)
- ✅ Slice A implementation scope (A0..A7) is complete and blocker stabilization is complete.
- 🟡 Checkpoint policy was executed as a consolidated code commit for A0..A6 (`db619c5`) followed by this plan/finalization update commit for A7.

### Commit policy for Slice A check stages
- Every `A0..A7` gate is a mandatory commit checkpoint.
- If a gate fails, fix-forward locally and do **not** checkpoint commit until the gate passes.
- One checkpoint commit per stage (`A0`, `A1`, ...), plus one final cleanup commit (`A7`).
- Suggested commit subjects:
  - `kindrape/slice-a/a0: scaffold adaptive topology module`
  - `kindrape/slice-a/a1: deterministic adaptive graph construction`
  - `kindrape/slice-a/a2: add split-merge transition primitives`
  - `kindrape/slice-a/a3: derive adaptive row cardinality + transitions`
  - `kindrape/slice-a/a4: switch emitter to adaptive topology`
  - `kindrape/slice-a/a5: wire adaptive topology diagnostics`
  - `kindrape/slice-a/a6: add adaptive topology tests`
  - `kindrape/slice-a/a7: remove temporary fallbacks and finalize docs`

### A0 — Scaffolding only (no behavior change)
- [x] Add new files:
  - `freecad/Composites/fishnet/fishnet_kindrape_topology.hpp`
  - `freecad/Composites/fishnet/fishnet_kindrape_topology.cpp`
- [x] Introduce core types only:
  - `AdaptiveNode`, `AdaptiveEdge`, `AdaptiveCell`, `AdaptiveRowStats`, `TransitionEvent`
- [x] Add compile-only adapters from current grid data (`grid_indices`) to temporary adaptive containers.
- [x] No caller behavior changes; existing emit path remains active.

**Gate:** build extension + full native suite green.

**Checkpoint commit:** `kindrape/slice-a/a0`

### A1 — Deterministic adaptive graph construction (still rectangular parity)
- [x] Build deterministic node/cell ordering rules (stable IDs by row/column scan order).
- [x] Construct adaptive graph from current valid 4-node cells (rectangular parity mode).
- [x] Add internal invariants/assertions:
  - no dangling node references,
  - manifold-ish edge ownership (bounded per-edge incident cells),
  - deterministic ID assignment across repeated runs.
- [x] Keep old `append_grid_topology(...)` as the production emitter (via non-transition stitching mode for strict/default behavior).

**Gate:** full native suite + cone plotting sanity output unchanged qualitatively.

**Checkpoint commit:** `kindrape/slice-a/a1`

### A2 — Transition primitives (disabled by default)
- [x] Implement split/merge templates in topology module:
  - `N -> N+1`
  - `N -> N-1`
- [x] Record transition events in-memory only (`TransitionEvent` list).
- [x] Do **not** yet apply templates to production emission in strict/default mode.

**Gate:** compile + deterministic-run tests still pass.

**Checkpoint commit:** `kindrape/slice-a/a2`

### A3 — Adaptive row-cardinality extraction from current sampled rows
- [x] Replace one-dimensional row pruning side-effects with explicit per-row active-node sequences in adaptive structure.
- [x] Compute row-to-row cardinality deltas and instantiate transition events.
- [x] Keep a strict fallback path when transitions are invalid (emit explicit diagnostic reason, not silent downgrade).

**Gate:**
- existing cone variable-column test still passes,
- new targeted assertion: at least one transition event on strong taper cone/frustum.

**Checkpoint commit:** `kindrape/slice-a/a3`

### A4 — Switch emitter to adaptive topology (P0 cutover point)
- [x] Add new emitter in topology module:
  - emit quads/triangles from adaptive cells + transition stitching.
- [x] Wire `fishnet_geometry_sampling.cpp` to use adaptive emitter.
- [x] Keep old rectangular parity behavior available through topology build options for strict/default mode; no debug fallback switch retained.

**Gate:**
- no-overlap/foldback tests pass,
- spacing acceptance (`test_acp_v2_surface_spacing_enforces_near_constant_3d_edge_lengths`) remains green,
- cone/frustum adaptive-cardinality tests green.

**Checkpoint commit:** `kindrape/slice-a/a4`

### A5 — Diagnostics wiring for adaptive topology
- [x] Add diagnostics fields:
  - `topology_transition_count`
  - `topology_split_count`
  - `topology_merge_count`
  - `topology_transition_fail_count`
  - `per_ring_counts` (or `per_row_counts`) summary payload
- [x] Thread stats through:
  - `fishnet_sampling_api.hpp`
  - `fishnet_diagnostics_api.hpp`
  - `fishnet_result_builder.cpp`
  - `fishnet_diagnostics_result.cpp`

**Gate:** diagnostics present on both geometry and mesh solve outputs (where applicable).

**Checkpoint commit:** `kindrape/slice-a/a5`

### A6 — Tests added in same slice
- [x] `test_cone_face_adaptive_topology_emits_transition_events`
- [x] `test_frustum_cardinality_changes_are_stitched_without_overlap`
- [x] `test_adaptive_topology_deterministic_transition_counts`
- [x] `test_transition_failure_is_explicitly_reported`

**Gate:**
- full native suite green,
- targeted integration test green,
- no tolerance/threshold loosening.

**Checkpoint commit:** `kindrape/slice-a/a6`

### A7 — Cleanup before merging Slice A
- [x] Remove temporary debug fallback emitter switch.
- [x] Remove dead helper code from transitional adapters.
- [x] Update this plan file with Slice A status (`✅`/`🟡`) and links to merged commits.
- [x] Produce final Slice A summary with gate outputs and commit SHAs.

**Checkpoint commit:** `kindrape/slice-a/a7`

### Slice A final gate summary (2026-05-05)
- ✅ Native extension build: passed (`/home/jmw/opt/FreeCAD/.pixi/envs/default/bin/python setup.py build_ext --inplace`)
- ✅ Targeted blocker tests passed:
  - `test_acp_v2_surface_spacing_enforces_near_constant_3d_edge_lengths`
  - `test_cone_face_structural_edges_follow_fabric_spacing`
  - `test_strict_mode_enforces_shear_lock_and_no_foldback`
- ✅ Slice-A adaptive topology tests passed:
  - `test_cone_face_adaptive_topology_emits_transition_events`
  - `test_frustum_cardinality_changes_are_stitched_without_overlap`
  - `test_adaptive_topology_deterministic_transition_counts`
  - `test_transition_failure_is_explicitly_reported`
- ✅ Full native suite passed: `47/47`
- 🟡 Integration gate for this slice remains to be re-run before final merge gate.

### Slice A commit references
- `db619c5` — `kindrape/slice-a/a6: adaptive topology cutover + blocker stabilization`
- `HEAD (a7)` — `kindrape/slice-a/a7: finalize Slice A plan status and gate summary`

---

## Risk controls

- **Topology regressions:** gate every slice with no-overlap/foldback tests and deterministic repeat tests.
- **NR instability:** implement strict max-iter, fallback branch, and explicit infeasible diagnostics.
- **Silent behavior drift:** enforce stage-level diagnostics and per-stage assertions.
- **Boundary/hole stalls:** require explicit dead-zone recovery attempts and failure diagnostics.
- **Cross-face seam drift:** enforce continuity invariants and seam-break reporting.
- **Acceptance drift:** do not loosen tolerances without explicit approval.

## Final handover checklist

- [ ] All P0 phases complete (1,2,3,4,6).
- [ ] P1 diagnostics hardening complete (5).
- [ ] Full native + integration suites green.
- [ ] Updated docs reflect final propagation/topology model and diagnostics contract.
