# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import FreeCADGui
from .. import (
    SEAM_TOOL_ICON,
)
from ..tools.seam import (
    make_join_seam,
    make_edge_seam,
)
from .VPCompositeBase import VPCompositeBase, BaseFP
from .Command import BaseCommand


class SeamFP(BaseFP):
    def __init__(self, obj, edges=[]):

        obj.addProperty(
            "App::PropertyLinkSubList",
            "Edges",
            "References",
            "Edges",
            locked=True,
        ).Edges = edges

        obj.addProperty(
            "App::PropertyLength",
            "Overlap",
            "Dimension",
            "Overlap length",
            locked=True,
        ).Overlap = "10.0 mm"

        super().__init__(obj)

    def execute(self, fp):
        edges = [e[0].getSubObject(e[1])[0] for e in fp.Edges]
        source = fp.Edges[0][0]

        if not edges:
            raise ValueError("missing edges")

        shape = make_edge_seam(
            shape=source.Shape,
            edges=edges,
            overlap=fp.Overlap,
        )
        fp.Shape = shape
        source.Visibility = False


class ViewProviderSeam(VPCompositeBase):

    def claimChildren(self):
        return []

    def getIcon(self):
        return SEAM_TOOL_ICON

    def attach(self, vobj):
        self.Object = vobj.Object
        self.ViewObject = vobj

    def getDisplayModes(self, obj):
        modes = []
        return modes

    def getDefaultDisplayMode(self) -> str:
        return "Flat Lines"

    def setDisplayMode(self, mode):
        return mode


class CompositeSeamCommand(BaseCommand):

    icon = SEAM_TOOL_ICON
    menu_text = "Seam"
    tool_tip = "Generate seam edge. WORK-IN-PROGRESS"
    sel_args = [
        {
            "key": "edges",
            "type": "Part::TopoShape",
            "array": True,
        },
    ]
    type_id = "Part::FeaturePython"
    instance_name = "Seam"
    cls_fp = SeamFP
    cls_vp = ViewProviderSeam


FreeCADGui.addCommand("Composites_Seam", CompositeSeamCommand())


# sel = FreeCADGui.Selection.getSelectionEx()
# if len(sel) == 1:
#     sel = [sel[0].SubObjects[0], sel[0].SubObjects[1]]
# elif len(sel) == 2:
#     sel = [sel[0].SubObjects[0], sel[1].SubObjects[0]]
# else:
#     return None
# return sel
