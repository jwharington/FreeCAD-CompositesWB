import FreeCAD
import FreeCADGui
from pivy import coin
from . import LAMINATE_TOOL_ICON
from .objects.weave_type import WeaveType
from .objects import (
    FibreCompositeLamina,
    HomogeneousLamina,
    SimpleFabric,
)
from .Composite import add_composite_props


class BaseLaminaFP:

    Type = "Fem::MaterialMechanicalLamina"

    def __init__(self, obj):
        obj.Proxy = self
        obj.addExtension("App::SuppressibleExtensionPython")

        obj.addProperty(
            "App::PropertyBool",
            "Core",
            "Model",
            "Model as core or thin structure",
        ).Core = False

        obj.addProperty(
            "App::PropertyAngle",
            "Angle",
            "Model",
            "Planar angular offset",
        ).Angle = False

        obj.addProperty(
            "App::PropertyLength",
            "Thickness",
            "Model",
            "Thickness of layer",
        ).Thickness = 0.1

    def get_model(self, obj, parent):
        return None


class BaseViewProviderLamina:
    def __init__(self, obj):
        obj.Proxy = self

    def attach(self, obj):
        self.standard = coin.SoGroup()
        obj.addDisplayMode(self.standard, "Standard")
        self.ViewObject = obj
        self.Object = obj.Object

    def getDisplayModes(self, obj):
        return ["Standard"]

    def getDefaultDisplayMode(self):
        return "Standard"

    def setDisplayMode(self, mode):
        return mode

    def updateData(self, vobj, prop):
        # Update visual data based on feature properties
        pass

    def __getstate__(self):
        return {}

    def __setstate__(self, res):
        return None


class HomogeneousLaminaFP(BaseLaminaFP):

    Type = "Fem::MaterialMechanicalLamina"

    def __init__(self, obj):
        super().__init__(obj)

        obj.addProperty(
            "App::PropertyLinkGlobal",
            "Material",
            "References",
            "Material shapes",
        ).Material = None

    def get_model(self, obj):
        return HomogeneousLamina(
            core=obj.Core,
            thickness=obj.Thickness.Value,
            orientation=obj.Angle.Value,
            material=obj.Material,
        )


class ViewProviderHomogeneousLamina(BaseViewProviderLamina):

    def getIcon(self):
        return LAMINATE_TOOL_ICON

    def claimChildren(self):
        return [self.Object.Material]


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


class HomogeneousLaminaCommand:
    def GetResources(self):
        return {
            "Pixmap": LAMINATE_TOOL_ICON,
            "MenuText": "HomogeneousLamina",
            "ToolTip": "Homogeneous lamina container",
        }

    def Activated(self):
        doc = FreeCAD.ActiveDocument
        obj = doc.addObject(
            "App::FeaturePython",
            "HomogeneousLamina",
        )
        HomogeneousLaminaFP(obj)
        ViewProviderHomogeneousLamina(obj.ViewObject)
        doc.recompute()

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


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


FreeCADGui.addCommand("Composites_HomogeneousLamina", HomogeneousLaminaCommand())
FreeCADGui.addCommand("Composites_FibreCompositeLamina", FibreCompositeLaminaCommand())
