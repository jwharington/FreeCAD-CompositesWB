# Fishnet Architecture Deepening — Handover Plan

**Date:** 2026-05-05  
**Repo:** `freecad/Composites/fishnet/*`  
**Goal:** Execute all identified deepening opportunities while preserving solver behavior.

## 1) Outcomes

This handover plan covers all five selected opportunities:

1. Split `fishnet_algorithm_sections.hpp` into focused modules and seams.
2. Deepen sampling grid orchestration into a state-owning module.
3. Unify geometry and mesh solve orchestration behind a shared pipeline seam with adapters.
4. Separate domain diagnostics/result assembly from Python object adapter.
5. Centralize parameter interpretation in one typed parameter module.

Success criteria:
- Build remains green after each phase (`python setup.py build_ext --inplace`).
- Python compile checks remain green (`python -m compileall freecad/Composites/fishnet`).
- Existing fishnet native tests remain unchanged in tolerance and assertions.
- Public Python interface remains stable (`freecad.Composites.fishnet.solve`).

## 2) Guiding constraints

- Behavior-preserving refactor only (no algorithmic behavior drift unless explicitly approved).
- Do not weaken tests, remove tests, or loosen thresholds.
- Keep each module’s interface smaller than its implementation (depth target).
- Prefer high locality: each change should have one obvious owning module.

## 3) Execution strategy

Use six phases with merge-safe checkpoints.

### Phase 0 — Baseline and guardrails (1 PR)

**Deliverables**
- Snapshot current module sizes and include graph.
- Capture baseline command outputs:
  - `python setup.py build_ext --inplace`
  - `python -m compileall freecad/Composites/fishnet`
- Capture current test invocation notes for `compositestests/test_fishnet_native.py` (environment-dependent).

**Acceptance**
- Baseline document committed under `artifacts/`.

### Phase 1 — Header seam split for algorithm sections (1–2 PRs)

**Current friction**
`fishnet_algorithm_sections.hpp` is a broad module interface mixing unrelated declarations.

**Plan**
- Create focused headers, e.g.:
  - `fishnet_sampling_api.hpp`
  - `fishnet_layout_geometry_api.hpp`
  - `fishnet_diagnostics_api.hpp`
  - `fishnet_options_api.hpp`
  - `fishnet_result_api.hpp`
- Move declarations incrementally; keep temporary compatibility includes if needed.
- Update includes in implementation files to consume only required seams.

**Acceptance**
- `fishnet_algorithm_sections.hpp` either removed or reduced to a narrow compatibility shim.
- Include usage is purpose-specific per module.

### Phase 2 — Deep sampling grid module (1–2 PRs)

**Current friction**
Sampling flow still leaks grid-state invariants across orchestration functions.

**Plan**
- Introduce a deep module owning sampling grid state + invariants, e.g. `SamplingGridModule`.
- Move mutation-heavy fields (`grid_indices`, `grid_u/v`, `grid_normals`, `active_nodes`, seeds) behind module interface.
- Keep node update and relaxation behind this seam as implementation.

**Acceptance**
- Callers do not manually coordinate grid vectors.
- Sampling entrypoint consumes compact input and emits `FaceSample` + diagnostics.

### Phase 3 — Shared solve pipeline + two adapters (1–2 PRs)

**Current friction**
Geometry and mesh solve paths duplicate orchestration patterns.

**Plan**
- Define one pipeline module for common solve flow.
- Keep two adapters at the seam:
  - Geometry adapter (TopoDS/Part face extraction path)
  - Mesh adapter (point/face sequence path)
- Preserve result parity and error modes.

**Acceptance**
- One orchestration implementation for pipeline steps.
- Two concrete adapters in production (real seam, not hypothetical).

### Phase 4 — Result domain module + Python adapter split (1–2 PRs)

**Current friction**
`fishnet_result_builder.cpp` mixes domain decisions and Python C-API object assembly.

**Plan**
- Build typed domain result and diagnostics summarization module.
- Keep Python object conversion in thin adapter module.
- Reuse existing `fishnet_python_util.*` helpers where practical.

**Acceptance**
- Domain result assembly is testable without Python object construction.
- Python adapter layer is mostly serialization/mapping.

### Phase 5 — Typed parameter module centralization (1 PR)

**Current friction**
Parameter parsing logic is distributed (`fishnet_options.cpp`, `fishnet_acp_layout.cpp`, diagnostics/profile functions).

**Plan**
- Introduce typed parameter module for all accepted keys/defaults/clamps.
- Replace scattered `PyDict_GetItemString` reads in downstream modules with typed access.
- Keep algorithm-profile interpretation in one location.

**Acceptance**
- One source of truth for parameter interface and invariants.
- Downstream modules avoid direct dict parsing.

### Phase 6 — Consolidation and hardening (1 PR)

**Plan**
- Remove temporary compatibility shims.
- Re-run size snapshot and compare against baseline.
- Run build/compile checks and environment-available tests.
- Produce final architecture delta notes.

**Acceptance**
- No dead seams or pass-through modules remain from transition.
- Updated handover note with final module map.

## 4) Work breakdown by module

### A. Seam split
- Primary files: `fishnet_algorithm_sections.hpp`, all fishnet `.cpp/.hpp` includes.
- Risk: include cycles.
- Mitigation: move shared structs to minimal type header first.

### B. Sampling deepening
- Primary files: `fishnet_geometry_sampling.cpp`, `fishnet_sampling_node_update.*`, `fishnet_surface_relaxation.*`.
- Risk: hidden invariants in active-node behavior.
- Mitigation: add focused regression checks for node activation/order stability.

### C. Shared pipeline
- Primary files: `fishnet_algorithm.cpp` (+ new pipeline module).
- Risk: geometry/mesh divergence in edge cases.
- Mitigation: parity tests for both adapters with matched synthetic inputs.

### D. Result split
- Primary files: `fishnet_result_builder.cpp`, `fishnet_diagnostics_result.cpp`, `fishnet_python_util.cpp`.
- Risk: Python refcount regressions.
- Mitigation: keep adapter minimal and reuse existing list/tuple builders.

### E. Typed params
- Primary files: `fishnet_options.*`, `fishnet_acp_layout.cpp`, `fishnet_diagnostics_result.cpp`.
- Risk: behavior drift from fallback/default changes.
- Mitigation: preserve exact default constants and key precedence order.

## 5) Test and verification plan

Per PR (required):
1. `python setup.py build_ext --inplace`
2. `python -m compileall freecad/Composites/fishnet`
3. Run available subset of fishnet native tests in current environment.

Milestone-level (after Phases 3 and 6):
- Execute `freecad/Composites/compositestests/test_fishnet_native.py` scenarios available in environment.
- Record parity checks for:
  - output keys
  - point/quad counts
  - diagnostics presence and key naming
  - algorithm metadata (`algorithm`, `termination_reason`, `converged`, `iterations`)

## 6) Handover checklist for incoming engineer

- [x] Read this plan and current `artifacts/` baseline snapshot.
- [x] Confirm clean working tree and rebuild extension.
- [x] Execute phases sequentially; do not batch all phases in one PR.
- [x] Preserve external solve interface and diagnostics key compatibility.
- [x] Keep commits scoped to one seam deepening objective each.
- [x] At end of each PR, capture before/after module size deltas.

### Phase completion status (2026-05-05)

| Phase | Description | Status | Tests |
|-------|-------------|--------|-------|
| 0 | Baseline snapshot | ✅ done | — |
| 1 | Header seam split (`fishnet_algorithm_sections.hpp` → 5 focused headers + shim) | ✅ done | 42/42 |
| 2 | Deep sampling grid module (`SamplingGridState` owning all grid vectors) | ✅ done | 42/42 |
| 3 | Shared solve pipeline + geometry/mesh adapters | ✅ done | 42/42 |
| 4 | Result domain/Python adapter split (`SolverDiagnosticsInput` + 3 fns moved to diagnostics seam) | ✅ done | 42/42 |
| 5 | Typed parameter module (`param_double/bool/string` consolidated to `fishnet_options.cpp`) | ✅ done | 42/42 |
| 6 | Consolidation: shim deleted, `relax_fabric_points_with_edge_constraints` moved to `fishnet_layout_geometry_api.hpp` | ✅ done | 42/42 |

All six phases complete. No dead seams or compatibility shims remain.

## 7) Rollback strategy

If a phase destabilizes behavior:
- Revert only that phase PR.
- Keep previous accepted seams intact.
- Resume with smaller vertical slice in same phase.

No cross-phase rewrites before prior phase is green.

## 8) Definition of done

- [x] All five deepening opportunities implemented (plus shim removal as Phase 6).
- [x] Solver behavior preserved for existing covered scenarios.
- [x] Build and compile checks green.
- [x] Module map shows improved depth (smaller interfaces, concentrated implementations, better locality).

**Completed 2026-05-05. 42/42 native tests pass on all phases.**
- Final handover update includes resulting seams and owning modules.
