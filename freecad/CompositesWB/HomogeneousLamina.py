import FreeCAD
import FreeCADGui
from . import HOMOGENEOUS_LAMINA_TOOL_ICON
from .objects import (
    HomogeneousLamina,
)
from .Lamina import BaseLaminaFP, BaseViewProviderLamina
from .taskpanels import task_homogeneous_lamina


class HomogeneousLaminaFP(BaseLaminaFP):

    Type = "Fem::MaterialMechanicalLamina"

    def __init__(self, obj):
        super().__init__(obj)

        obj.addProperty(
            "App::PropertyMap",
            "Material",
            "Materials",
            "Material",
        ).Material = {}

        obj.addProperty(
            "App::PropertyString",
            "MaterialUUID",
            "Materials",
            "Fibre material UUID",
            hidden=True,
        ).MaterialUUID = ""

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

    def setEdit(self, vobj, mode=0):
        return super().setEdit(
            vobj,
            mode,
            task_homogeneous_lamina._TaskPanel,
        )


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
