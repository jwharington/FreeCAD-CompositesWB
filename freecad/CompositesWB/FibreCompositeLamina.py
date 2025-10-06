import FreeCAD
import FreeCADGui
from . import LAMINATE_TOOL_ICON
from .objects.weave_type import WeaveType
from .objects import (
    FibreCompositeLamina,
    SimpleFabric,
)
from .Composite import add_composite_props
from .Lamina import BaseLaminaFP, BaseViewProviderLamina


class FibreCompositeLaminaFP(BaseLaminaFP):

    Type = "Fem::MaterialMechanicalLamina"

    def __init__(self, obj):
        super().__init__(obj)

        add_composite_props()

        obj.addProperty(
            "App::PropertyLinkGlobal",
            "FibreMaterial",
            "Materials",
            "Material shapes",
        ).FibreMaterial = None

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

        fabric = SimpleFabric(
            thickness=obj.Thickness.Value,
            orientation=obj.Angle.Value,
            weave=WeaveType(obj.WeaveType),
            volume_fraction=volume_fraction,
        )
        return FibreCompositeLamina(fibre=fabric)


class ViewProviderFibreCompositeLamina(BaseViewProviderLamina):

    def getIcon(self):
        return LAMINATE_TOOL_ICON

    def claimChildren(self):
        return [self.Object.FibreMaterial, self.Object.ResinMaterial]


class FibreCompositeLaminaCommand:
    def GetResources(self):
        return {
            "Pixmap": LAMINATE_TOOL_ICON,
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


FreeCADGui.addCommand("Composites_FibreCompositeLamina", FibreCompositeLaminaCommand())
