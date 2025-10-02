import FreeCAD
import FreeCADGui
from pivy import coin
from . import LAMINATE_TOOL_ICON
from .mechanics import StackModelType
from .test.examples import make_laminate
from .util.fem_util import (
    get_layers_ccx,
    write_lamina_materials_ccx,
    write_shell_section_ccx,
)


# import Plot
# Fem::MaterialMechanicalNonlinear
# App::DocumentObjectGroup


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

    def onDocumentRestored(self, obj):
        if not obj.hasExtension("App::SuppressibleExtensionPython"):
            obj.addExtension("App::SuppressibleExtensionPython")
        self.laminate = make_laminate()
        obj.recompute()

    def execute(self, obj):
        model_type = StackModelType[obj.StackModelType]
        laminate = make_laminate()
        self.layers = get_layers_ccx(laminate, model_type)

    def get_materials(self, obj):
        return write_lamina_materials_ccx(
            self.layers,
            prefix=obj.Name,
        )

    def write_shell_section(self, obj):
        return write_shell_section_ccx(
            prefix=obj.Name,
            layers=self.layers,
        )

    def __getstate__(self):
        return {}
        # data = asdict(self.laminate)
        # print(data)
        # return {"laminate": data}

    def __setstate__(self, res):
        return None


class ViewProviderLaminate:
    def __init__(self, obj):
        obj.Proxy = self

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
        # Update visual data based on feature properties
        pass

    def claimChildren(self):
        return self.Object.Layers  # Or return child objects

    def __getstate__(self):
        return {}
        # data = asdict(self.laminate)
        # print(data)
        # return {"laminate": data}

    def __setstate__(self, res):
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
