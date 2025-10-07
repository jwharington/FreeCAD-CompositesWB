import FreeCAD
import FreeCADGui
from . import COMPOSITE_LAMINATE_TOOL_ICON
from .Composite import add_composite_props
from .Laminate import (
    LaminateFP,
    ViewProviderLaminate,
    get_model_layers,
)
from .objects import (
    CompositeLaminate,
    SymmetryType,
)


class CompositeLaminateFP(LaminateFP):

    def __init__(self, obj):
        super().__init__(obj)

        add_composite_props(obj)

    def get_model(self, obj):
        model_layers = get_model_layers(obj)
        if not model_layers:
            print("invalid model")
            return None
        if volume_fraction := obj.FibreVolumeFraction:
            volume_fraction *= 0.01
        else:
            volume_fraction = None

        return CompositeLaminate(
            symmetry=SymmetryType.Odd,
            layers=model_layers,
            volume_fraction_fibre=volume_fraction,
            material_matrix=obj.ResinMaterial,
        )


class ViewProviderCompositeLaminate(ViewProviderLaminate):

    def getIcon(self):
        return COMPOSITE_LAMINATE_TOOL_ICON


class CompositeLaminateCommand:
    def GetResources(self):
        return {
            "Pixmap": COMPOSITE_LAMINATE_TOOL_ICON,
            "MenuText": "CompositeLaminate",
            "ToolTip": "Composite laminate container",
        }

    def Activated(self):
        doc = FreeCAD.ActiveDocument
        obj = doc.addObject(
            "App::FeaturePython",
            "Laminate",
        )
        CompositeLaminateFP(obj)
        ViewProviderCompositeLaminate(obj.ViewObject)
        doc.recompute()

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


FreeCADGui.addCommand(
    "Composites_CompositeLaminate",
    CompositeLaminateCommand(),
)
