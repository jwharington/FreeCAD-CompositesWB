import FreeCADGui
from . import (
    HOMOGENEOUS_LAMINA_TOOL_ICON,
)
from .objects import (
    HomogeneousLamina,
    Lamina,
)
from .Lamina import BaseLaminaFP, BaseViewProviderLamina
from .taskpanels import task_homogeneous_lamina
from .Command import BaseCommand


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

    def get_model(self, obj) -> Lamina:
        return HomogeneousLamina(
            core=obj.Core,
            thickness=obj.Thickness.Value,
            orientation=obj.Angle.Value,
            material=obj.Material,
        )


class ViewProviderHomogeneousLamina(BaseViewProviderLamina):

    def getIcon(self):
        return HOMOGENEOUS_LAMINA_TOOL_ICON

    def setEdit(self, vobj, mode=0, TaskPanel=None):
        return super().setEdit(
            vobj,
            mode,
            task_homogeneous_lamina._TaskPanel,
        )


class HomogeneousLaminaCommand(BaseCommand):

    icon = HOMOGENEOUS_LAMINA_TOOL_ICON
    menu_text = "Homogeneous lamina"
    tool_tip = "Create homogeneous lamina"
    sel_args = []
    type_id = "App::FeaturePython"
    instance_name = "HomogeneousLamina"
    cls_fp = HomogeneousLaminaFP
    cls_vp = ViewProviderHomogeneousLamina


FreeCADGui.addCommand(
    "Composites_HomogeneousLamina",
    HomogeneousLaminaCommand(),
)
