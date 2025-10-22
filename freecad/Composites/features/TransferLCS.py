# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import FreeCADGui
import Part
from .. import (
    TRANSFER_LCS_TOOL_ICON,
)
from ..tools.lcs import (
    transfer_lcs_to_point,
    transfer_lcs_to_edge,
)
from .VPCompositeBase import VPCompositeBase, FPBase
from .Command import BaseCommand
from .CompositeShell import is_composite_shell


class TransferLCSFP(FPBase):

    Type = "Composite::TransferLCS"

    def __init__(self, obj, shell=None, support=None):

        obj.addProperty(
            type="App::PropertyLinkGlobal",
            name="CompositeShell",
            group="References",
            doc="Composite shell (leading)",
        ).CompositeShell = shell

        obj.addProperty(
            type="App::PropertyLinkSubGlobal",
            name="Support",
            group="References",
            doc="Supporting geometry (at follower)",
        ).Support = support

        obj.addProperty(
            type="App::PropertyLinkGlobal",
            name="LocalCoordinateSystem",
            group="Materials",
            doc="Local coordinate system (following)",
        )
        obj.LocalCoordinateSystem = obj.Document.addObject(
            "Part::LocalCoordinateSystem",
            "LCS",
        )
        obj.setPropertyStatus("LocalCoordinateSystem", "LockDynamic")
        obj.setPropertyStatus("LocalCoordinateSystem", "ReadOnly")

        obj.addProperty(
            type="App::PropertyFloat",
            name="Position",
            group="Dimensions",
            doc="Proportion of distance along edge",
        ).Position = 0.5

        super().__init__(obj)

    def execute(self, fp):
        if not fp.Support:
            return
        draper = fp.CompositeShell.Proxy.get_draper()

        (sup, sub) = fp.Support
        support = sup.getSubObject(sub)
        if len(support) != 1:
            raise ValueError("Unhandled Support")
        res = None
        match type(support[0]):
            case Part.Face:
                res = self.handle_face(
                    fp,
                    draper=draper,
                    edge=support[0],
                    fraction=fp.Position,
                )
            case Part.Edge:
                res = transfer_lcs_to_edge(
                    draper=draper,
                    edge=support[0],
                    fraction=fp.Position,
                )
            case Part.Vertex:
                res = transfer_lcs_to_point(
                    draper=draper,
                    position=support[0].Point,
                )
            case _:
                raise ValueError("Unhandled Support")
        if res:
            (position, rotation) = res
            lcs = fp.LocalCoordinateSystem
            lcs.Placement.Base = position
            lcs.Placement.Rotation = rotation.inverted()

    def onChanged(self, fp, prop):
        match prop:
            case "CompositeShell" | "Support":
                fp.recompute()

    def handle_face(self, fp, draper, edge, fraction):
        raise ValueError("unhandled")


class ViewProviderTransferLCS(VPCompositeBase):

    def getIcon(self):
        return TRANSFER_LCS_TOOL_ICON

    def claimChildren(self):
        return [
            self.Object.LocalCoordinateSystem,
        ]


class TransferLCSCommand(BaseCommand):

    icon = TRANSFER_LCS_TOOL_ICON
    menu_text = "Transfer LCS"
    tool_tip = "Transfer LCS along composite shell"
    sel_args = [
        {
            "key": "shell",
            "test": is_composite_shell,
        },
        {
            "key": "support",
            "type": "Part::Feature",
            "optional": True,
        },
    ]
    type_id = "App::FeaturePython"
    instance_name = "TransferLCS"
    cls_fp = TransferLCSFP
    cls_vp = ViewProviderTransferLCS


FreeCADGui.addCommand(
    "Composites_TransferLCS",
    TransferLCSCommand(),
)
