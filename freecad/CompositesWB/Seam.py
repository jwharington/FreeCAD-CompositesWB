from FreeCAD import Console
import FreeCADGui
from . import (
    SEAM_TOOL_ICON,
)
from .tools.seam import make_seam


class CompositeSeamCommand:
    """Composite seam command"""

    def GetResources(self):
        return {
            "Pixmap": SEAM_TOOL_ICON,
            "MenuText": "Seam",
            "ToolTip": "Generate seam",
        }

    def check_sel(self):
        sel = FreeCADGui.Selection.getSelectionEx()
        if len(sel) == 1:
            sel = [sel[0].SubObjects[0], sel[0].SubObjects[1]]
        elif len(sel) == 2:
            sel = [sel[0].SubObjects[0], sel[1].SubObjects[0]]
        else:
            return None
        return sel

    def Activated(self):
        if sel := self.check_sel():
            make_seam(sel[0], sel[1])
        else:
            Console.PrintError("Select two faces\r\n")
        return

    def IsActive(self):
        return self.check_sel() is not None


FreeCADGui.addCommand("Composites_Seam", CompositeSeamCommand())
