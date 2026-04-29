# Fishnet Draping Workbench Design

## Summary

Replace the current prototype draping path in the Composites workbench with a production fishnet draping backend implemented in C++, while preserving the public `CompositeShell` document-object API.

This is a **hard replacement**:

- production code must not depend on `flatmesh.FaceUnwrapper`
- `CompositeShell` stays the user-facing workbench entrypoint
- downstream consumers such as `TexturePlan` and fibre-orientation helpers keep using the same `CompositeShell` methods
- the existing `tools/draper.py` module stays in the repo as reference/prototype code only

The main design goal is **API stability**, not numerical equivalence with the current prototype draper.

## Goals

1. Implement the drape solver in C++ so the expensive propagation work is not done in Python.
2. Keep FreeCAD document-object plumbing in Python.
3. Preserve the current `CompositeShell` API used by `TexturePlan`, grid rendering, and fibre/orientation analysis.
4. Provide a usable FreeCAD UI flow for creating and previewing fishnet drapes.
5. Add tests at both the native-solver level and the FreeCAD integration level.

## Non-goals

1. Do not keep `flatmesh` as a production fallback.
2. Do not try to match the current prototype solver numerically.
3. Do not create a second production shell object type when `CompositeShell` already satisfies the workbench API.
4. Do not move FreeCAD-specific document-object logic into C++.
5. Do not refactor unrelated composite features.

## Current state

`CompositeShellFP` currently constructs `tools.draper.Draper`, which in turn uses `flatmesh.FaceUnwrapper` to generate flattened fabric points and strains.

That prototype path is useful for understanding the intended shape of the data, but it is not the production architecture we want to keep. The current design couples the shell feature directly to a Python draper implementation, which makes it hard to replace the solver cleanly.

Several existing consumers rely on the current `CompositeShell` API:

- `TexturePlan` calls `get_boundaries()`
- grid display calls `get_tex_coords()`
- fibre analysis uses `get_strains()`
- orientation/LCS tools call `get_lcs()` and `get_lcs_at_point()`

The replacement must keep those method names and overall behavior available.

## Proposed architecture

### 1. Native C++ fishnet solver

Add a native module that owns the actual fishnet propagation algorithm.

Responsibilities:

- build and traverse adjacency on the tessellated shell mesh
- propagate the fishnet pattern across the surface
- generate flattened fabric coordinates for each node
- derive boundary loops from the solved net
- compute per-face strain-like metadata
- accept solver parameters such as seed/origin handling, relaxation, step size, and fabric spacing

The solver should return a compact, Python-friendly result structure. It should not know anything about FreeCAD document objects, GUI state, or FeaturePython classes.

#### Native module shape

Use a small CPython extension built from the repository source tree. Keep the interface narrow so the Python layer remains thin.

Recommended exported shape:

- `solve(mesh_points, mesh_faces, parameters) -> result`
- result contains:
  - solved fabric node coordinates
  - boundary loops
  - per-face strain data
  - validity / error information

The exact binding mechanism can stay simple and direct; the important part is that the production algorithm lives in C++.

### 2. Python adapter layer

Add a Python wrapper around the native solver.

Responsibilities:

- translate FreeCAD meshes into native solver input
- translate solver output back into FreeCAD-friendly vectors, wires, and arrays
- keep the public draping methods used by `CompositeShell`
- centralize input validation and error messages

This adapter should become the new production draper-facing abstraction. It may be a new module such as `freecad/Composites/tools/fishnet_draper.py`.

The adapter should expose the same operational surface that `CompositeShell` needs today:

- `isValid()`
- `get_tex_coords(offset_angle_deg=0)`
- `get_boundaries(offset_angle_deg=0)`
- `get_lcs(tris)`
- `get_lcs_at_point(center)`
- `get_tex_coord_at_point(point, offset_angle_deg=0)`
- `get_strains()`

Internally it may reuse existing math helpers such as `mesh_util.py` for coordinate transforms, but the solver itself must be native.

### 3. `CompositeShell` remains the public document object

Keep `CompositeShell` as the workbench’s production shell object and command entrypoint.

Responsibilities:

- hold the support, laminate, LCS, and rosette links already used by the workbench
- own a generated mesh feature for display and analysis
- compute drape results through the new fishnet adapter
- expose the same helper methods that downstream tools already call

#### Feature properties

Keep the existing properties and add a small set of fishnet-specific configuration fields.

Existing properties to preserve:

- `Support`
- `LocalCoordinateSystem`
- `Rosette`
- `Laminate`
- `MaxLength`
- `Mesh`

Recommended new properties:

- `FabricSpacing` — target spacing between fishnet nodes
- `RelaxWeight` — relaxation damping for propagation
- `SolveSteps` — number of propagation / relaxation passes
- `DrapeStatus` — short status string such as `Ready` or `Error`
- `DrapeError` — error message for invalid geometry or solver failure

The shell object should still recompute when the relevant links or parameters change.

#### Execution flow

1. `execute()` validates `Support` and `Laminate`.
2. Build a tessellated mesh from the support shape using the existing mesh helper.
3. Create the fishnet adapter with the mesh, LCS/rosette context, and solver parameters.
4. On success:
   - store the generated mesh in the `Mesh` feature
   - cache the fishnet result for `get_tex_coords()`, `get_boundaries()`, and `get_strains()`
   - set `DrapeStatus = "Ready"`
   - clear `DrapeError`
5. On failure:
   - clear the cached result
   - set `DrapeStatus = "Error"`
   - write the error text into `DrapeError`
   - avoid calling production code through `flatmesh`

The feature should fail visibly and predictably rather than silently dropping into the old solver path.

### 4. UI and preview flow

Keep `Composites_CompositeShell` as the user-facing command, but give its view provider a fishnet-oriented task panel and preview flow.

This keeps the document object stable while still giving users a place to tune draping parameters.

Responsibilities of the UI layer:

- expose the new fishnet parameters in a task panel
- keep the support / laminate / LCS / rosette selection contract unchanged
- trigger recompute when the user accepts or edits parameters
- reuse the current grid shader / strain visualization for preview

A separate production object type is not needed because `CompositeShell` already serves that role and is referenced throughout the workbench.

Suggested UI artifacts:

- `freecad/Composites/taskpanels/task_fishnet_drape.py`
- `freecad/Composites/resources/ui/FishnetDrape.ui`

The preview can remain the existing mesh overlay and strain coloring in the 3D view.

## Data flow

### Input

The solver input should come from the current FreeCAD shell setup:

- support shape
- tessellated shell mesh
- local coordinate system or rosette
- fishnet solver parameters

### Processing

- Python prepares a mesh and reference frame.
- C++ performs propagation and fabric mapping.
- Python wraps the result into the current `CompositeShell` API.

### Output

The shell object exposes:

- flattened fabric coordinates for grid rendering
- boundary wires for texture-plan generation
- per-face strain arrays for analysis coloring
- local coordinate system/orientation helpers for downstream tools

## Error handling

The fishnet work should be explicit about invalid geometry and solver failures.

Rules:

1. Bad support geometry or empty mesh input should produce `DrapeStatus = "Error"` and a useful `DrapeError` message.
2. Solver failures must not fall back to `flatmesh`.
3. `CompositeShell` helper methods should return `None` when no valid result exists, matching the current calling pattern.
4. `TexturePlan` and other consumers should keep working on valid shells and skip invalid shells cleanly.

## Testing strategy

### Native solver tests

Add C++ unit tests for the fishnet kernel.

Minimum coverage:

- a simple flat mold solves successfully
- a small curved mold produces a valid fabric mapping
- boundary extraction returns the expected number of loops
- a planar case produces near-zero strain
- invalid or degenerate input returns a controlled error

### Python adapter tests

Add unit tests for the adapter layer.

Minimum coverage:

- FreeCAD mesh input is converted into native solver input correctly
- solver output becomes Vector / wire / array data in the expected shape
- offset-angle handling still works in `get_tex_coords()` and `get_boundaries()`
- invalid solver results propagate into `isValid()` / `DrapeStatus` correctly

### Feature and integration tests

Update the existing FeaturePython and real-FreeCAD integration tests.

Minimum coverage:

- `CompositeShellFP` still builds correctly with its existing selection contract
- the production code path no longer requires `flatmesh`
- `TexturePlan` can still consume `CompositeShell.get_boundaries()`
- a real FreeCAD document can create a shell, recompute it, and produce a mesh/result object
- the shell object exposes strain data for display modes

The integration tests should verify the end-to-end path in a real FreeCAD process, not mocks.

## Packaging and build wiring

The repository is currently Python-first, so the native solver needs build wiring added alongside the code.

Recommended approach:

- keep the project structure under the existing `freecad/Composites` package
- add the native source files under a dedicated subdirectory
- extend `setup.py` so the extension builds from source
- keep the Python adapter importable from the existing package layout

The implementation should avoid introducing a heavyweight new build system unless the native module proves impossible to build cleanly through setuptools.

## Compatibility notes

- `tools/draper.py` remains as reference/prototype code only.
- No production module should import `flatmesh` after the migration.
- `CompositeShell` remains the public API surface for `TexturePlan`, fibre helpers, and visualization.
- The workbench command name can remain `Composites_CompositeShell` so existing toolbar and selection workflows do not need to change.

## Implementation sequence

1. Add the native fishnet kernel and its tests.
2. Add the Python adapter around the native kernel.
3. Switch `CompositeShell` to the new adapter and add explicit error/status reporting.
4. Add the task panel / UI controls and preview flow.
5. Update integration tests and documentation.

## Acceptance criteria

The work is complete when all of the following are true:

- `CompositeShell` no longer relies on `flatmesh.FaceUnwrapper` in production code
- the fishnet solver runs in C++
- the Python layer keeps the existing draping API stable
- the command still creates a shell object that `TexturePlan` and other consumers can use
- the UI exposes fishnet parameters and a useful preview
- native and FreeCAD-level tests cover the path end to end
