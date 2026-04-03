# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from FreeCAD import Console
import FreeCADGui
from .. import (
    COMPOSITE_SHELL_TOOL_ICON,
    is_comp_type,
    roma_map,
)
from ..tools.draper import Draper
from ..tools.fibre import (
    make_fibre_length_analysis,
    make_fibre_orientation_analysis,
)
from ..shaders.MeshGridShader import MeshGridShader
from .Command import BaseCommand
from .Container import getCompositesContainer
from .Laminate import is_laminate
from .VPCompositeBase import CompositeBaseFP
from ..util.mesh_util import shape2Mesh
import MeshEnums


def is_composite_shell(obj):
    return is_comp_type(
        obj,
        "Part::FeaturePython",
        "Composite::Shell",
    )


class CompositeShellFP(CompositeBaseFP):

    Type = "Composite::Shell"

    def __init__(self, obj, support=None, laminate=None, lcs=None):

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

        super().__init__(obj)

    def execute(self, fp):
        if (not fp.Support) or (not fp.Laminate):
            return

        fp.Shape = fp.Support.Shape

        def get_lcs():
            if fp.LocalCoordinateSystem:
                return fp.LocalCoordinateSystem
            return fp.Support

        try:
            mesh = shape2Mesh(fp.Shape, fp.MaxLength)
            self.draper = Draper(mesh, get_lcs(), fp.Shape)
            if self.has_valid_draper():
                fp.Mesh.Mesh = mesh
                self.fibre_analysis(fp)
        except Exception:
            self.draper = None

        if fp.ViewObject:
            fp.ViewObject.update()

    def fibre_analysis(self, fp):
        histograms_length = make_fibre_length_analysis(fp)
        Console.PrintMessage("Material fibre length analysis:")
        for material, histogram in histograms_length.items():
            Console.PrintMessage(f"  {material}: {histogram.average_length}")
        orientation_fraction = make_fibre_orientation_analysis(fp)
        Console.PrintMessage("Orientation fraction analysis:")
        for orientation, fraction in orientation_fraction.items():
            Console.PrintMessage(f"  {orientation}: {fraction:.2f}")

    def onChanged(self, fp, prop):
        match prop:
            case "Laminate":
                fp.recompute()
            case "LocalCoordinateSystem":
                fp.recompute()
            case "MaxLength" | "Support":
                fp.recompute()

    def has_valid_draper(self):
        return hasattr(self, "draper") and self.draper and self.draper.isValid()

    def get_tex_coords(self, offset_angle_deg):
        if self.has_valid_draper():
            return self.draper.get_tex_coords(
                offset_angle_deg=offset_angle_deg,
            )
        return None

    def get_draper(self):
        if self.has_valid_draper():
            return self.draper
        raise ValueError("Draper invalid")

    def get_drape_lcs(self, tris):
        if self.has_valid_draper():
            return self.draper.get_lcs(tris)
        return None

    def get_boundaries(self, offset_angle_deg):
        if self.has_valid_draper():
            return self.draper.get_boundaries(
                offset_angle_deg=offset_angle_deg,
            )
        return None

    def get_strains(self):
        if self.has_valid_draper():
            return self.draper.strains
        return None

    def get_stack_assembly(self, fp):
        lam_obj = fp.Laminate
        return lam_obj.Proxy.get_stack_assembly(lam_obj)


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

    def setDisplayMode(self, mode):
        return mode

    def getDisplayModes(self, obj):
        return ["Grid", "Strain XX", "Strain YY", "Strain XY"]

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

    def update_visibility(self, vobj):
        visible = vobj.Visibility
        if vobj.DisplayMode not in self.getDisplayModes(vobj):
            visible = False
        self.Object.Mesh.Visibility = visible
        if self.Object.LocalCoordinateSystem:
            self.Object.LocalCoordinateSystem.Visibility = visible

    def update_mesh_material(self, vobj):
        # use draper to determine distortion for coloring
        mesh = vobj.Object.Mesh
        n = mesh.Mesh.CountFacets
        if "Material" not in mesh.PropertiesList:
            mesh.addProperty("Mesh::PropertyMaterial", "Material")
        strains = vobj.Object.Proxy.get_strains()
        if strains is not None:

            material = {
                "binding": MeshEnums.Binding.PER_FACE,
                "transparency": [0.0] * n,
                "ambientColor": [(0.5, 0.5, 0.5)] * n,
                "diffuseColor": [(0.5, 0.5, 0.5)] * n,
                "shininess": [0.0] * n,
            }
            cont = getCompositesContainer()
            limit_pos = cont.MaxStrainTension
            limit_neg = cont.MaxStrainCompression
            match vobj.DisplayMode:
                case "Strain XX":
                    index = 0
                case "Strain YY":
                    index = 1
                case "Strain XY":
                    index = 2
                    limit_pos = cont.MaxStrainShear
                    limit_neg = cont.MaxStrainShear
                case _:
                    index = -1
            if index >= 0:
                s = strains[:, index]

                def map_val(x):
                    if x > 0:
                        s = min(1.0, (1.0 + (x / limit_pos) / 2))
                    elif x < 0:
                        s = max(0.0, (1.0 + (x / limit_neg) / 2))
                    else:
                        s = 0.5
                    return roma_map(s)[0:3]

                material["diffuseColor"] = [map_val(x) for x in s]
            mesh.Material = material
            mesh.ViewObject.Coloring = True
        self.update_visibility(vobj)

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
                self.update_visibility(vobj)
            case "DisplayMode":
                self.update_mesh_material(vobj)
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
    tool_tip = """Create composite shell.
        Select support feature, laminate and local coordinate system."""
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
