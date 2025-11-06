This is very much a work in progress.  A lot is subject to change or refactoring.
Lots of code needs unit testing and handling input errors.

This requires a modified version of FreeCAD, mainly to support FEM analysis.
  https://github.com/jwharington/FreeCAD/tree/fem-orthotropic

Current capabilities:
- Local coordinate system with orthotropic materials in FEM solver
- LCS varies across the laminate shell by draping material
- Visualisation of fibre orientation across the part 
- Visualisation of fabric draping strains across the part
- Tools for managing fibre orientations across cut lines like seams etc; aligning zero fibres 
- Elements for fibre composite, homogeneous composite lamina and laminates, cores
- Classical Laminate Theory merging of laminates
- Various material fabrics (uni, bidirectional etc)
- Tools for cutting darts and creating seam/overlap/transition regions
- FEM stress exposure factor calculations including stress/strain/Tsai-hill
- Construction of aligned texture plans for layup
- Analysis tools such as average fibre length, % of plies in each orientation
- Tools for constructing stiffeners with custom profiles
- Some preliminary work on constructing moulds and part lines


TODO:
- Refactoring to allow use of lower-level code without FeaturePython objects/gui
- Design rules
- Hybrid (2 fibre material) fabrics
- Failure modes implement as plug in to FEM
- CompositeShell should have code sensitive to whether laminate is Fibre
- Seam detection and splitting when unwrap fails or high strain
  - Mesh_PolyCut
- Scale expand drape if positive linear strain
  .scale
- TexturePlan
  - add easement
  - add overlaps at darts?
  
Terminology:
- splice
- butt joint
- joint

 