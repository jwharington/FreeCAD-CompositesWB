import FreeCAD
import FreeCADGui
from . import LAMINATE_TOOL_ICON
from .mechanics import StackModelType
from .util.fem_util import (
    get_layers_ccx,
    write_lamina_materials_ccx,
    write_shell_section_ccx,
)
from .objects import (
    Laminate,
    SymmetryType,
)
from .VPCompositeBase import VPCompositeBase

# import Plot
# Fem::MaterialMechanicalNonlinear
# App::DocumentObjectGroup

# from femtaskpanels import task_material_reinforced


def get_model_layers(obj):
    return [o.Proxy.get_model(o) for o in obj.Layers]


class LaminateFP:

    Type = "Fem::MaterialMechanicalLaminate"

    def __init__(self, obj):
        obj.Proxy = self
        obj.addExtension("App::SuppressibleExtensionPython")

        obj.addProperty(
            "App::PropertyLinkListGlobal",
            "Layers",
            "Dimensions",
            "Link to lamina",
        ).Layers = []

        obj.addProperty(
            "App::PropertyEnumeration",
            "StackModelType",
            "Dimensions",
            "Representation of layers",
        )
        obj.StackModelType = [item.name for item in StackModelType]
        obj.StackModelType = StackModelType.Discrete.name

        obj.addProperty(
            "App::PropertyEnumeration",
            "Symmetry",
            "Composition",
            "Repeating stackup",
        )
        obj.Symmetry = [item.name for item in SymmetryType]
        obj.Symmetry = SymmetryType.Odd.name

        obj.addProperty(
            "App::PropertyMap",
            "StackOrientation",
            "Composition",
            "Orientation of layers in stack",
            hidden=True,
        ).StackOrientation = {}

        obj.addProperty(
            "App::PropertyLength",
            "Thickness",
            "Dimensions",
            "Thickness of laminate",
        )
        obj.setPropertyStatus("Thickness", "ReadOnly")

        # obj.addProperty(
        #     "App::PropertyPythonObject",
        #     "FEMLayers",
        #     "Dimensions",
        #     "FEM representation of layers",
        #     0,
        #     True,
        # ).FEMLayers = []

    def onDocumentRestored(self, obj):
        if not obj.hasExtension("App::SuppressibleExtensionPython"):
            obj.addExtension("App::SuppressibleExtensionPython")
        obj.recompute()

    def execute(self, obj):
        laminate = self.get_model(obj)
        self.FEMLayers = get_layers_ccx(
            laminate=laminate,
            model_type=StackModelType[obj.StackModelType],
        )
        obj.StackOrientation = {
            o.material["Name"]: f"{int(o.orientation_display):d}"
            for o in self.FEMLayers
        }
        print(f"laminate execute: {laminate.thickness}")
        obj.Thickness = FreeCAD.Units.Quantity(laminate.thickness)

    def onChanged(self, fp, prop):
        match prop:
            case "Layers":
                fp.recompute()

    def get_materials(self, obj):
        return write_lamina_materials_ccx(
            prefix=obj.Name,
            layers=self.FEMLayers,
        )

    def write_shell_section(self, obj):
        return write_shell_section_ccx(
            prefix=obj.Name,
            layers=self.FEMLayers,
        )

    def __getstate__(self):
        return {}

    def __setstate__(self, state):
        return None

    def get_model(self, obj):
        model_layers = get_model_layers(obj)
        if not model_layers:
            print("invalid model")
            return None
        return self.make_model(obj, model_layers)

    def make_model(self, obj, model_layers):
        return Laminate(
            symmetry=SymmetryType[obj.Symmetry],
            layers=model_layers,
        )


class ViewProviderLaminate(VPCompositeBase):

    def getIcon(self):
        return LAMINATE_TOOL_ICON

    def updateData(self, vobj, prop):
        pass

    def claimChildren(self):
        return self.Object.Layers


class LaminateCommand:
    def GetResources(self):
        return {
            "Pixmap": LAMINATE_TOOL_ICON,
            "MenuText": "Laminate",
            "ToolTip": "Laminate container",
        }

    def Activated(self):
        doc = FreeCAD.ActiveDocument
        obj = doc.addObject(
            "App::FeaturePython",
            "Laminate",
        )
        LaminateFP(obj)
        if FreeCAD.GuiUp:
            ViewProviderLaminate(obj.ViewObject)
            FreeCADGui.Selection.clearSelection()
            FreeCADGui.ActiveDocument.setEdit(doc.ActiveObject)
        doc.recompute()

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


FreeCADGui.addCommand("Composites_Laminate", LaminateCommand())
