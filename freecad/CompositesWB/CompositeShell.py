import FreeCADGui
import Mesh
import MeshPart
from . import (
    COMPOSITE_SHELL_TOOL_ICON,
    is_comp_type,
)
from .tools.draper import Draper
from .shaders.MeshGridShader import MeshGridShader
from .Command import BaseCommand
from .Laminate import is_laminate


def is_composite_shell(obj):
    return is_comp_type(
        obj,
        "Part::FeaturePython",
        "Composite::Shell",
    )


class CompositeShellFP:

    Type = "Composite::Shell"

    def __init__(self, obj, support=None, laminate=None, lcs=None):
        obj.addExtension("App::SuppressibleExtensionPython")

        obj.addProperty(
            type="App::PropertyLinkGlobal",
            name="Support",
            group="References",
            doc="Shell shape",
        )

        obj.setPropertyStatus("Support", "LockDynamic")
        obj.setPropertyStatus("Support", "ReadOnly")

        obj.addProperty(
            type="App::PropertyLinkGlobal",
            name="LocalCoordinateSystem",
            group="Materials",
            doc="Local coordinate system used for orthotropic materials",
        )

        obj.addProperty(
            type="App::PropertyLinkGlobal",
            name="Laminate",
            group="Materials",
            doc="Laminate material",
        )
        # section could be composite laminate, or homogeneous lamina

        obj.addProperty(
            type="App::PropertyFloat",
            name="MaxLength",
            group="Draping",
            doc="Max length of draping mesh",
        )

        obj.addProperty(
            type="App::PropertyLinkGlobal",
            name="Mesh",
            group="Orthographic",
            doc="Mesh for orthotropic materials",
            hidden=True,
        )

        obj.Mesh = obj.Document.addObject(
            "Mesh::Feature",
            "DrapeMesh",
        )

        obj.setPropertyStatus("Mesh", "LockDynamic")
        obj.setPropertyStatus("Mesh", "ReadOnly")

        obj.MaxLength = 5.0
        obj.LocalCoordinateSystem = lcs
        obj.Laminate = laminate
        obj.Support = support
        obj.Proxy = self

    def execute(self, fp):
        if (not fp.Support) or (not fp.Laminate):
            return

        fp.Shape = fp.Support.Shape

        def get_lcs():
            if fp.LocalCoordinateSystem:
                return fp.LocalCoordinateSystem
            return fp.Support

        mesh = self.update_mesh(fp)
        self.draper = Draper(mesh, get_lcs())
        fp.Mesh.Mesh = mesh
        if fp.ViewObject:
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
        self.grid_shader = MeshGridShader()

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
        obj.Proxy = self

    def getDisplayModes(self, obj):
        return ["Shaded", "Grid"]

    def getDefaultDisplayMode(self):
        return "Shaded"

    def getIcon(self):
        return COMPOSITE_SHELL_TOOL_ICON

    def claimChildren(self):
        return [
            self.Object.Mesh,
            self.Object.LocalCoordinateSystem,
        ]

    def attach(self, obj):
        self.Active = False

        self.ViewObject = obj
        self.Object = obj.Object

        if not hasattr(self, "grid_shader"):
            self.grid_shader = MeshGridShader()
        obj.addDisplayMode(self.grid_shader.grp, "Grid")
        # self.load_shader()

        # needed to trigger color update
        self.onChanged(obj, "Color")

    def update_display_layer(self, fp):
        if not hasattr(fp.ViewObject, "DisplayLayer"):
            return
        display_layer_opts = list(fp.Laminate.StackOrientation.keys())
        sel = fp.ViewObject.DisplayLayer
        fp.ViewObject.DisplayLayer = display_layer_opts
        if sel in display_layer_opts:
            return
        if display_layer_opts:
            fp.ViewObject.DisplayLayer = display_layer_opts[0]

    def updateData(self, fp, prop):
        match prop:
            case "LocalCoordinateSystem" | "Support":
                pass
            case "Laminate":
                if fp.Laminate:
                    self.update_display_layer(fp)
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
            case "ShapeAppearance":
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
        if not hasattr(vobj.ViewObject, "DisplayLayer"):
            return 0
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
        if tex_coords and self.grid_shader:
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


class CompositeShellCommand(BaseCommand):

    icon = COMPOSITE_SHELL_TOOL_ICON
    menu_text = "Composite shell"
    tool_tip = "Create composite shell"
    sel_args = [
        {
            "key": "support",
            "type": "Part::Feature",
        },
        {
            "key": "laminate",
            "test": is_laminate,
        },
        {
            "key": "lcs",
            "type": "Part::LocalCoordinateSystem",
            "optional": True,
        },
    ]
    type_id = "Part::FeaturePython"
    instance_name = "CompositeShell"
    cls_fp = CompositeShellFP
    cls_vp = ViewProviderCompositeShell


FreeCADGui.addCommand(
    "Composites_CompositeShell",
    CompositeShellCommand(),
)
