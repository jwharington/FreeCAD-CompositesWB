# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import FreeCAD
import FreeCADGui
import Part
from .. import (
    TEXTURE_PLAN_TOOL_ICON,
)
from .Command import BaseCommand
from .CompositeShell import is_composite_shell
from .VPCompositeBase import VPCompositeBase, FPBase


class TexturePlanFP(FPBase):

    Type = "Composite::TexturePlan"

    def __init__(self, obj, shells=[]):
        obj.addProperty(
            type="App::PropertyLinkListGlobal",
            name="CompositeShell",
            group="References",
            doc="Composite Shells to unwrap",
        ).CompositeShell = shells

        super().__init__(obj)

    def execute(self, fp):
        shapes = []
        for obj in fp.CompositeShell:
            if "Composite::Shell" != obj.Proxy.Type:
                FreeCAD.Console.PrintError(f"Incorrect type {obj.Name}\n")
                continue
            # TODO: lay out separate shapes for each layer in the composites
            for key, orientation in obj.Laminate.StackAssembly.items():
                print(f"name {obj.Name} key {key} orientation {orientation}")
                boundaries = obj.Proxy.get_boundaries(offset_angle_deg=int(orientation))
                if not boundaries:
                    continue
                for w in boundaries:
                    shapes.append(Part.Wire(Part.makePolygon(w)))
        fp.Shape = Part.makeCompound(shapes)

        # fp.ViewObject.update()

    def onChanged(self, fp, prop):
        match prop:
            case "CompositeShell":
                fp.recompute()


class ViewProviderTexturePlan(VPCompositeBase):

    def getDisplayModes(self, obj):
        return []

    def getDefaultDisplayMode(self):
        return "Wireframe"

    def getIcon(self):
        return TEXTURE_PLAN_TOOL_ICON

    def attach(self, vobj):
        self.Object = vobj.Object
        self.ViewObject = vobj


class TexturePlanCommand(BaseCommand):

    icon = TEXTURE_PLAN_TOOL_ICON
    menu_text = "Texture plan"
    tool_tip = "Create texture plan"
    sel_args = [
        {
            "key": "shells",
            "test": is_composite_shell,
            "array": True,
            "optional": True,
        },
    ]
    type_id = "Part::FeaturePython"
    instance_name = "TexturePlan"
    cls_fp = TexturePlanFP
    cls_vp = ViewProviderTexturePlan


FreeCADGui.addCommand(
    "Composites_TexturePlan",
    TexturePlanCommand(),
)
