# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import FreeCADGui
from .. import (
    STIFFENER_TOOL_ICON,
)
from ..tools.stiffener import (
    make_stiffener,
)
from .VPCompositeBase import VPCompositeBase, BaseFP
from .Command import BaseCommand


class StiffenerFP(BaseFP):
    def __init__(self, obj, source):

        obj.addProperty(
            "App::PropertyLink",
            "Source",
            "References",
            "Link to the shape",
            locked=True,
        ).Source = source

        obj.addProperty(
            "App::PropertyLinkSubList",
            "Edges",
            "References",
            "Edges",
            locked=True,
        ).Edges = []

        super().__init__(obj)

    def execute(self, fp):
        edges = [e[0].getSubObject(e[1])[0] for e in fp.Edges]

        if not edges:
            raise ValueError("missing edges")

        shape = make_stiffener(
            support=fp.Source.Shape,
            edges=edges,
        )
        fp.Shape = shape


class ViewProviderStiffener(VPCompositeBase):

    def claimChildren(self):
        return [self.Object.Source]

    def getIcon(self):
        return STIFFENER_TOOL_ICON

    def attach(self, vobj):
        self.Object = vobj.Object
        self.ViewObject = vobj

    def getDisplayModes(self, obj):
        modes = []
        return modes

    def getDefaultDisplayMode(self):
        return "Flat Lines"

    def setDisplayMode(self, mode):
        return mode


class CompositeStiffenerCommand(BaseCommand):

    icon = STIFFENER_TOOL_ICON
    menu_text = "Stiffener"
    tool_tip = "Generate stiffener. WORK-IN-PROGRESS"
    sel_args = [
        {
            "key": "source",
            "type": "Part::Feature",
        },
    ]
    type_id = "Part::FeaturePython"
    instance_name = "Stiffener"
    cls_fp = StiffenerFP
    cls_vp = ViewProviderStiffener


FreeCADGui.addCommand("Composites_Stiffener", CompositeStiffenerCommand())
