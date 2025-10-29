# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from FreeCAD import Vector
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
    def __init__(self, obj, support=None, plan=None, profile=None):

        obj.addProperty(
            "App::PropertyLink",
            "Support",
            "References",
            "Link to the shape",
            locked=True,
        ).Support = support

        obj.addProperty(
            "App::PropertyLink",
            "Plan",
            "Layout",
            "Plan layout",
            locked=True,
        ).Plan = plan

        obj.addProperty(
            "App::PropertyVector",
            "Direction",
            "Layout",
            "Projection direction",
        ).Direction = Vector(0, 0, 1)

        obj.addProperty(
            "App::PropertyLink",
            "Profile",
            "Dimensions",
            "Profile section of the stiffener",
        ).Profile = profile

        super().__init__(obj)

    def execute(self, fp):
        shape = make_stiffener(
            support=fp.Support.Shape,
            plan=fp.Plan,
            profile=fp.Profile,
            direction=fp.Direction,
        )
        fp.Shape = shape

        fp.Plan.Visibility = False
        fp.Support.Visibility = False
        fp.Profile.Visibility = False


class ViewProviderStiffener(VPCompositeBase):

    def claimChildren(self):
        return [self.Object.Support, self.Object.Plan, self.Object.Profile]

    def getIcon(self):
        return STIFFENER_TOOL_ICON

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


class CompositeStiffenerCommand(BaseCommand):

    icon = STIFFENER_TOOL_ICON
    menu_text = "Stiffener"
    tool_tip = "Generate stiffener. WORK-IN-PROGRESS"
    sel_args = [
        {
            "key": "plan",
            "type": "Sketcher::SketchObject",
        },
        {
            "key": "support",
            "type": "Part::Feature",
        },
        {
            "key": "profile",
            "type": "Sketcher::SketchObject",
        },
    ]
    type_id = "Part::FeaturePython"
    instance_name = "Stiffener"
    cls_fp = StiffenerFP
    cls_vp = ViewProviderStiffener


FreeCADGui.addCommand("Composites_Stiffener", CompositeStiffenerCommand())
