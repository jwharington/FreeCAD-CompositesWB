# FreeCAD Composite Mould Workbench — Handover Plan

**Status:** Core MVP slice implemented; refinement and hardening remaining  
**Scope:** Automatic geometry synthesis for composite tooling, starting with two-piece molds but designed to extend to multipart molds later.  
**Local source checkout:** `~/opt/FreeCAD`  
**Note:** The mould-related code currently in this repository is illustrative/prototype-only and should be treated as geometry exploration, not as the final solver architecture.

## 1. Goal
Build a custom FreeCAD workbench that analyzes a composite part’s geometry and proposes mold tooling geometry automatically.

Implementation should happen in this repository, with integration tested against a local FreeCAD build.

As of the current work on this repository, the first end-to-end MVP slice has already been implemented and validated in FreeCAD integration tests. The remaining work is to harden the heuristics, improve geometric fidelity, and extend the multipart architecture.

The first release should:
- accept a solid part model
- infer or let the user choose a draw direction
- detect undercuts and negative draft regions
- propose split lines and parting surfaces
- generate two mold halves as the MVP
- keep the architecture extensible for 3+ piece decomposition later

## 2. Problem framing
Composite tooling is not just “split a part in half.” The tool must also account for:
- draft and demouldability
- closed-section geometry
- flanges and stock allowance
- alignment / clamping features
- large-tool structural constraints

The workbench should therefore separate **analysis** from **synthesis**:
1. analyze the part for moldability
2. propose a tooling strategy
3. generate candidate mold solids
4. validate the result

The current mould helpers began as illustrative examples of this problem space, and the workbench now layers a working MVP analysis/synthesis flow on top of that prototype boundary.

## 3. Recommended implementation strategy
### Recommended path
Start with a **two-piece mold capability inside the existing workbench**, while keeping the internal model multipart-ready.

### Why
- delivers a useful MVP quickly
- keeps UI and solver boundaries clean
- avoids painting the project into a two-part-only corner

### Issue tracking
Implementation is broken into GitHub issues rather than tracked as one large effort. The current tracer-bullet breakdown for this plan was stored in GitHub issues and accessed with the `gh` command-line tool. The initial mould MVP slices are complete; the remaining mould work should be tracked as follow-on issues or milestones.

## 4. Core algorithms to implement
### 4.1 Draw-direction analysis
Given a candidate pull direction, score the part for moldability.

Outputs:
- candidate directions
- visible / non-visible regions
- undercut regions
- draft violations

### 4.2 Undercut detection
For each face or face patch:
- classify whether it is visible from the draw direction
- flag negative draft / blocking geometry
- group problem areas into candidate parting regions

### 4.3 Parting-line proposal
Use a hybrid strategy:
- simple regions: extrusion-based split lines / parting surfaces
- complex regions: subdivision-based surface completion

### 4.4 Parting-surface generation
Generate a separating surface that:
- closes the tooling split
- avoids interlock between mold halves
- remains compatible with downstream machining or export

### 4.5 Multipart-ready decomposition model
Represent the tool as a graph or plan rather than a fixed two-solid result.

This allows later extension to:
- removable mandrels
- 3+ piece tools
- internal tooling for closed sections

## 5. FreeCAD workbench architecture
### 5.1 Package layout
Suggested structure:
- `freecad/Composites/tools/` for geometry, analysis, and synthesis helpers
- `freecad/Composites/features/` for FeaturePython wrappers, commands, and view providers
- `freecad/Composites/resources/` for icons and UI assets
- `freecad/Composites/compositestests/` for geometry and integration tests

### 5.2 Logical modules
#### Geometry analysis module
Responsibilities:
- draw direction scoring
- draft checks
- undercut classification
- visibility / accessibility analysis

#### Mold synthesis module
Responsibilities:
- split-line creation
- parting-surface generation
- tool-half solid generation
- future multipart decomposition

#### Validation module
Responsibilities:
- interference checks
- closure checks
- draft conformity checks
- report generation

#### FeaturePython / command module
Responsibilities:
- workbench commands
- task panel / selection handling
- preview / apply / cancel flow
- result objects in the FreeCAD document

## 6. User workflow
### Current MVP workflow
1. User selects a solid.
2. Workbench evaluates candidate draw directions.
3. The analysis object stores the best direction, heuristic score, undercut/draft summary, parting surface preview, two mold-half previews, and validation report.
4. User can inspect the resulting document object state in FreeCAD.

### Later workflow
- same analysis front-end
- optional refinement into 3+ mold pieces
- optional internal mandrel generation for closed sections


## 7. Data model
Use explicit objects instead of hidden procedural state.

### Suggested object types
- `MouldAnalysis`
- `DrawDirectionCandidate`
- `UndercutRegion`
- `PartingCurve`
- `PartingSurface`
- `MouldHalf`
- `MouldDecompositionPlan`
- `MouldValidationReport`

### Why this matters
A plan object makes it easier to:
- inspect intermediate results
- save partial progress
- extend from two-piece to multipart later
- test solver stages independently

For the MVP, the plan can represent a two-piece split, but it should not hard-code that assumption.

## 8. Extension points for multipart molds
Design these hooks from day one:
- multiple draw directions
- multiple split surfaces
- decomposition graph / tree
- per-piece validation
- assembly constraints
- locking / alignment features

Do not hard-code the solver to exactly two halves if multipart support is a future requirement.

## 9. Validation and testing
### Geometry tests
- simple convex part
- part with shallow draft
- part with a clear undercut
- closed-section composite-like shape
- large shell-like surface

### Integration tests
- workbench loads in a real FreeCAD session
- command creates analysis object
- command generates parting proposal
- command writes output solids to the document
- objects recompute cleanly after document reload/recompute where applicable

### Acceptance checks
- workbench can analyze a sample part without crashing
- undercuts are reported consistently
- two-piece result can be generated for the MVP case
- validation report is produced for success and failure cases
- architecture does not block multipart extension
- the existing MVP slice remains usable as the implementation basis for future refinement

## 10. Risks
- Exact optimal multipart decomposition may be too hard for MVP.
- FreeCAD topology operations can be fragile on complex shapes.
- Draft / visibility classification may need tolerance tuning.
- Composite tooling practice may require case-specific heuristics more than exact algorithms.

## 11. Suggested delivery phases
### Phase 0: formalize the prototype boundary
- treat current mould and part-plane helpers as illustrative geometry experiments
- identify which pieces, if any, are reusable
- define the stable solver interface

### Phase 1: harden the MVP analysis engine
- improve draw-direction scoring beyond bounding-box heuristics
- replace slice-area undercut detection with face/visibility-based classification
- tighten draft reporting and tolerances
- keep the current document-object contract stable

### Phase 2: harden synthesis and validation
- improve parting-surface generation
- improve mold-half generation robustness
- add stronger validation checks for null / fragile shapes
- add richer reporting and failure diagnostics

### Phase 3: multipart-ready refactor
- decomposition plan model
- multiple split surfaces
- piece graph / assembly constraints

### Phase 4: composite-tooling details
- flanges
- stock allowance
- alignment / clamping features
- removable mandrel support

## 12. Handover summary
The recommended implementation is a **two-piece-first FreeCAD workbench** with a **multipart-capable internal architecture**.

The workbench should expose:
- analysis commands
- synthesis commands
- validation commands
- a clear document object model

Implementation tracking was managed through GitHub issues rather than a single large ticket. The initial mould MVP work is complete in issues #8–#13.

The most important design choice is to keep the solver generic enough to support future multipart composite tooling while still shipping an immediately useful two-piece MVP. The current mould-related modules started as illustrative geometry experiments, and the repo now contains a working MVP built on top of that prototype boundary.
