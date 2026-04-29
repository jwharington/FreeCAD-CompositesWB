# Fishnet Stitched Atlas Design

**Date:** 2026-04-29  
**Repository:** `FreeCAD-CompositesWB`  
**Status:** Draft design for implementation planning

## 1. Problem Statement

The fishnet draping plots now show a second 2D view for the solved drape, but the intended third pane for solid cases is still not a true stitched atlas. It is currently derived from the same flattened coordinates as the drape view, so the plot does not communicate where adjacent faces are stitched, where seams occur, or where the atlas must split into multiple charts.

The workbench needs a native, explicit atlas representation that can answer three questions:

1. What pieces of fabric are needed?
2. Which faces belong to each stitched piece?
3. Where are the unavoidable seams, joins, and chart breaks?

The atlas must be a first-class result of the solver, not an inference in plotting code.

## 2. Goals

### Primary goals

1. Make the stitched atlas a native solver output.
2. Preserve face adjacency and orientation continuity explicitly.
3. Auto-split into multiple charts when one connected atlas cannot be formed.
4. Record the exact face transitions where continuity breaks.
5. Render the third plot pane from atlas data rather than from the drape view.

### Secondary goals

1. Keep the existing `CompositeShell`, `TexturePlan`, and grid-rendering APIs stable.
2. Keep the Python fallback API aligned with the native solver output.
3. Preserve the current plot/report workflow and opt-in plotting behavior.
4. Make atlas failures actionable by identifying which regions require cuts or joins.

## 3. Non-Goals

This design does **not** attempt to:

- produce manufacturing-grade nesting or material optimization
- solve cutting patterns, marker layout, or layup planning
- redesign the shell draping UI
- remove the existing drape mesh view
- replace the current solver topology with a different geometric kernel

## 4. Current State

The current fishnet pipeline already provides:

- a native solver module under `freecad/Composites/_fishnet.cpp`
- a Python fallback module under `freecad/Composites/_fishnet.py`
- a Python draper adapter under `freecad/Composites/tools/fishnet_draper.py`
- integration plotting in `freecad/Composites/compositestests/plotting.py`
- shell-level compatibility through `CompositeShell.get_tex_coords()` and `CompositeShell.get_boundaries()`

The current third plot pane is only a visual duplicate of the flattened coordinates. It does not yet represent stitched atlas layout, chart breaks, or seam semantics.

## 5. Proposed Approach

### 5.1 Native atlas builder

Extend the solver result with a stitched-atlas builder that operates on the shell face graph.

Responsibilities:

- choose a root face per atlas chart
- propagate orientation across adjacency
- place neighboring faces into shared 2D chart space
- preserve edge continuity when orientation is compatible
- split into a new chart when a face cannot be placed without overlap or ambiguity
- record every chart boundary, seam, and break explicitly

The atlas builder should run in the native solver layer so the result is authoritative and testable.

### 5.2 Chart-level result model

The solver should emit a charted atlas rather than a single flat array.

Recommended result fields:

- `atlas_charts`
  - a list of charts
  - each chart contains its own atlas points, atlas quads, and face mapping
- `atlas_seams`
  - explicit seam edges and stitched joins
- `atlas_breaks`
  - face transitions where placement failed or a new chart was required
- `atlas_face_frames`
  - per-face 2D placement metadata in chart space
- `atlas_reasons`
  - human-readable reasons for chart splits or failed continuity

### 5.3 Plotting responsibilities

The plotting layer should become a renderer only.

Responsibilities:

- use atlas data for the third pane when chart data is present
- show each stitched chart with its own layout
- highlight seams and breaks explicitly
- keep the current drape mesh pane unchanged
- fall back gracefully if atlas data is unavailable

## 6. Atlas Placement Rules

### 6.1 One-piece stitching preferred

The builder should try to keep adjacent faces in a single chart whenever possible.

### 6.2 Continuity requirement

A face may be stitched to a neighboring face only when the shared edge orientation can be preserved consistently.

### 6.3 Failure means a chart split, not silence

If a face cannot be placed into the current chart, the solver must not guess.
It should:

1. end the current chart,
2. start a new chart,
3. record the transition reason,
4. continue solving the remaining connected region.

### 6.4 Explicit failure semantics

A placement failure means the current atlas cannot remain one connected piece under the solver’s rules.
That does **not** mean the entire shape is unsolvable. It means the shape needs multiple charts or fabric pieces.

### 6.5 User feedback requirement

The solver must preserve enough information to tell the user:

- which faces belong to which chart
- which face transition caused a split
- whether the split is due to orientation mismatch, hard geometry, or parameterization ambiguity
- where a cut or join would be required in the physical fabric

## 7. Data Flow

1. `CompositeShell` or the draper adapter sends shell geometry to the solver.
2. The native solver builds face adjacency and local face frames.
3. The atlas builder traverses the face graph and creates stitched charts.
4. The solver result returns charts, seams, breaks, and per-face chart metadata.
5. Python stores the result on the draper object.
6. Plotting uses atlas charts for the third pane.
7. `TexturePlan` and grid rendering continue to use the existing public methods.

## 8. Result Shape

The solver result should include the existing fields plus atlas metadata:

Existing fields to preserve:

- `valid`
- `error`
- `fabric_points`
- `fabric_quads`
- `boundary_loops`
- `mesh_points`
- `mesh_faces`
- `face_frames`
- `orientation_breaks`
- `parameters`

New atlas fields:

- `atlas_charts`
- `atlas_seams`
- `atlas_breaks`
- `atlas_face_frames`
- `atlas_reasons`

Each chart should be self-contained enough for plotting and downstream inspection.

## 9. Error Handling

Atlas failures should be explicit and inspectable.

Rules:

1. If a chart cannot absorb a neighboring face, the solver must record the break.
2. If the solver cannot place a face at all, it should start a new chart rather than silently dropping the face.
3. If atlas construction fails entirely, the result should still be valid enough to explain why.
4. Plotting should degrade gracefully when atlas data is incomplete.
5. The solver should keep the distinction between a recoverable chart split and a true geometry failure.

## 10. Plotting Behavior

The integration plot should use the atlas output as follows:

- **Source shape**: unchanged 3D view of the input solid or shell
- **Drape mesh**: the existing flattened net view
- **Unwrapped net**: the stitched atlas view built from `atlas_charts`

For solid cases, the third pane should show:

- chart outlines
- seam edges
- breaks or join candidates
- multiple charts if the shape cannot be represented as one piece

If only one chart exists, the third pane should still be a stitched atlas, not a duplicate of the drape view.

## 11. Testing Strategy

### 11.1 Atlas construction tests

Add coverage for:

- a simple planar face that yields one chart
- adjacent faces with smooth continuity that remain stitched
- a reversed or awkwardly parameterized face that forces a chart break
- a concave or stepped shell that requires multiple charts
- explicit seam and break reporting

### 11.2 Plotting regression tests

Add coverage for:

- the third pane rendering a distinct atlas layout
- multi-chart output drawing more than one chart
- seam and break overlays appearing in the plot
- solid integration cases continuing to render source shape and drape mesh correctly

### 11.3 Existing compatibility tests

Keep the current regression coverage intact for:

- planar square native solve
- cylinder patch native solve
- concave L-shape native solve
- step mesh native solve
- solid and shell integration tests
- `TexturePlan` compatibility

## 12. Rollout Plan

### Phase 1: native atlas data

Add charted atlas output to the solver result and keep the Python fallback aligned.

### Phase 2: plotting integration

Switch the third pane to render atlas charts and seam metadata.

### Phase 3: feedback semantics

Expose chart splits and join hints clearly in result metadata and test output.

### Phase 4: refinement

Tighten chart placement heuristics and improve the clarity of break reasons.

## 13. Success Criteria

This design is successful when:

- the third pane shows a true stitched atlas
- multi-face shells are split into charts when needed
- chart breaks and seam candidates are explicitly recorded
- the user can tell which parts need joins or cuts
- `CompositeShell`, `TexturePlan`, and grid rendering remain compatible
- native and integration tests cover the atlas behavior end to end

## 14. Relationship to Existing Fishnet Work

This design extends the existing fishnet solver work rather than replacing it.
It uses the already established face-frame and orientation-break machinery, but adds a charted atlas layer so plotting and feedback can reflect the true stitched fabric layout.
