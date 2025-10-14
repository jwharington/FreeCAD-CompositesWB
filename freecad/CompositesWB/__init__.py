import os
import FreeCAD
from os import path
from .version import __version__

MODULE_PATH = os.path.dirname(__file__)
ICONPATH = os.path.join(MODULE_PATH, "resources", "icons")
UIPATH = os.path.join(MODULE_PATH, "resources", "ui")
MATPATH = os.path.join(MODULE_PATH, "resources", "materials")

TEXTURE_PLAN_TOOL_ICON = path.join(ICONPATH, "CompositeTexturePlanCommand.svg")
DRAPE_TOOL_ICON = path.join(ICONPATH, "CompositeTexturePlanCommand.svg")
MOULD_TOOL_ICON = path.join(ICONPATH, "CompositeMouldCommand.svg")
PART_PLANE_TOOL_ICON = path.join(ICONPATH, "CompositePartPlaneCommand.svg")
SEAM_TOOL_ICON = path.join(ICONPATH, "CompositeSeamCommand.svg")

LAMINATE_TOOL_ICON = path.join(ICONPATH, "FEM_MaterialLaminate.svg")
COMPOSITE_LAMINATE_TOOL_ICON = path.join(
    ICONPATH,
    "FEM_MaterialCompositeLaminate.svg",
)
HOMOGENEOUS_LAMINA_TOOL_ICON = path.join(
    ICONPATH,
    "FEM_MaterialHomogeneousLamina.svg",
)
FIBRE_COMPOSITE_LAMINA_TOOL_ICON = path.join(
    ICONPATH,
    "FEM_MaterialFibreCompositeLamina.svg",
)
COMPOSITE_SHELL_TOOL_ICON = path.join(ICONPATH, "CompositeShell.svg")
WB_ICON = path.join(ICONPATH, "CompositesWB.svg")


TOL3D = 1e-7
TOL2D = 1e-9
if hasattr(FreeCAD.Base, "Precision"):
    TOL3D = FreeCAD.Base.Precision.confusion()
    TOL2D = FreeCAD.Base.Precision.parametric(TOL3D)

# Add materials to the user config dir
materials = FreeCAD.ParamGet(
    "User parameter:BaseApp/Preferences/Mod/Material/Resources/Modules/CompositesWB"
)
materials.SetString(
    "ModuleIcon",
    COMPOSITE_LAMINATE_TOOL_ICON,
)
materials.SetString("ModuleDir", MATPATH)
# materials.SetString("ModuleModelDir", moddir)

# FreeCAD.addImportType("My own format (*.own)", "importOwn")
# FreeCAD.addExportType("My own format (*.own)", "exportOwn")

container_name = "CompositesContainer"


class _ViewProviderCompositesContainer:

    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return WB_ICON


def getCompositesContainer():
    for obj in FreeCAD.ActiveDocument.Objects:
        if obj.Name == container_name:
            return obj

    obj = FreeCAD.ActiveDocument.addObject(
        "App::DocumentObjectGroupPython",
        container_name,
    )
    if not obj:
        return None
    obj.Label = "Composites"
    if FreeCAD.GuiUp:
        _ViewProviderCompositesContainer(obj.ViewObject)
    return obj


# def getDocumentCompositeLaminates():
#     for obj in FreeCAD.ActiveDocument.Objects:
#         if obj.Name == container_name:
#             res = []
#             for o in obj.Group:
#                 if o.isDerivedFrom("App::FeaturePython"):
#                     res.append(o)
#             return res
#     return []
