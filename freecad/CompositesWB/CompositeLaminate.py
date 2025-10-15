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
from .Laminate import LaminateCommand


class CompositeLaminateFP(LaminateFP):

    def __init__(self, obj, laminae=[]):
        super().__init__(obj, laminae=laminae)

        add_composite_props(obj)

    def make_model(self, obj, model_layers):
        if volume_fraction := obj.FibreVolumeFraction:
            volume_fraction *= 0.01
        else:
            volume_fraction = 0

        return CompositeLaminate(
            symmetry=SymmetryType[obj.Symmetry],
            layers=model_layers,
            volume_fraction_fibre=volume_fraction,  # noqa
            material_matrix=obj.ResinMaterial,
        )

    def execute(self, obj):
        if not obj.ResinMaterial:
            raise ValueError("invalid resin material")
        super().execute(obj)


class ViewProviderCompositeLaminate(ViewProviderLaminate):

    def getIcon(self):
        return COMPOSITE_LAMINATE_TOOL_ICON

    def setEdit(self, vobj, mode=0, TaskPanel=None):
        return super().setEdit(
            vobj,
            mode,
            task_composite_laminate._TaskPanel,
        )


class CompositeLaminateCommand(LaminateCommand):

    icon = COMPOSITE_LAMINATE_TOOL_ICON
    menu_text = "Composite laminate"
    tool_tip = "Create composite laminate"
    instance_name = "CompositeLaminate"
    cls_fp = CompositeLaminateFP
    cls_vp = ViewProviderCompositeLaminate


FreeCADGui.addCommand(
    "Composites_CompositeLaminate",
    CompositeLaminateCommand(),
)
