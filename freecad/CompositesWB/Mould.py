import FreeCAD
from FreeCAD import Console
import FreeCADGui
from . import (
    MOULD_TOOL_ICON,
)
from .tools.mould import make_moulds


class MouldFP:
    def __init__(self, obj, source):
        obj.addProperty(
            "App::PropertyLink",
            "Source",
            "Mould",
            "Link to the shape",
            locked=True,
        ).Source = source

        obj.addProperty(
            "App::PropertyLength",
            "XOverhang",
            "Mould",
            "X overhang length",
            locked=True,
        ).XOverhang = "30.0 mm"

        obj.addProperty(
            "App::PropertyLength",
            "YOverhang",
            "Mould",
            "Y overhang length",
            locked=True,
        ).YOverhang = "30.0 mm"

        obj.addProperty(
            "App::PropertyLength",
            "ZOverhang",
            "Mould",
            "Z overhang length",
            locked=True,
        ).ZOverhang = "5.0 mm"

        obj.Proxy = self

    def onChanged(self, fp, prop):
        return

    def execute(self, fp):
        buffer = [fp.XOverhang.Value, fp.YOverhang.Value, fp.ZOverhang.Value]
        fp.Shape = make_moulds(fp.Source.Shape, buffer)


class ViewProviderMould:
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


class CompositeMouldCommand:
    """Composite mould command"""

    def GetResources(self):
        return {
            "Pixmap": MOULD_TOOL_ICON,
            "MenuText": "Mould",
            "ToolTip": "Generate mould",
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
                "Mould",
            )
            MouldFP(obj, source)
            ViewProviderMould(obj.ViewObject)
            doc.recompute()
        else:
            Console.PrintError("Select 1 object exactly\r\n")

    def IsActive(self):
        return self.check_sel() is not None


FreeCADGui.addCommand("Composites_Mould", CompositeMouldCommand())
