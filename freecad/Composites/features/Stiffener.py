# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from FreeCAD import Vector
import FreeCADGui
from .. import (
    STIFFENER_TOOL_ICON,
)
from ..tools.stiffener import (
    make_stiffener,
    StiffenerAlignment,
)
from .VPCompositePart import (
    VPCompositePart,
    CompositePartFP,
)
from .Command import BaseCommand


class StiffenerFP(CompositePartFP):
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
            "App::PropertyBool",
            "MirrorX",
            "Layout",
            "Mirror profile in X direction",
        ).MirrorX = False

        obj.addProperty(
            "App::PropertyBool",
            "MirrorY",
            "Layout",
            "Mirror profile in Y direction",
        ).MirrorY = False

        obj.addProperty(
            "App::PropertyLink",
            "Profile",
            "Dimensions",
            "Profile section of the stiffener",
        ).Profile = profile

        super().__init__(obj)

    def execute(self, fp):

        alignment = StiffenerAlignment(
            direction=fp.Direction,
            flip_x=fp.MirrorX,
            flip_y=fp.MirrorY,
        )

        shape, tools = make_stiffener(
            support=fp.Support.Shape,
            plan=fp.Plan,
            profile=fp.Profile,
            alignment=alignment,
        )
        fp.Shape = shape
        self.tools = tools

        fp.Plan.Visibility = False
        fp.Support.Visibility = False
        fp.Profile.Visibility = False


class ViewProviderStiffener(VPCompositePart):

    def claimChildren(self):
        return [self.Object.Support, self.Object.Plan, self.Object.Profile]

    def getIcon(self):
        return STIFFENER_TOOL_ICON


class CompositeStiffenerCommand(BaseCommand):

    icon = STIFFENER_TOOL_ICON
    menu_text = "Stiffener"
    tool_tip = """Generate stiffener.
        Select a sketch for the plan layout, support feature,
        and profile sketch.
        WORK-IN-PROGRESS"""
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
