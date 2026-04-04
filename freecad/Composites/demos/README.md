# Composites Workbench Demos

This folder contains a FreeCAD generator for stable workbench feature demonstrations.

Run the generator with FreeCAD to create `.FCStd` demo files in `generated/`:

```bash
~/opt/FreeCAD-build/bin/FreeCADCmd -P . freecad/Composites/demos/generate_feature_demos.py
```

The generated demos cover these features:

- `Rosette`
- `FibreCompositeLamina`
- `HomogeneousLamina`
- `CompositeLaminate`
- `CompositeShell`
- `PartPlane`
- `Mould`

The following features were intentionally excluded from the generated demos because they produced null or default geometry in the current headless FreeCAD MCP run:

- `TexturePlan`
- `TransferLCS`
- `AlignFibreLCS`
- `Seam`
- `Stiffener`

`WrapLCS` was not included because it was not validated in this run.