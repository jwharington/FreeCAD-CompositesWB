# Fishnet Native Geometry Cutover Design

**Date:** 2026-04-30  
**Repository:** `FreeCAD-CompositesWB`  
**Status:** Draft design for implementation planning

## 1. Problem Statement

The fishnet solver has already moved a large portion of its work into native C++, but the current implementation still calls back into Python for some geometry evaluation in tight loops. The most important examples are surface evaluation and face classification:

- `valueAt` / `normalAt` for sampling and frame construction
- `isInside` / face containment checks when classifying points
- repeated Python attribute lookups used to derive UV bounds and face parameters

These calls are correct, but they are the wrong layer for the hot path. They add overhead, make the solver dependent on Python object shape at runtime, and prevent the fishnet backend from becoming a clean native geometry pipeline.

The goal of this refactor is to keep the public Python entrypoint stable while moving the solver’s repeated geometry work onto native FreeCAD/OCC objects entirely.

## 2. Goals

### Primary goals

1. Remove Python geometry calls from fishnet hot loops.
2. Evaluate points, normals, bounds, and containment natively in C++.
3. Keep the public solver API stable for existing callers.
4. Preserve current fishnet outputs and plotting behavior.
5. Keep testing after every phase of the refactor.

### Secondary goals

1. Reduce repeated Python attribute lookups in the solver path.
2. Make geometry ownership and classification explicit in C++.
3. Keep the legacy Python fallback path aligned until it can be trimmed safely.
4. Preserve the current native-vs-legacy comparison tests for curved faces.

## 3. Non-Goals

This design does **not** attempt to:

- refactor other workbench modules outside fishnet
- change the UI, task panels, or texture rendering API
- switch fishnet to Coin3D for geometry evaluation
- redesign atlas plotting or mesh visualization
- introduce new manufacturing or nesting features

## 4. Important Clarification: Not Coin3D

Coin3D is the view/scene-graph layer. It is not the geometry kernel.

For fishnet, the lower-level native path should use FreeCAD/OCC geometry directly:

- `TopoDS_Face`
- `TopoDS_Shape`
- `BRep_Tool`
- `BRepAdaptor_Surface`
- `GeomLProp_SLProps`
- OCC face classification utilities where appropriate

The solver should not descend into Coin3D to evaluate geometry.

## 5. Current State

The current fishnet pipeline already has:

- a native solver module in `freecad/Composites/_fishnet.cpp`
- a Python compatibility module in `freecad/Composites/_fishnet.py`
- Python-facing adapter code in `freecad/Composites/tools/fishnet_draper.py`
- integration plot coverage in `freecad/Composites/compositestests/plotting.py`
- native and integration regression tests in `freecad/Composites/compositestests/test_fishnet_native.py` and `test_integration_freecad.py`

The solver currently still uses Python geometry methods in a few places, especially where face/surface information is queried repeatedly.

## 6. Proposed Architecture

### 6.1 Public API boundary stays Python-compatible

The external `solve(...)` entrypoint should continue to accept the same Python/FreeCAD geometry objects as today.

That boundary is only for compatibility and conversion.

### 6.2 Native geometry adapter inside C++

Introduce a native face adapter in `_fishnet.cpp` that converts the input face or shell geometry to native OCC handles once, then caches what the solver needs:

- face shape handle
- surface handle / adaptor
- UV bounds
- face-local frame data
- native point classifier for containment checks

After that conversion, the solver should not call back into Python for geometry in the hot path.

### 6.3 Native evaluation helpers

Replace repeated Python geometry lookups with native helpers for:

- surface point evaluation
- surface normal evaluation
- parameter range / UV bounds access
- containment checks (`isInside` equivalent)
- adjacency and orientation transfer traversal where it depends on face geometry

### 6.4 Keep output shape stable

The solver result must continue to expose the current core fields used by the rest of the workbench:

- `valid`
- `error`
- `fabric_points`
- `fabric_quads`
- `boundary_loops`
- `strains`
- `mesh_points`
- `mesh_faces`
- `face_frames`
- `orientation_breaks`
- `atlas_charts`
- `origin`
- `normal`
- `x_axis`
- `y_axis`
- `parameters`

The atlas result is already native, so this work should not destabilize it.

## 7. Refactor Phases

### Phase 1: Native face adapter

#### Scope
- Add a native C++ representation for the supported fishnet face types.
- Extract UV bounds and surface handles natively.
- Remove repeated Python attribute access used only to discover geometry metadata.

#### Deliverables
- Native helper(s) for face wrapping and bound extraction.
- A single conversion step at the Python/C++ boundary.

#### Testing for this phase
- Rebuild the extension:
  - `python setup.py build_ext --inplace`
- Run native fishnet tests:
  - `freecad/Composites/compositestests/test_fishnet_native.py`
- Run integration tests:
  - `freecad/Composites/compositestests/test_integration_freecad.py`
- Add or update face-bound regression checks for:
  - planar face
  - cylinder face
  - cone face

### Phase 2: Native surface sampling

#### Scope
- Replace `valueAt`-based sampling with native surface evaluation.
- Replace `normalAt`-based frame construction with native normal evaluation.
- Keep the solver API and result shape unchanged.

#### Deliverables
- Native point evaluation helper.
- Native normal evaluation helper.
- Sampling path no longer depends on Python surface methods.

#### Testing for this phase
- Existing curved-face comparison tests must still pass:
  - cylinder face legacy-vs-native comparison
  - cone face legacy-vs-native comparison
- Keep the manual-review plot path available.
- Run:
  - `test_fishnet_native.py`
  - `test_integration_freecad.py`
- If plotting is enabled, verify the saved comparison plots visually.

### Phase 3: Native containment / `isInside`

#### Scope
- Replace Python point-in-face checks with native containment classification.
- Cache any classifier setup needed so classification remains efficient in loops.

#### Deliverables
- Native containment helper.
- No repeated Python `isInside` calls inside solver loops.

#### Testing for this phase
- Add targeted containment tests for inside/outside/boundary cases.
- Use procedural geometry only:
  - cylinder segment
  - cone segment
  - one concave/stepped shell case if needed for coverage
- Run:
  - new containment tests
  - `test_fishnet_native.py`
  - `test_integration_freecad.py`

### Phase 4: Native orientation transfer cleanup

#### Scope
- Remove any remaining Python geometry calls used by face adjacency and orientation propagation.
- Keep atlas chart output and plot consumers unchanged.

#### Deliverables
- Native-only geometry queries in the hot path.
- Orientation transfer logic that depends on native face data rather than Python access.

#### Testing for this phase
- Re-run the full fishnet native suite.
- Re-run the full integration suite.
- Verify the stitched atlas still renders correctly in the third plot pane.
- Re-check the curved-face comparison plots manually.

### Phase 5: Cleanup and fallback trimming

#### Scope
- Remove dead Python geometry helpers in `_fishnet.py` once the native path is stable.
- Remove any redundant compatibility scaffolding that no longer serves the solver.
- Keep only the Python boundary necessary for public API compatibility.

#### Deliverables
- Smaller Python fallback surface.
- Cleaner native solver boundary.

#### Testing for this phase
- Full native fishnet suite.
- Full integration suite.
- Plot generation smoke test with `FISHNET_PLOTS=1`.

## 8. Error Handling

The refactor should preserve current solver behavior for valid geometry and improve clarity for invalid geometry.

Rules:

1. If a face cannot be converted to native OCC geometry, return a clear solver error rather than falling back into a slow Python loop.
2. If a sampled point or normal cannot be evaluated natively, fail that face explicitly and preserve the error context.
3. If a point-classification query fails, report the face and point context rather than silently retrying in Python.
4. Keep recoverable geometric issues distinct from hard solver failures.

## 9. Testing Strategy

Testing is required at **every phase**, not only at the end.

### Required test layers

1. **Build test**
   - `python setup.py build_ext --inplace`
2. **Native solver tests**
   - `freecad/Composites/compositestests/test_fishnet_native.py`
3. **Integration tests**
   - `freecad/Composites/compositestests/test_integration_freecad.py`
4. **Manual-review plots**
   - enable with `FISHNET_PLOTS=1`
   - confirm cylinder/cone comparison visuals remain sensible

### Phase-gated rule

Do not advance from one phase to the next until the tests for the current phase pass.

## 10. Success Criteria

This refactor is successful when:

- the fishnet solver no longer calls Python geometry methods in hot loops
- `valueAt`, `normalAt`, and `isInside` equivalents are native
- the public solver API remains usable from Python
- the existing fishnet tests still pass
- manual-review plots for curved faces still work
- atlas rendering and texture-plan compatibility remain intact

## 11. Rollout Plan

1. Implement the native face adapter.
2. Replace sampling and normals with native OCC evaluation.
3. Replace Python containment checks with a native classifier.
4. Finish native orientation-transfer cleanup.
5. Remove obsolete Python geometry helpers.
6. Re-run the full test matrix after each step.

## 12. Implementation Notes

- Prefer the smallest native abstraction that keeps the solver readable: helper functions around `TopoDS_Face`, `BRepAdaptor_Surface`, and OCC classifiers first; a dedicated wrapper type only if profiling or code clarity demands it.
- Keep the Python compatibility boundary only as long as the public solver entrypoint still needs it. The hot path itself should remain native.
- Choose the OCC classification path that matches existing solver behavior first, then optimize after the phase-specific tests pass.
