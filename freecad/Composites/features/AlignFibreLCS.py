# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import FreeCAD
from FreeCAD import Console
import FreeCADGui
import Part
from .. import (
    ALIGN_FIBRE_LCS_TOOL_ICON,
)
from ..tools.lcs import (
    align_fibre_lcs,
    transfer_lcs_to_point,
)

from .CompositeShell import is_composite_shell
from .TransferLCS import (
    TransferLCSFP,
    ViewProviderTransferLCS,
    TransferLCSCommand,
)


def _get_shell_lcs_base(shell):
    """Return the base position of the composite shell's LCS.

    Prefers the Rosette's LCS when a Rosette is set on the shell, falls back
    to the shell's plain LocalCoordinateSystem, and returns the zero vector
    when neither is available.
    """
    lcs = None
    if hasattr(shell, "Rosette") and shell.Rosette:
        lcs = shell.Rosette.LocalCoordinateSystem
    elif shell.LocalCoordinateSystem:
        lcs = shell.LocalCoordinateSystem
    if lcs:
        return lcs.Placement.Base
    return FreeCAD.Vector(0.0, 0.0, 0.0)


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
        match type(support[0]):
            case Part.Vertex:
                position, rotation = transfer_lcs_to_point(
                    draper=draper,
                    position=support[0].Point,
                )
                base_position = _get_shell_lcs_base(fp.CompositeShell)
                angle = align_fibre_lcs(
                    draper=draper,
                    position=support[0].Point,
                    base_position=base_position,
                )
                R_align = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), angle)
                lcs = fp.LocalCoordinateSystem
                lcs.Placement.Base = position
                lcs.Placement.Rotation = (rotation * R_align).inverted()
            case _:
                raise ValueError("Unhandled Support")

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
    tool_tip = """Align fibre LCS along composite shell.
        Select composite shell and support feature."""
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
