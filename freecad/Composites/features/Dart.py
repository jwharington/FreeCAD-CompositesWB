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

        obj.addProperty(
            type="App::PropertyLinkGlobal",
            name="Mesh",
            group="Orthographic",
            doc="Mesh for orthotropic materials",
            hidden=True,
        )

        obj.addProperty(
            type="App::PropertyFloat",
            name="GapLength",
            group="Dimensions",
            doc="Gap length at cut",
        ).GapLength = 0.1

        obj.Mesh = obj.Document.addObject(
            "Mesh::Feature",
            "DrapeMesh",
        )

        super().__init__(obj)

    def execute(self, fp):
        edges = [e[0].getSubObject(e[1])[0] for e in fp.Edges]
        source = fp.Edges[0][0]

        if not edges:
            raise ValueError("missing edges")

        mesh = make_dart(
            shape=source.Shape,
            edges=edges,
            gap_length=fp.GapLength,
        )
        fp.Mesh.Mesh = mesh
        source.Visibility = False


class ViewProviderDart(VPCompositePart):

    def claimChildren(self):
        return [
            self.Object.Mesh,
        ]

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
