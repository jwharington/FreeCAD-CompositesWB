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
from .VPCompositeBase import VPCompositeBase
from .Command import BaseCommand


class SeamFP:
    def __init__(self, obj):

        obj.addProperty(
            "App::PropertyLink",
            "Source",
            "References",
            "Link to the shape",
            locked=True,
        ).Source = None

        obj.addProperty(
            "App::PropertyLinkSubList",
            "Edges",
            "References",
            "Edges",
            locked=True,
        ).Edges = []

        obj.addProperty(
            "App::PropertyLength",
            "Overlap",
            "Dimension",
            "Overlap length",
            locked=True,
        ).Overlap = "10.0 mm"

        obj.Proxy = self

    def onChanged(self, fp, prop):
        return

    def execute(self, fp):
        edges = [e[0].getSubObject(e[1])[0] for e in fp.Edges]

        shape = make_edge_seam(
            shape=fp.Source.Shape,
            edges=edges,
            overlap=fp.Overlap,
        )
        fp.Shape = shape

    def onDocumentRestored(self, fp):
        fp.recompute()


class ViewProviderSeam(VPCompositeBase):

    def claimChildren(self):
        return [self.Object.Source]

    def getIcon(self):
        return SEAM_TOOL_ICON


class CompositeSeamCommand(BaseCommand):

    icon = SEAM_TOOL_ICON
    menu_text = "Seam"
    tool_tip = "Generate seam edge. WORK-IN-PROGRESS"
    sel_args = [
        # {
        #     "key": "source",
        #     "type": "Part::Feature",
        # },
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
