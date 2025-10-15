import FreeCAD
import FreeCADGui
from . import (
    FIBRE_COMPOSITE_LAMINA_TOOL_ICON,
)
from .objects.weave_type import WeaveType
from .objects import (
    FibreCompositeLamina,
    SimpleFabric,
    Lamina,
)
from .Composite import add_composite_props
from .Lamina import BaseLaminaFP, BaseViewProviderLamina
from .taskpanels import task_fibre_composite_lamina
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

    def onChanged(self, obj, prop):
        density = self.get_density(obj)
        if not density:
            return
        if "Thickness" == prop:
            obj.ArealWeight = FreeCAD.Units.Quantity(obj.Thickness) * density

    def get_model(self, obj) -> Lamina:
        if volume_fraction := obj.FibreVolumeFraction:
            volume_fraction *= 0.01
        else:
            volume_fraction = 0.0
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

    def setEdit(self, vobj, mode=0, TaskPanel=None):
        return super().setEdit(
            vobj,
            mode,
            task_fibre_composite_lamina._TaskPanel,
        )


class FibreCompositeLaminaCommand(BaseCommand):

    icon = FIBRE_COMPOSITE_LAMINA_TOOL_ICON
    menu_text = "Fibre composite lamina"
    tool_tip = "Create fibre composite lamina"
    sel_args = []
    type_id = "Part::FeaturePython"
    instance_name = "FibreCompositeLamina"
    cls_fp = FibreCompositeLaminaFP
    cls_vp = ViewProviderFibreCompositeLamina


FreeCADGui.addCommand(
    "Composites_FibreCompositeLamina",
    FibreCompositeLaminaCommand(),
)
