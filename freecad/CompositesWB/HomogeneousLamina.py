import FreeCAD
import FreeCADGui
from . import HOMOGENEOUS_LAMINA_TOOL_ICON
from .objects import (
    HomogeneousLamina,
)
from .Lamina import BaseLaminaFP, BaseViewProviderLamina


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
        return HOMOGENEOUS_LAMINA_TOOL_ICON


class HomogeneousLaminaCommand:
    def GetResources(self):
        return {
            "Pixmap": HOMOGENEOUS_LAMINA_TOOL_ICON,
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
        if FreeCAD.GuiUp:
            ViewProviderHomogeneousLamina(obj.ViewObject)
            FreeCADGui.Selection.clearSelection()
            FreeCADGui.ActiveDocument.setEdit(doc.ActiveObject)
        doc.recompute()

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


FreeCADGui.addCommand(
    "Composites_HomogeneousLamina",
    HomogeneousLaminaCommand(),
)
