# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import FreeCADGui
from .. import (
    MOULD_TOOL_ICON,
)
from ..tools.mould import make_moulds
from .Command import BaseCommand
from .VPCompositeBase import VPCompositeBase, FPBase


class MouldFP(FPBase):
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

        super().__init__(obj)

    def execute(self, fp):
        buffer = [fp.XOverhang.Value, fp.YOverhang.Value, fp.ZOverhang.Value]
        fp.Shape = make_moulds(fp.Source.Shape, buffer)


class ViewProviderMould(VPCompositeBase):

    def getIcon(self):
        return MOULD_TOOL_ICON


class CompositeMouldCommand(BaseCommand):

    icon = MOULD_TOOL_ICON
    menu_text = "Mould"
    tool_tip = "Generate two part mould.  WORK-IN-PROGRESS"
    sel_args = [
        {
            "key": "source",
            "type": "Part::Feature",
        },
    ]
    type_id = "Part::FeaturePython"
    instance_name = "Mould"
    cls_fp = MouldFP
    cls_vp = ViewProviderMould


FreeCADGui.addCommand("Composites_Mould", CompositeMouldCommand())
