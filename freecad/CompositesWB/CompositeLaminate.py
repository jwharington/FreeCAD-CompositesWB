import FreeCADGui
from . import (
    COMPOSITE_LAMINATE_TOOL_ICON,
)
from .Composite import add_composite_props
from .Laminate import (
    LaminateFP,
    ViewProviderLaminate,
)
from .objects import (
    CompositeLaminate,
    SymmetryType,
)
from .taskpanels import task_composite_laminate
from .Command import BaseCommand


class CompositeLaminateFP(LaminateFP):

    def __init__(self, obj):
        super().__init__(obj)

        add_composite_props(obj)

    def make_model(self, obj, model_layers):
        if volume_fraction := obj.FibreVolumeFraction:
            volume_fraction *= 0.01
        else:
            volume_fraction = None

        return CompositeLaminate(
            symmetry=SymmetryType[obj.Symmetry],
            layers=model_layers,
            volume_fraction_fibre=volume_fraction,
            material_matrix=obj.ResinMaterial,
        )


class ViewProviderCompositeLaminate(ViewProviderLaminate):

    def getIcon(self):
        return COMPOSITE_LAMINATE_TOOL_ICON

    def setEdit(self, vobj, mode=0, TaskPanel=None):
        return super().setEdit(
            vobj,
            mode,
            task_composite_laminate._TaskPanel,
        )


class CompositeLaminateCommand(BaseCommand):

    icon = COMPOSITE_LAMINATE_TOOL_ICON
    menu_text = "Composite laminate"
    tool_tip = "Create composite laminate"
    sel_args = []
    type_id = "Part::FeaturePython"
    instance_name = "CompositeShell"
    cls_fp = CompositeLaminateFP
    cls_vp = ViewProviderCompositeLaminate


FreeCADGui.addCommand(
    "Composites_CompositeLaminate",
    CompositeLaminateCommand(),
)
