import FreeCAD
import FreeCADGui
from . import (
    COMPOSITE_LAMINATE_TOOL_ICON,
    getCompositesContainer,
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
            "CompositeLaminate",
        )
        CompositeLaminateFP(obj)
        if FreeCAD.GuiUp:
            ViewProviderCompositeLaminate(obj.ViewObject)
            FreeCADGui.Selection.clearSelection()
            FreeCADGui.ActiveDocument.setEdit(doc.ActiveObject)
        getCompositesContainer().addObject(obj)
        doc.recompute()

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


FreeCADGui.addCommand(
    "Composites_CompositeLaminate",
    CompositeLaminateCommand(),
)
