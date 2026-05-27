# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import traceback

import FreeCAD
import FreeCADGui

from .. import WB_ICON
from ..compositeexamples import runner


class RunCompositeExampleCommand:
    def GetResources(self):
        return {
            "Pixmap": WB_ICON,
            "MenuText": "Run Composite Example",
            "ToolTip": "Run the default composites example (ud_plate_basic)",
        }

    def Activated(self):
        try:
            result = runner.run("ud_plate_basic", run_solver=False)
            FreeCAD.Console.PrintMessage(
                f"[Composites] Example 'ud_plate_basic' completed: {result}\n",
            )
        except Exception:
            FreeCAD.Console.PrintError(
                "[Composites] Failed to run example 'ud_plate_basic'.\n",
            )
            FreeCAD.Console.PrintError(traceback.format_exc())

    def IsActive(self):
        return True


FreeCADGui.addCommand(
    "Composites_RunCompositeExample",
    RunCompositeExampleCommand(),
)
