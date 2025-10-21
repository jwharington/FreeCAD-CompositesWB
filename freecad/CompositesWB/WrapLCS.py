# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import FreeCADGui
from .TransferLCS import (
    TransferLCSFP,
    ViewProviderTransferLCS,
    TransferLCSCommand,
)
from . import (
    WRAP_LCS_TOOL_ICON,
)
from .tools.lcs import (
    transfer_lcs_to_face,
)
from .CompositeShell import is_composite_shell


class WrapLCSFP(TransferLCSFP):

    def __init__(self, obj, shell=None, support=None, follower_shell=None):
        super().__init__(obj, shell=shell, support=support)

        obj.addProperty(
            type="App::PropertyLinkGlobal",
            name="FollowerShell",
            group="References",
            doc="Follower shell",
        ).FollowerShell = follower_shell

    def handle_face(self, fp, draper, edge, fraction):
        (sup, sub) = fp.FollowerShell
        shell = sup.getSubObject(sub)
        if len(shell) != 1:
            raise ValueError("Unhandled Support")

        return transfer_lcs_to_face(
            draper=draper,
            face=shell[0],
            edge=edge,
            fraction=fraction,
        )


class ViewProviderWrapLCS(ViewProviderTransferLCS):

    def getIcon(self):
        return WRAP_LCS_TOOL_ICON


class WrapLCSCommand(TransferLCSCommand):

    icon = WRAP_LCS_TOOL_ICON
    menu_text = "Wrap LCS"
    tool_tip = "Wrap LCS onto adjacent shell"
    sel_args = [
        {
            "key": "shell",
            "test": is_composite_shell,
        },
        {
            "key": "follower_shell",
            "type": "Part::Feature",
        },
        {
            "key": "support",
            "type": "Part::Feature",
            "optional": True,
        },
    ]
    type_id = "App::FeaturePython"
    instance_name = "WrapLCS"
    cls_fp = WrapLCSFP
    cls_vp = ViewProviderWrapLCS


FreeCADGui.addCommand(
    "Composites_WrapLCS",
    WrapLCSCommand(),
)
