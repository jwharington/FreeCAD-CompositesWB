import FreeCAD
import FreeCADGui
import MeshPart
from . import COMPOSITE_SHELL_TOOL_ICON
from .tools.draper import Draper


class CompositeShellFP:

    Type = "Composite::Shell"

    def __init__(self, obj, support):
        obj.Proxy = self
        obj.addExtension("App::SuppressibleExtensionPython")
        obj.Support = support

        obj.addProperty(
            type="App::PropertyLinkGlobal",
            name="LocalCoordinateSystem",
            group="Materials",
            doc="Local coordinate system used for orthotropic materials",
        ).LocalCoordinateSystem = None

        obj.addProperty(
            type="App::PropertyLinkGlobal",
            name="Laminate",
            group="Materials",
            doc="Laminate material",
        ).Laminate = None
        # section could be composite laminate, or homogeneous lamina

        obj.addProperty(
            type="App::PropertyFloat",
            name="MaxLength",
            group="Draping",
            doc="Max length of draping mesh",
        ).MaxLength = 5.0

    def execute(self, fp):

        def get_lcs():
            if fp.LocalCoordinateSystem:
                return fp.LocalCoordinateSystem
            return fp.Support

        mesh = self.update_mesh(fp)
        self.draper = Draper(mesh, get_lcs())
        fp.ViewObject.update()

    def onDocumentRestored(self, fp):
        # super().onDocumentRestored(fp)
        fp.recompute()

    def onChanged(self, fp, prop):
        match prop:
            case "Laminate":
                fp.recompute()
            case "LocalCoordinateSystem":
                fp.recompute()
            case "MaxLength" | "Support":
                fp.recompute()

    def get_tex_coords(self, offset_angle_deg):
        return self.draper.get_tex_coords(offset_angle_deg=offset_angle_deg)

    def get_drape_lcs(self, tris):
        return self.draper.get_lcs(tris)

    def update_mesh(self, fp):
        ml = fp.MaxLength
        shape = fp.Shape
        maxl = max(ml, shape.BoundBox.DiagonalLength / 50.0)
        return MeshPart.meshFromShape(Shape=shape, MaxLength=maxl)


class ViewProviderCompositeShell:

    def __init__(self, obj):
        obj.Proxy = self

    def getIcon(self):
        return COMPOSITE_SHELL_TOOL_ICON


class CompositeShellCommand:
    def GetResources(self):
        return {
            "Pixmap": COMPOSITE_SHELL_TOOL_ICON,
            "MenuText": "CompositeShell",
            "ToolTip": "Composite shell",
        }

    def Activated(self):
        doc = FreeCAD.ActiveDocument
        obj = doc.addObject(
            "PartDesign::SubShapeBinderPython",
            "CompositeShell",
        )
        selection = FreeCADGui.Selection.getSelectionEx()
        support = []
        for sel in selection:
            if hasattr(sel, "SubElementNames") and sel.SubElementNames:
                support.append((sel.Object, sel.SubElementNames))

        CompositeShellFP(obj, support)
        if FreeCAD.GuiUp:
            ViewProviderCompositeShell(obj.ViewObject)
            # FreeCADGui.Selection.clearSelection()
            # FreeCADGui.ActiveDocument.setEdit(doc.ActiveObject)
        doc.recompute()

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


FreeCADGui.addCommand(
    "Composites_CompositeShell",
    CompositeShellCommand(),
)
