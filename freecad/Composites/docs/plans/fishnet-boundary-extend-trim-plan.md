# Fishnet Boundary Extension + Edge Trimming Plan

## Goal
Modify the fishnet draping pipeline so that:
1. drape growth extends past trimmed face boundaries (to avoid under-coverage near edges), and
2. final draped output is trimmed cleanly at face edges (including holes), producing valid boundary-conforming mesh output.

---

## Success Criteria
- The resulting drape visually and topologically covers the full face up to edges.
- Output mesh triangles/quads do not extend outside the target trimmed face.
- Inner holes remain open (not filled by drape cells).
- Boundary loops reflect trimmed output boundaries.
- Existing solver stability and spacing behavior are preserved in interior regions.
- Deterministic outputs for fixed seeds/parameters.

---

## Scope
### In scope
- Geometry-input fishnet path (`Part.Face` / shape sampling path).
- Sampling/growth behavior near boundaries.
- Post-solve trim of draped cells to trimmed face boundaries.
- Result output data wiring (mesh faces, quads, boundary loops, warp/weft boundaries).
- New/updated tests for boundary coverage and clipping correctness.

### Out of scope (phase 1)
- Mesh-input solver path changes.
- New UI controls beyond optional solver parameters.
- Major objective-function redesign.

---

## Current Behavior (Problem Summary)
- Geometry sampling currently rejects points outside the trimmed face during grid growth.
- This prevents overshoot/bleed near boundary edges and can leave edge-adjacent coverage gaps.
- Boundary loops are derived from pre-trim topology, so output alignment to exact CAD edges is limited.

---

## Proposed Approach
Use a **two-stage boundary workflow**:
1. **Extend stage**: allow drape sampling/topology to grow over boundary edges (within UV domain).
2. **Trim stage**: clip draped cells back to exact trimmed face boundaries before final output.

This preserves robust interior drape behavior while ensuring exact boundary conformity.

---

## Design Details

## 1) Add boundary behavior options
**Files:**
- `Composites/fishnet/fishnet_options_api.hpp`
- `Composites/fishnet/fishnet_options.cpp`
- `Composites/fishnet/fishnet_options.hpp`

### Changes
Add normalized parameters:
- `boundary_extend` (bool, default `true` for geometry path)
- `boundary_trim` (bool, default `true` for geometry path)

These provide a controlled rollout and debugging fallback.

---

## 2) Allow growth beyond trimmed boundaries
**Primary file:**
- `Composites/fishnet/fishnet_geometry_sampling.cpp`

### Changes
- In `ensure_grid_node_at(...)`, stop hard-rejecting nodes because `native_face_is_inside == false` when `boundary_extend=true`.
- Continue sampling in UV domain but record per-node face state (`IN`/`ON`/`OUT`) for trimming.

### Supporting data model
**File:**
- `Composites/fishnet/fishnet_sampling_grid_module.hpp`

Add per-node classification storage (e.g. `grid_face_state`) parallel to `grid_indices`.

---

## 3) Keep solver constraints on the untrimmed structural grid
**Primary file:**
- `Composites/fishnet/fishnet_algorithm.cpp`

### Changes
- Continue using extended grid topology for relaxation/objective solving.
- Do **not** include tiny clip-generated trim edges in solver edge constraints.

### Rationale
Avoids instability and false edge-length violations caused by very short clipped edge fragments.

---

## 4) Add dedicated post-solve trim pass
**New module (recommended):**
- `Composites/fishnet/fishnet_boundary_trim.hpp`
- `Composites/fishnet/fishnet_boundary_trim.cpp`

### Input
- Original native face (`TopoDS_Face`)
- Extended drape points/cells (mesh + fabric coordinates)
- Per-node face state where available

### Output
- Trimmed mesh points/faces (3D)
- Trimmed fabric points/cells (2D drape coordinates)
- Mapping/reindexing for consistent result packaging

### Algorithm (cell clipping)
For each draped cell (quad or derived triangle):
1. Classify corners as IN/ON/OUT.
2. If all IN/ON: keep cell.
3. If mixed: clip polygon against face boundary.
4. Compute edge-boundary intersections using robust UV bisection + classifier checks.
5. Cache intersections by edge key so neighboring cells share exact trim vertices.
6. Triangulate clipped polygons for `mesh_faces` output.
7. Keep quads only when clipped polygon remains 4-sided and valid.

### Critical consistency rule
Whenever a new clipped vertex is created:
- create synchronized entries in:
  - 3D mesh point list,
  - fabric point list,
  - local point list (if needed for strain bookkeeping).

---

## 5) Rebuild boundary loops from trimmed topology
**Files:**
- `Composites/fishnet/fishnet_algorithm.cpp`
- `Composites/fishnet/fishnet_result_builder.hpp`
- `Composites/fishnet/fishnet_result_builder.cpp`

### Changes
- Compute output `boundary_loops` from trimmed output faces (not pre-trim solver faces).
- Ensure `warp_weft_boundary_loops` align with trimmed boundaries.

---

## 6) Separate solver topology vs output topology in result payload
**Files:**
- `Composites/fishnet/fishnet_result_builder.hpp`
- `Composites/fishnet/fishnet_result_builder.cpp`

### Changes
- Extend geometry result input to carry both:
  - solver topology/data (for objective/diagnostics continuity), and
  - trimmed output topology/data (for final mesh/loops/quads).

### Diagnostic policy
- Preserve existing edge/objective diagnostics against solver topology.
- Add optional trim diagnostics (e.g., clipped cell count, generated trim vertex count).

---

## 7) Testing Plan
**Primary file:**
- `Composites/compositestests/test_fishnet_native.py`

### New tests
1. **Edge coverage on trimmed irregular face**
   - Use irregular spline boundary (with hole where applicable).
   - Assert boundary-adjacent coverage is present (no large edge gaps).

2. **Trim correctness**
   - Assert all output mesh vertices are IN/ON (within tolerance).
   - Assert no output triangle crosses outside.

3. **Hole preservation**
   - For holed face, verify hole boundary remains represented and unfilled.

4. **Determinism**
   - Repeated runs with identical params/seed produce stable counts/topology metrics.

5. **Regression safety**
   - Existing cone/cylinder and spacing/shear tests remain green.

---

## 8) Performance and Robustness Guardrails
- Cache node face-state classifications.
- Cache edge intersection points by edge key `(min_idx,max_idx)`.
- Restrict expensive clipping/classification work to mixed-state boundary cells.
- Use strict epsilon policy for intersection de-duplication and loop closure.

---

## Implementation Sequence
1. Add new boundary parameters + parsing.
2. Extend geometry sampling past trimmed boundaries and store node face state.
3. Implement post-solve trim module with shared-edge intersection caching.
4. Wire trimmed outputs into result builder and boundary loop generation.
5. Add trim diagnostics.
6. Add focused tests, then run full fishnet native suite.

---

## Risks and Mitigations
- **Risk:** Tiny clipped slivers create unstable topology.
  - **Mitigation:** minimum area/edge filters during clipped polygon triangulation.
- **Risk:** Non-deterministic intersection ordering.
  - **Mitigation:** canonical edge keys + deterministic vertex insertion order.
- **Risk:** Diagnostic drift after topology split.
  - **Mitigation:** preserve solver diagnostics on pre-trim topology; add separate trim metrics.

---

## Definition of Done
- All planned tests pass (new + existing).
- Boundary coverage and trim behavior validated on:
  - cone/frustum-like curved faces,
  - irregular trimmed planar face,
  - holed face.
- Result payloads (`mesh_faces`, `fabric_quads`, `boundary_loops`, `warp_weft_boundary_loops`) are boundary-consistent.
- No regression in determinism or core spacing/shear behavior.
