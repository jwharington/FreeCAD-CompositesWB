# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import FreeCAD
import FreeCADGui
from .. import (
    FIBRE_COMPOSITE_LAMINA_TOOL_ICON,
)
from ..objects import (
    FibreCompositeLamina,
    SimpleFabric,
    Lamina,
    WeaveType,
)
from ..taskpanels import task_fibre_composite_lamina
from .Composite import add_composite_props
from .Lamina import BaseLaminaFP, BaseViewProviderLamina
from .Command import BaseCommand


class FibreCompositeLaminaFP(BaseLaminaFP):

    Type = "Fem::MaterialMechanicalLamina"

    def __init__(self, obj):
        super().__init__(obj)

        add_composite_props(obj)

        obj.addProperty(
            "App::PropertyMap",
            "FibreMaterial",
            "Materials",
            "Fibre material",
        ).FibreMaterial = {}

        obj.addProperty(
            "App::PropertyString",
            "FibreMaterialUUID",
            "Materials",
            "Fibre material UUID",
            hidden=True,
        ).FibreMaterialUUID = ""

        obj.addProperty(
            "App::PropertyEnumeration",
            "WeaveType",
            "Composition",
            "Structure of layers",
        )
        obj.WeaveType = [item.name for item in WeaveType]
        obj.WeaveType = WeaveType.UD.name

        obj.addProperty(
            "App::PropertyArealMass",
            "ArealWeight",
            "Composition",
            "Areal weight of fibres",
        )
        obj.setPropertyStatus("ArealWeight", "ReadOnly")

    def get_density(self, obj):
        if not hasattr(obj, "FibreMaterial"):
            return None
        if "Density" not in obj.FibreMaterial:
            return None
        val = obj.FibreMaterial["Density"]
        return FreeCAD.Units.Quantity(val)

    def get_volume_fraction(self, obj):
        if volume_fraction := obj.FibreVolumeFraction:
            volume_fraction *= 0.01
        else:
            volume_fraction = 0.0
        return volume_fraction

    def update_areal_weight(self, obj):
        density = self.get_density(obj)
        if not density:
            return
        vf = self.get_volume_fraction(obj)
        if not vf:
            return
        t = FreeCAD.Units.Quantity(obj.Thickness)
        obj.ArealWeight = t * density * vf

    def onChanged(self, obj, prop):
        if "Thickness" == prop:
            self.update_areal_weight(obj)

    def get_model(self, obj) -> Lamina:
        if not obj.FibreMaterial:
            raise ValueError("No fibre material")
        weave_type = WeaveType[obj.WeaveType]
        fabric = SimpleFabric(
            material_fibre=obj.FibreMaterial,
            thickness=obj.Thickness.Value,
            orientation=obj.Angle.Value,
            weave=weave_type,
            volume_fraction_fibre=self.get_volume_fraction(obj),
        )
        return FibreCompositeLamina(fibre=fabric)

    def onDocumentRestored(self, obj):
        super().onDocumentRestored(obj)
        self.update_areal_weight(obj)


class ViewProviderFibreCompositeLamina(BaseViewProviderLamina):

    _taskPanel = task_fibre_composite_lamina._TaskPanel

    def getIcon(self):
        return FIBRE_COMPOSITE_LAMINA_TOOL_ICON


class FibreCompositeLaminaCommand(BaseCommand):

    icon = FIBRE_COMPOSITE_LAMINA_TOOL_ICON
    menu_text = "Fibre composite lamina"
    tool_tip = "Create fibre composite lamina"
    sel_args = []
    type_id = "App::FeaturePython"
    instance_name = "FibreCompositeLamina"
    cls_fp = FibreCompositeLaminaFP
    cls_vp = ViewProviderFibreCompositeLamina


FreeCADGui.addCommand(
    "Composites_FibreCompositeLamina",
    FibreCompositeLaminaCommand(),
)
