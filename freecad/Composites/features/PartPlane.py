# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from FreeCAD import Vector
import FreeCADGui
from .. import (
    PART_PLANE_TOOL_ICON,
)
from ..tools.part_plane import (
    # make_part_plane,
    # make_part_plane2,
    make_part_plane3,
)
from .Command import BaseCommand


class PartPlaneFP:
    def __init__(self, obj, source):
        obj.addProperty(
            "App::PropertyLink",
            "Source",
            "PartPlane",
            "Link to the shape",
            locked=True,
        ).Source = source

        obj.addProperty(
            "App::PropertyLength",
            "Inset",
            "PartPlane",
            "Inset length",
            locked=True,
        ).Inset = "0.01 mm"

        obj.addProperty(
            "App::PropertyBool",
            "Ruled",
            "PartPlane",
            "Ruled",
            locked=True,
        ).Ruled = True

        obj.addProperty(
            "App::PropertyVector",
            "ViewDir",
            "ReflectLines",
            "View direction",
        ).ViewDir = Vector(0, 0, 1)

        obj.Proxy = self

    def onChanged(self, fp, prop):
        return

    def execute(self, fp):
        shape = make_part_plane3(
            fp.Source.Shape,
        )
        fp.Shape = shape


class ViewProviderPartPlane:
    def __init__(self, obj):
        self.obj = obj
        obj.Proxy = self

    def onChanged(self, obj, prop):
        return

    def updateData(self, fp, prop):
        return

    def claimChildren(self):
        return []  # [self.obj.Object.Source]

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class CompositePartPlaneCommand(BaseCommand):

    icon = PART_PLANE_TOOL_ICON
    menu_text = "Part plane"
    tool_tip = "Generate two part mould plane. WORK-IN-PROGRESS"
    sel_args = [
        {
            "key": "source",
            "type": "Part::Feature",
        },
    ]
    type_id = "Part::FeaturePython"
    instance_name = "PartPlane"
    cls_fp = PartPlaneFP
    cls_vp = ViewProviderPartPlane


FreeCADGui.addCommand("Composites_PartPlane", CompositePartPlaneCommand())
