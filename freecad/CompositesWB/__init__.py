import os
import FreeCAD
from os import path
from .version import __version__

ICONPATH = os.path.join(os.path.dirname(__file__), "resources", "icons")

WB_ICON = path.join(ICONPATH, "CompositeMouldCommand.svg")
TEXTURE_PLAN_TOOL_ICON = path.join(ICONPATH, "CompositeTexturePlanCommand.svg")
DRAPE_TOOL_ICON = path.join(ICONPATH, "CompositeTexturePlanCommand.svg")
MOULD_TOOL_ICON = path.join(ICONPATH, "CompositeMouldCommand.svg")
PART_PLANE_TOOL_ICON = path.join(ICONPATH, "CompositePartPlaneCommand.svg")
SEAM_TOOL_ICON = path.join(ICONPATH, "CompositeSeamCommand.svg")

LAMINATE_TOOL_ICON = path.join(ICONPATH, "FEM_MaterialLaminate.svg")
COMPOSITE_LAMINATE_TOOL_ICON = path.join(ICONPATH, "FEM_MaterialLaminate.svg")
HOMOGENEOUS_LAMINA_TOOL_ICON = path.join(ICONPATH, "FEM_MaterialLaminate.svg")
FIBRE_COMPOSITE_LAMINA_TOOL_ICON = path.join(
    ICONPATH,
    "FEM_MaterialLaminate.svg",
)

TOL3D = 1e-7
TOL2D = 1e-9
if hasattr(FreeCAD.Base, "Precision"):
    TOL3D = FreeCAD.Base.Precision.confusion()
    TOL2D = FreeCAD.Base.Precision.parametric(TOL3D)


# FreeCAD.addImportType("My own format (*.own)", "importOwn")
# FreeCAD.addExportType("My own format (*.own)", "exportOwn")

print(f"Composites Workbench {__version__}")
