# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import FreeCAD
import FreeCADGui
import Part
from .. import (
    ROSETTE_TOOL_ICON,
)
from .VPCompositeBase import (
    VPCompositeBase,
    CompositeBaseFP,
)
from .Command import BaseCommand


def _origin_from_support(fp):
    """Return (position, rotation) from the Support property.

    Handles vertex, edge (midpoint), and face (parametric centre).
    Returns (FreeCAD.Vector(0,0,0), FreeCAD.Rotation()) when no support is set.
    """
    if not fp.Support:
        return FreeCAD.Vector(0.0, 0.0, 0.0), FreeCAD.Rotation()

    (sup, sub) = fp.Support
    geom_list = sup.getSubObject(sub)
    if geom_list is None or len(geom_list) == 0:
        raise ValueError("Support sub-object could not be resolved")
    geom = geom_list[0]

    rotation = FreeCAD.Rotation()

    match type(geom):
        case Part.Vertex:
            position = geom.Point
        case Part.Edge:
            t = geom.getParameterByLength(0.5 * geom.Length)
            position = geom.valueAt(t)
        case Part.Face:
            u0, u1, v0, v1 = geom.ParameterRange
            position = geom.valueAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)
            normal = geom.normalAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)
            rotation = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), normal)
        case _:
            raise ValueError(f"Unhandled Support type: {type(geom)}")

    return position, rotation


class RosetteFP(CompositeBaseFP):
    """FeaturePython for a Rosette – a planar local coordinate system datum.

    The Rosette defines an origin (derived from a vertex, edge midpoint, or
    face parametric centre) and a primary fibre-orientation angle (the degree
    of freedom).  A ``Part::LocalCoordinateSystem`` child object tracks the
    computed placement.
    """

    Type = "Composite::Rosette"

    def __init__(self, obj, support=None):

        obj.addProperty(
            "App::PropertyLinkSubGlobal",
            "Support",
            "References",
            "Vertex, edge, or face that defines the rosette origin",
        ).Support = support

        obj.addProperty(
            "App::PropertyAngle",
            "Angle",
            "Parameters",
            "Primary fibre orientation angle (degrees)",
        ).Angle = 0.0

        obj.addProperty(
            "App::PropertyLinkGlobal",
            "LocalCoordinateSystem",
            "Materials",
            "Local coordinate system for the rosette datum",
        )
        obj.LocalCoordinateSystem = obj.Document.addObject(
            "Part::LocalCoordinateSystem",
            "LCS",
        )
        obj.setPropertyStatus("LocalCoordinateSystem", "LockDynamic")
        obj.setPropertyStatus("LocalCoordinateSystem", "ReadOnly")

        super().__init__(obj)

    def execute(self, fp):
        position, rotation = _origin_from_support(fp)
        lcs = fp.LocalCoordinateSystem
        lcs.Placement.Base = position
        lcs.Placement.Rotation = rotation

    def onChanged(self, fp, prop):
        match prop:
            case "Support":
                fp.recompute()


class ViewProviderRosette(VPCompositeBase):

    def attach(self, vobj):
        from pivy import coin
        from .RosetteSymbol import RosetteSymbol

        self.Object = vobj.Object
        self.ViewObject = vobj
        self._rosette = RosetteSymbol()
        self.standard = coin.SoGroup()
        self.standard.addChild(self._rosette.separator)
        vobj.addDisplayMode(self.standard, "Standard")
        self._update_symbol()

    def updateData(self, fp, prop):
        if prop in ("Support", "Angle"):
            self._update_symbol()

    def _update_symbol(self):
        fp = self.Object
        angle = float(fp.Angle)
        lcs = fp.LocalCoordinateSystem
        pos = lcs.Placement.Base
        rot = lcs.Placement.Rotation
        q = rot.Q
        self._rosette.update(
            orientations=[angle],
            position=(pos.x, pos.y, pos.z),
            rotation=(q[0], q[1], q[2], q[3]),
        )

    def claimChildren(self):
        return [self.Object.LocalCoordinateSystem]

    def getIcon(self):
        return ROSETTE_TOOL_ICON


def _is_vertex_edge_or_face(o):
    """Return True if *o* is a Part vertex, edge, or face shape."""
    return isinstance(o, (Part.Vertex, Part.Edge, Part.Face))


class RosetteCommand(BaseCommand):

    icon = ROSETTE_TOOL_ICON
    menu_text = "Rosette"
    tool_tip = (
        "Create a Rosette (planar local coordinate system datum).\n"
        "Select a vertex (origin at vertex), edge (origin at midpoint),\n"
        "or face (origin at parametric centre).\n"
        "Without selection the origin is at the model origin."
    )
    sel_args = [
        {
            "key": "support",
            "test": _is_vertex_edge_or_face,
            "optional": True,
        },
    ]
    type_id = "App::FeaturePython"
    instance_name = "Rosette"
    cls_fp = RosetteFP
    cls_vp = ViewProviderRosette


FreeCADGui.addCommand("Composites_Rosette", RosetteCommand())
