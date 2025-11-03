# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import FreeCADGui
from .. import (
    DART_TOOL_ICON,
)
from ..tools.dart import (
    make_dart,
)
from .VPCompositePart import VPCompositePart, CompositePartFP
from .Command import BaseCommand


class DartFP(CompositePartFP):
    def __init__(self, obj, edges=[]):

        obj.addProperty(
            "App::PropertyLinkSubList",
            "Edges",
            "References",
            "Edges",
            locked=True,
        ).Edges = edges

        super().__init__(obj)

    def execute(self, fp):
        edges = [e[0].getSubObject(e[1])[0] for e in fp.Edges]
        source = fp.Edges[0][0]

        if not edges:
            raise ValueError("missing edges")

        shape = make_dart(
            shape=source.Shape,
            edges=edges,
        )
        fp.Shape = shape
        source.Visibility = False


class ViewProviderDart(VPCompositePart):

    def claimChildren(self):
        return []

    def getIcon(self):
        return DART_TOOL_ICON


class CompositeDartCommand(BaseCommand):

    icon = DART_TOOL_ICON
    menu_text = "Dart"
    tool_tip = """Generate Dart edge.
        Select one or more edges of a shape.
        WORK-IN-PROGRESS"""
    sel_args = [
        {
            "key": "edges",
            "type": "Part::TopoShape",
            "array": True,
        },
    ]
    type_id = "Part::FeaturePython"
    instance_name = "Dart"
    cls_fp = DartFP
    cls_vp = ViewProviderDart


FreeCADGui.addCommand("Composites_Dart", CompositeDartCommand())
