# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import os
import FreeCAD
from os import path
from .version import __version__  # noqa

debug = False


MODULE_PATH = os.path.dirname(__file__)
ICONPATH = os.path.join(MODULE_PATH, "resources", "icons")
UIPATH = os.path.join(MODULE_PATH, "resources", "ui")
MATPATH = os.path.join(MODULE_PATH, "resources", "materials")

TEXTURE_PLAN_TOOL_ICON = path.join(ICONPATH, "TexturePlan.svg")
MOULD_TOOL_ICON = path.join(ICONPATH, "Mould.svg")
PART_PLANE_TOOL_ICON = path.join(ICONPATH, "PartPlane.svg")
SEAM_TOOL_ICON = path.join(ICONPATH, "Seam.svg")

LAMINATE_TOOL_ICON = path.join(ICONPATH, "Laminate.svg")
COMPOSITE_LAMINATE_TOOL_ICON = path.join(
    ICONPATH,
    "CompositeLaminate.svg",
)
HOMOGENEOUS_LAMINA_TOOL_ICON = path.join(
    ICONPATH,
    "HomogeneousLamina.svg",
)
FIBRE_COMPOSITE_LAMINA_TOOL_ICON = path.join(
    ICONPATH,
    "FibreCompositeLamina.svg",
)
COMPOSITE_SHELL_TOOL_ICON = path.join(ICONPATH, "CompositeShell.svg")
TRANSFER_LCS_TOOL_ICON = path.join(ICONPATH, "TransferLCS.svg")
WRAP_LCS_TOOL_ICON = path.join(ICONPATH, "WrapLCS.svg")
ALIGN_FIBRE_LCS_TOOL_ICON = path.join(ICONPATH, "AlignFibreLCS.svg")
WB_ICON = path.join(ICONPATH, "CompositesWB.svg")


TOL3D = 1e-7
TOL2D = 1e-9
if hasattr(FreeCAD.Base, "Precision"):
    TOL3D = FreeCAD.Base.Precision.confusion()
    TOL2D = FreeCAD.Base.Precision.parametric(TOL3D)

# Add materials to the user config dir
material_base = "BaseApp/Preferences/Mod/Material/Resources/Modules"
materials = FreeCAD.ParamGet("User parameter:{material_base}/CompositesWB")
materials.SetString(
    "ModuleIcon",
    COMPOSITE_LAMINATE_TOOL_ICON,
)
materials.SetString("ModuleDir", MATPATH)
# materials.SetString("ModuleModelDir", moddir)

# FreeCAD.addImportType("My own format (*.own)", "importOwn")
# FreeCAD.addExportType("My own format (*.own)", "exportOwn")

container_name = "CompositesContainer"


def is_comp_type(obj, type_id, proxy_type):
    if obj.TypeId != type_id:
        return False
    if not hasattr(obj, "Proxy"):
        return False
    if not obj.Proxy:
        return False
    if not hasattr(obj.Proxy, "Type"):
        return False
    if obj.Proxy.Type != proxy_type:
        return False
    return True


class _ViewProviderCompositesContainer:

    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return WB_ICON


def getCompositesContainer() -> FreeCAD.Document:
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

FreeCAD.__unit_test__ += ["TestCompositesApp"]
