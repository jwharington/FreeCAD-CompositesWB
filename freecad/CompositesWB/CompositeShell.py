import FreeCAD
import FreeCADGui
import Mesh
import MeshPart
from . import COMPOSITE_SHELL_TOOL_ICON
from .tools.draper import Draper
from .shaders.MeshGridShader import MeshGridShader


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

        obj.addProperty(
            type="App::PropertyLinkGlobal",
            name="Mesh",
            group="Orthographic",
            doc="Mesh for orthotropic materials",
            hidden=True,
        ).Mesh = None

        obj.Mesh = obj.Document.addObject(
            "Mesh::Feature",
            "DrapeMesh",
        )

        obj.setPropertyStatus("Mesh", "LockDynamic")
        obj.setPropertyStatus("Mesh", "ReadOnly")

    def execute(self, fp):

        def get_lcs():
            if fp.LocalCoordinateSystem:
                return fp.LocalCoordinateSystem
            return fp.Support

        mesh = self.update_mesh(fp)
        self.draper = Draper(mesh, get_lcs())
        fp.Mesh.Mesh = mesh
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
        if self.draper.isValid():
            return self.draper.get_tex_coords(
                offset_angle_deg=offset_angle_deg,
            )
        return None

    def get_drape_lcs(self, tris):
        if self.draper.isValid():
            return self.draper.get_lcs(tris)
        return None

    def get_boundaries(self, offset_angle_deg):
        if self.draper.isValid():
            return self.draper.get_boundaries(
                offset_angle_deg=offset_angle_deg,
            )
        return None

    def update_mesh(self, fp):
        if not fp.Shape.BoundBox.isValid():
            return Mesh.Mesh()
        ml = fp.MaxLength
        shape = fp.Shape
        maxl = max(ml, shape.BoundBox.DiagonalLength / 50.0)
        return MeshPart.meshFromShape(Shape=shape, MaxLength=maxl)

    def __getstate__(self):
        return {}

    def __setstate__(self, state):
        return None


class ViewProviderCompositeShell:

    def __init__(self, obj):
        obj.Proxy = self

        obj.addProperty(
            "App::PropertyFloatConstraint",
            "Darken",
            "AnalysisOptions",
            "Grid darkness",
        )
        obj.Darken = 0.5

        obj.addProperty(
            "App::PropertyEnumeration",
            "DisplayLayer",
            "AnalysisOptions",
            "Select layer to display",
        )
        obj.DisplayLayer = ["0"]
        obj.DisplayLayer = "0"

        self.grid_shader = None

    def getDisplayModes(self, obj):
        return ["Grid"]

    def getDefaultDisplayMode(self):
        return "Grid"

    def getIcon(self):
        return COMPOSITE_SHELL_TOOL_ICON

    def claimChildren(self):
        return [
            self.Object.Mesh,
            self.Object.LocalCoordinateSystem,
        ]

    def attach(self, vobj):
        self.Active = False

        self.Object = vobj.Object
        self.ViewObject = vobj

        self.grid_shader = MeshGridShader()
        vobj.addDisplayMode(self.grid_shader.grp, "Grid")
        self.load_shader()

    def updateData(self, fp, prop):
        match prop:
            case "LocalCoordinateSystem" | "References":
                pass
            case "Laminate":
                if fp.Laminate:
                    display_layer_opts = list(fp.Laminate.StackOrientation.keys())
                    sel = fp.ViewObject.DisplayLayer
                    fp.ViewObject.DisplayLayer = display_layer_opts
                    if (sel not in display_layer_opts) and (display_layer_opts):
                        fp.ViewObject.DisplayLayer = display_layer_opts[0]
                else:
                    fp.ViewObject.DisplayLayer = ["0"]
                    fp.ViewObject.DisplayLayer = "0"
            case _:
                return
        self.reload_shader()

    def onChanged(self, vobj, prop):
        match prop:
            case "Visibility":
                visible = vobj.Visibility
                if self.Object.LocalCoordinateSystem:
                    self.Object.LocalCoordinateSystem.Visibility = visible
                self.Object.Mesh.Visibility = visible
            case "Darken":
                if self.grid_shader:
                    self.grid_shader.Darken = vobj.Darken
            case "DisplayLayer":
                self.reload_shader()
            case _:
                pass

    def onDelete(self, vobj, sub):
        self.remove_shader()
        return True

    def reload_shader(self):
        self.remove_shader()
        self.load_shader()

    def get_offset_angle(self, vobj):
        layer = vobj.ViewObject.DisplayLayer
        if not vobj.Laminate:
            return 0
        if layer in vobj.Laminate.StackOrientation:
            return int(vobj.Laminate.StackOrientation[layer])
        return 0

    def load_shader(self):
        if self.Active:
            return
        vobj = self.Object
        obj = vobj.Proxy
        if not hasattr(obj, "draper"):
            return

        aobj = vobj.Mesh
        offset_angle_deg = self.get_offset_angle(vobj)
        tex_coords = obj.get_tex_coords(offset_angle_deg=offset_angle_deg)
        if tex_coords:
            self.grid_shader.attach(vobj, aobj, tex_coords)
            self.Active = True
            FreeCADGui.Selection.addObserver(self)

    def remove_shader(self):
        if not self.Active:
            return
        aobj = self.Object.Mesh
        self.grid_shader.detach(aobj)
        self.Active = False
        FreeCADGui.Selection.removeObserver(self)

    def __getstate__(self):
        return {}

    def __setstate__(self, state):
        return None


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
