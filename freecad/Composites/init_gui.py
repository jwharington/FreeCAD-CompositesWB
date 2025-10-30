# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import FreeCAD
import FreeCADGui as Gui
from . import WB_ICON


class CompositesWorkbench(Gui.Workbench):

    MenuText = "Composites"
    ToolTip = "Tools for composite structures"
    Icon = WB_ICON

    def Initialize(self):
        """This function is executed when the workbench is first activated.
        It is executed once in a FreeCAD session followed by the Activated
        function.
        """

        from .features import CompositeShell  # noqa
        from .features import TexturePlan  # noqa
        from .features import ToolbarGroup  # noqa

        cmds_section = [
            "Composites_LaminaTools",
            "Composites_LaminateTools",
        ]
        cmds_structure = [
            "Composites_CompositeShell",
            "Composites_StructureTools",
            "Composites_LCSTools",
        ]
        cmds_manufacturing = [
            "Composites_TexturePlan",
            "Composites_MouldTools",
        ]
        self.list = (
            cmds_section
            + ["Separator"]
            + cmds_structure
            + ["Separator"]
            + cmds_manufacturing
        )
        self.appendToolbar("Composites", self.list)
        self.appendMenu("Composites", self.list)

    def Activated(self):
        """This function is executed whenever the workbench is activated"""
        return

    def Deactivated(self):
        """This function is executed whenever the workbench is deactivated"""
        return

    def ContextMenu(self, recipient):
        """This function is executed whenever the user right-clicks on
        screen"""
        # "recipient" will be either "view" or "tree"
        self.appendContextMenu("Composites", self.list)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(CompositesWorkbench())
FreeCAD.__unit_test__ += ["TestCompositesGui"]
