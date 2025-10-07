import FreeCAD
import FreeCADGui
from . import FIBRE_COMPOSITE_LAMINA_TOOL_ICON
from .objects.weave_type import WeaveType
from .objects import (
    FibreCompositeLamina,
    SimpleFabric,
)
from .Composite import add_composite_props
from .Lamina import BaseLaminaFP, BaseViewProviderLamina
from .test.example_materials import glass


class FibreCompositeLaminaFP(BaseLaminaFP):

    Type = "Fem::MaterialMechanicalLamina"

    def __init__(self, obj):
        super().__init__(obj)

        add_composite_props(obj)

        obj.addProperty(
            "App::PropertyMap",
            "FibreMaterial",
            "Materials",
            "Material shapes",
        ).FibreMaterial = glass

        obj.addProperty(
            "App::PropertyEnumeration",
            "WeaveType",
            "Composition",
            "Representation of layers",
        )
        obj.WeaveType = [item.name for item in WeaveType]
        obj.WeaveType = WeaveType.UD.name

    def get_model(self, obj):
        if volume_fraction := obj.FibreVolumeFraction:
            volume_fraction *= 0.01
        else:
            volume_fraction = None
        if not obj.FibreMaterial:
            raise ValueError("No fibre material")
        weave_type = WeaveType[obj.WeaveType]
        fabric = SimpleFabric(
            material_fibre=obj.FibreMaterial,
            thickness=obj.Thickness.Value,
            orientation=obj.Angle.Value,
            weave=weave_type,
            volume_fraction_fibre=volume_fraction,
        )
        return FibreCompositeLamina(fibre=fabric)


class ViewProviderFibreCompositeLamina(BaseViewProviderLamina):

    def getIcon(self):
        return FIBRE_COMPOSITE_LAMINA_TOOL_ICON

    def claimChildren(self):
        return [self.Object.FibreMaterial, self.Object.ResinMaterial]


class FibreCompositeLaminaCommand:
    def GetResources(self):
        return {
            "Pixmap": FIBRE_COMPOSITE_LAMINA_TOOL_ICON,
            "MenuText": "FibreCompositeLamina",
            "ToolTip": "Fibre composite lamina container",
        }

    def Activated(self):
        doc = FreeCAD.ActiveDocument
        obj = doc.addObject(
            "App::FeaturePython",
            "CompositeLamina",
        )
        FibreCompositeLaminaFP(obj)
        ViewProviderFibreCompositeLamina(obj.ViewObject)
        doc.recompute()

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


FreeCADGui.addCommand(
    "Composites_FibreCompositeLamina",
    FibreCompositeLaminaCommand(),
)
