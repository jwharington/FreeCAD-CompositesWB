# Fishnet Draping Workbench Handover

**Repo:** `git@github.com:jwharington/FreeCAD-CompositesWB.git`  
**Local checkout:** `~/opt/FreeCAD-CompositesWB`

## Goal
Implement an automatic **fishnet draping** workflow for composite fabrics in the FreeCAD Composites workbench.

The production drape solver should be implemented in **C++** for efficiency, with a thin Python-facing adapter for FreeCAD integration.

## Important current-state note
The existing draping path in this workbench is **not** the fishnet implementation:

- `freecad/Composites/tools/draper.py` currently uses `flatmesh.FaceUnwrapper`
- it is useful as an **illustrative / prototype-only** draping helper
- it should not be treated as the production fishnet solver

`CompositeShell` currently calls that draper path, so the new fishnet backend needs to be introduced behind a stable abstraction before the workbench can switch over cleanly.

## Recommended architecture

### 1. C++ fishnet kernel
Build the actual propagation / mapping algorithm in C++ so the expensive geometry work stays out of Python.

The kernel should own:
- node propagation logic
- surface traversal / neighborhood queries
- result generation for fabric points, orientation, and any strain-like metadata needed by the workbench
- algorithm parameters such as seed/origin, relaxation, step size, and fabric spacing

### 2. Python adapter layer
Keep FreeCAD-specific conversion and document-object plumbing in Python.

The adapter should:
- translate FreeCAD meshes / shapes into kernel inputs
- translate kernel output into FreeCAD-friendly result objects
- provide error handling for invalid geometry
- remain thin enough that the production algorithm still lives in C++

### 3. Workbench integration
Expose the fishnet drape workflow as a normal workbench command and document object.

The UI layer should:
- let the user select the shell / target surface
- set key fishnet parameters
- run the drape
- preview the resulting geometry in the document / 3D view

### 4. Testing
Add both unit and integration coverage.

- C++ unit tests should cover the core kernel on a small, simple mold
- FreeCAD integration tests should cover selection → command → result object → recompute
- keep the current illustrative draper path available for comparison while the migration happens

## GitHub issue breakdown
The work is already split into GitHub issues in dependency order:

1. **#14 — Add C++ fishnet draping kernel and unit tests**  
   Build the production fishnet solver core.

2. **#15 — Add Python adapter for fishnet drape results**  
   Convert FreeCAD inputs/outputs around the C++ core.

3. **#16 — Switch CompositeShell to the fishnet backend**  
   Move `CompositeShell` onto the new backend while keeping `tools/draper.py` as illustrative reference code.

4. **#17 — Add Fishnet drape command and preview UI**  
   Add the user-facing command / task panel / preview flow.

5. **#18 — Add integration tests and handover docs for fishnet draping**  
   Add real-FreeCAD integration coverage, sample geometry, and final documentation.

## Suggested implementation order
1. Add the C++ kernel first (#14).  
2. Add the Python adapter around it (#15).  
3. Switch the workbench backend in `CompositeShell` (#16).  
4. Add the UI / preview command (#17).  
5. Finish with integration tests and docs (#18).

## Notes for implementation
- Keep the current `draper.py` code path available as a prototype/illustration, but do not extend it into the production solver.
- Avoid putting the fishnet algorithm itself in Python if performance matters.
- Keep the FreeCAD document object model stable so downstream composite tools do not break when the backend changes.
- If C++ build scaffolding becomes a blocker, treat that as part of #14 rather than a separate branch of work.

## Risks
- FreeCAD topology operations can be fragile on complex shapes.
- The C++ extension/binding setup may take a little work because this repo is currently Python-first.
- Fishnet output may need tolerance tuning before it matches the existing visual workflows.
- The old draper and the new fishnet backend should not be mixed accidentally in production paths.

## Handover summary
This workbench should end up with a **C++ fishnet solver**, a **thin Python integration layer**, and a **user-facing FreeCAD command** that replaces the current illustrative draping path for production use.
