import FreeCAD
from FreeCAD import Console
import FreeCADGui
from . import (
    PART_PLANE_TOOL_ICON,
)
from .tools.part_plane import make_part_plane

# from .selection_utils import find_face_in_selection_object


class PartPlaneFP:
    def __init__(self, obj, source):
        obj.addProperty(
            "App::PropertyLink",
            "Source",
            "PartPlane",
            "Link to the shape",
            locked=True,
        ).Source = source

        obj.addProperty(
            "App::PropertyLength",
            "Inset",
            "PartPlane",
            "Inset length",
            locked=True,
        ).Inset = "0.01 mm"

        obj.addProperty(
            "App::PropertyBool",
            "Ruled",
            "PartPlane",
            "Ruled",
            locked=True,
        ).Ruled = True

        obj.Proxy = self

    def onChanged(self, fp, prop):
        return

    def execute(self, fp):
        shape = make_part_plane(
            fp.Source.Shape,
            inset=fp.Inset.Value,
            ruled=fp.Ruled,
        )
        fp.Shape = shape


class ViewProviderPartPlane:
    def __init__(self, obj):
        self.obj = obj
        obj.Proxy = self

    def onChanged(self, obj, prop):
        return

    def updateData(self, fp, prop):
        return

    def claimChildren(self):
        return []  # [self.obj.Object.Source]

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class CompositePartPlaneCommand:
    """Composite part plane command"""

    def GetResources(self):
        return {
            "Pixmap": PART_PLANE_TOOL_ICON,
            "MenuText": "Part plane",
            "ToolTip": "Generate part plane",
        }

    def check_sel(self):
        sel = FreeCADGui.Selection.getSelection()
        if len(sel) == 1:
            return sel
        return None

    def Activated(self):
        if sel := self.check_sel():
            source = sel[0]
            doc = FreeCAD.ActiveDocument
            obj = doc.addObject(
                "Part::FeaturePython",
                "PartPlane",
            )
            PartPlaneFP(obj, source)
            ViewProviderPartPlane(obj.ViewObject)
            doc.recompute()
        else:
            Console.PrintError("Select 1 object exactly\r\n")

    def IsActive(self):
        return self.check_sel() is not None


FreeCADGui.addCommand("Composites_PartPlane", CompositePartPlaneCommand())
