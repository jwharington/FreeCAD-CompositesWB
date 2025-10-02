import FreeCAD
import FreeCADGui
from pivy import coin
from . import LAMINATE_TOOL_ICON
from .objects.weave_type import WeaveType


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


class ViewProviderHomogeneousLamina(BaseViewProviderLamina):

    def getIcon(self):
        return LAMINATE_TOOL_ICON

    def claimChildren(self):
        return [self.Object.Material]


class FibreCompositeLaminaFP(BaseLaminaFP):

    Type = "Fem::MaterialMechanicalLamina"

    def __init__(self, obj):
        super().__init__(obj)

        obj.addProperty(
            "App::PropertyLinkGlobal",
            "ResinMaterial",
            "Materials",
            "Material shapes",
        ).ResinMaterial = None

        obj.addProperty(
            "App::PropertyLinkGlobal",
            "FibreMaterial",
            "Materials",
            "Material shapes",
        ).FibreMaterial = None

        obj.addProperty(
            "App::PropertyPercent",
            "FibreVolumeFraction",
            "Composition",
            "Composition",
        ).FibreVolumeFraction = 50

        obj.addProperty(
            "App::PropertyEnumeration",
            "WeaveType",
            "Composition",
            "Representation of layers",
        )
        obj.WeaveType = [item.name for item in WeaveType]
        obj.WeaveType = WeaveType.UD.name


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
