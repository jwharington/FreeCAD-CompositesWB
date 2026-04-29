# Fishnet Shell Orientation Transfer Design

**Date:** 2026-04-29  
**Repository:** `FreeCAD-CompositesWB`  
**Status:** Draft design for implementation planning

## 1. Problem Statement

The fishnet draping work has moved toward a native, surface-facing solver, but the remaining gap is **shell-wide orientation continuity**. A single-face solver can sample a face directly and build a pin-jointed net, but shells introduce a second problem: the fabric frame must remain coherent across adjacent faces.

Without an explicit orientation-transfer layer, the solver can:

- rotate warp/weft axes unexpectedly at face boundaries
- flip orientation when a face has reversed parameterization
- lose continuity across smooth transitions
- behave inconsistently on seams, hard edges, and trimmed openings
- confuse downstream tools that rely on stable texture coordinates and boundary loops

The design goal is to make shell handling **native and explicit**, not an accidental byproduct of iterating face-by-face.

## 2. Goals

### Primary goals

1. Make the fishnet solver work natively on FreeCAD surface geometry, not just on precomputed mesh input.
2. Add a native shell adapter that can propagate orientation across adjacent faces.
3. Keep warp/weft orientation stable across smooth face boundaries.
4. Preserve a clear distinction between continuous boundaries, seams, and open edges.
5. Keep the public `CompositeShell` API stable for `TexturePlan`, grid rendering, and fibre helpers.

### Secondary goals

1. Keep the Python fallback API available until the native extension is built.
2. Preserve the current texture renderer path (`TexturePlan` and `MeshGridShader`) through the new backend.
3. Keep the transition from the existing fishnet workbench architecture incremental and debuggable.

## 3. Non-Goals

This design does not attempt to solve everything at once. It does **not** aim to:

- implement a full manufacturing-grade multi-piece shell decomposition system
- guarantee exact numerical equivalence with the prior prototype draper
- remove all Python code from the workbench
- redesign the UI or task panels beyond what the shell adapter needs
- replace the public `CompositeShell` document object with a new object type

## 4. Current State

The current fishnet workbench already has:

- a native solver path under `freecad/Composites/_fishnet.cpp`
- a Python fallback mirroring the native solver API under `freecad/Composites/_fishnet.py`
- a Python draper adapter under `freecad/Composites/tools/fishnet_draper.py`
- a `CompositeShell` document object that remains the public API for the workbench
- a texture-plan workflow that consumes `CompositeShell.get_boundaries()`
- a grid-rendering workflow that consumes `CompositeShell.get_tex_coords()`

The remaining limitation is that the current native-facing path still behaves as a mesh-oriented pipeline in places where the shell itself should be the source of truth.

## 5. Proposed Approach

### 5.1 Native face solver

The core native solver should operate on a **single FreeCAD face** at a time.

Responsibilities:

- query the face surface directly
- sample the trimmed domain
- seed a warp/weft net on the surface
- relax the net using a pin-jointed / GIB-style loop
- project nodes back onto the surface
- emit fabric points, quads, boundary loops, strain data, and face frame data

This keeps the solver stable and easier to reason about.

### 5.2 Native shell adapter

A native shell adapter should sit above the face solver and be responsible for shell-wide continuity.

Responsibilities:

- traverse the shell face adjacency graph
- choose a stable starting face and starting frame
- transfer orientation across face boundaries
- merge per-face results into a shell-wide result
- mark seams and discontinuities explicitly
- preserve enough metadata for downstream texture and preview tooling

The shell adapter should be a thin orchestration layer, not a second solver.

### 5.3 Python fallback until build

Keep a Python fallback that mirrors the native API only until the extension is built.

Responsibilities:

- allow source checkouts to run before compilation
- mirror the same result structure as the native module
- keep the rest of the workbench importable in pure Python contexts

This fallback should not become the long-term production route.

## 6. Orientation Transfer Rules

Orientation transfer is the core shell-adapter responsibility.

### 6.1 Local frame on each face

For every solved face, store a local frame:

- `N` = face normal
- `X` = warp direction
- `Y` = weft direction

The face solver should emit or allow reconstruction of this frame.

### 6.2 Propagation across adjacency

When the adapter crosses from face A to adjacent face B:

1. Use the shared edge tangent as the continuity anchor.
2. Project face A’s `X` axis into face B’s tangent plane.
3. Recompute `Y` from `N × X`.
4. Choose the orientation that best preserves continuity.
5. If the projection is degenerate, mark the transition as a break and reseed locally.

### 6.3 Continuity policy

Prefer continuity unless a break is justified by geometry.

A transition should be treated as a continuity break when:

- the shared edge is a seam or topological discontinuity
- the faces meet at a hard or highly non-smooth angle
- the projected axis becomes nearly zero length
- the face parameterization flips or is unreliable

### 6.4 Explicit break markers

If continuity is not safe, the adapter should record that fact instead of guessing.

The result should preserve:

- which edges were continuous
- which edges were breaks
- where reseeding occurred
- where orientation had to be locally re-established

That makes the behavior inspectable in tests and previews.

## 7. Data Flow

1. `CompositeShell` receives a support shape, laminate, LCS, and fishnet parameters.
2. The native layer solves one face or a face chain.
3. The shell adapter propagates orientation and merges face results.
4. Python exposes the result through the existing `CompositeShell` methods.
5. `TexturePlan`, grid rendering, and strain visualization consume the same stable API as before.

## 8. Result Shape

The shell-level solver result should include:

- `fabric_points`
- `fabric_quads`
- `boundary_loops`
- `face_frames`
- `orientation_breaks`
- `strain` / convergence diagnostics
- validity / error information

The adapter should expose this without requiring downstream consumers to know whether the data came from one face or many.

## 9. Error Handling

Rules for shell orientation failures:

1. Invalid geometry or sampling failure should set `DrapeStatus = "Error"`.
2. Shell orientation ambiguity should be explicit, not silent.
3. A failed face transition should not silently inherit a frame that is obviously inconsistent.
4. The workbench should never fall back to the old prototype draper in production code.
5. Python fallback behavior should remain available only until the native extension is built.

Partial success is allowed if the result is clearly marked and the downstream API remains usable.

## 10. Compatibility with Existing Workbench Features

This design must preserve the current public shell API:

- `get_tex_coords()`
- `get_boundaries()`
- `get_lcs()`
- `get_lcs_at_point()`
- `get_tex_coord_at_point()`
- `get_strains()`

It must also continue to support the current texture renderer path:

- `TexturePlan`
- `MeshGridShader`
- boundary-wire previews
- grid overlays

The adapter should do the work needed to keep those consumers stable.

## 11. Testing Strategy

### 11.1 Native face solver tests

Add coverage for:

- a simple planar face
- a cylindrical face
- a concave trimmed face
- direct surface sampling
- quad generation and boundary loop extraction

### 11.2 Native shell-adapter tests

Add coverage for:

- two adjacent faces with smooth continuity
- a hard-edge face transition
- a seam or discontinuity case
- a flipped or awkward parameterization case
- a shell with an open boundary

### 11.3 FreeCAD integration tests

Add integration coverage for:

- `CompositeShell` recompute on shell-like geometry
- `TexturePlan` consuming `get_boundaries()` from the new solver result
- grid rendering using `get_tex_coords()` from the new solver result
- solid cases still showing the unwrapped net in the plot views
- explicit failure reporting when continuity cannot be maintained

## 12. Rollout Plan

### Phase 1: face solver

Implement the native direct-surface face solver and its Python fallback mirror.

### Phase 2: shell adapter

Add the native shell adapter and orientation propagation rules.

### Phase 3: compatibility checks

Verify `CompositeShell`, `TexturePlan`, grid rendering, and strain helpers still work.

### Phase 4: remove fallback dependency

Once the extension is built and stable, keep the Python fallback only for source checkout compatibility if needed, but do not use it as the production path.

## 13. Success Criteria

This design is successful when:

- the solver works natively on FreeCAD surface geometry
- shell face orientation stays coherent across smooth boundaries
- seams and discontinuities are explicit
- `CompositeShell` retains its current public API
- `TexturePlan` and grid rendering continue to work unchanged from the consumer side
- native and FreeCAD integration tests cover face and shell behavior end to end

## 14. Relationship to Existing Fishnet Work

This design is a refinement of the existing fishnet workbench design. It narrows the focus to the shell-adapter and orientation-propagation problem, while keeping the previously established goals intact:

- native fishnet solver in C++
- Python adapter for workbench compatibility
- stable `CompositeShell` API
- support for the existing texture renderer and plot/test flow
