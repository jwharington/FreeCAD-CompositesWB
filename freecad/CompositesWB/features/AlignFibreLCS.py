# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import FreeCADGui
import Part
from .. import (
    ALIGN_FIBRE_LCS_TOOL_ICON,
)
from ..tools.lcs import (
    align_fibre_lcs,
)

from .CompositeShell import is_composite_shell
from .TransferLCS import (
    TransferLCSFP,
    ViewProviderTransferLCS,
    TransferLCSCommand,
)


class AlignFibreLCSFP(TransferLCSFP):

    Type = "Composite::AlignFibreLCS"

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
            case Part.Vertex:
                res = align_fibre_lcs(
                    draper=draper,
                    position=support[0].Point,
                    base_position=fp.LocalCoordinateSystem.Placement.Base,
                )
            case _:
                raise ValueError("Unhandled Support")
        if res:
            print(f"TODO rotate LCS by {res}")
            # lcs = fp.LocalCoordinateSystem
            # lcs.Placement.Base = position
            # lcs.Placement.Rotation = rotation.inverted()

    def onChanged(self, fp, prop):
        match prop:
            case "CompositeShell" | "Support" | "LocalCoordinateSystem":
                fp.recompute()


class ViewProviderAlignFibreLCS(ViewProviderTransferLCS):

    def getIcon(self):
        return ALIGN_FIBRE_LCS_TOOL_ICON


class AlignFibreLCSCommand(TransferLCSCommand):

    icon = ALIGN_FIBRE_LCS_TOOL_ICON
    menu_text = "Align fibre LCS"
    tool_tip = "Align fibre LCS along composite shell"
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
    instance_name = "AlignFibreLCS"
    cls_fp = AlignFibreLCSFP
    cls_vp = ViewProviderAlignFibreLCS


FreeCADGui.addCommand(
    "Composites_AlignFibreLCS",
    AlignFibreLCSCommand(),
)
