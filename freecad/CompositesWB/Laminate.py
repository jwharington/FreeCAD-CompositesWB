import FreeCAD
import FreeCADGui
from pivy import coin
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

# import Plot
# Fem::MaterialMechanicalNonlinear
# App::DocumentObjectGroup


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
        self.FEMLayers = get_layers_ccx(
            laminate=self.get_model(obj),
            model_type=StackModelType[obj.StackModelType],
        )

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


class ViewProviderLaminate:
    def __init__(self, obj):
        obj.Proxy = self
        self.modes = ["Standard"]

    def attach(self, obj):
        self.standard = coin.SoGroup()
        obj.addDisplayMode(self.standard, "Standard")
        self.ViewObject = obj
        self.Object = obj.Object

    def getIcon(self):
        return LAMINATE_TOOL_ICON

    def getDisplayModes(self, obj):
        return ["Standard"]

    def getDefaultDisplayMode(self):
        return "Standard"

    def setDisplayMode(self, mode):
        return mode

    def updateData(self, vobj, prop):
        pass

    def claimChildren(self):
        return self.Object.Layers  # Or return child objects

    def __getstate__(self):
        return {}

    def __setstate__(self, state):
        return None


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
        ViewProviderLaminate(obj.ViewObject)
        doc.recompute()

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


FreeCADGui.addCommand("Composites_Laminate", LaminateCommand())
