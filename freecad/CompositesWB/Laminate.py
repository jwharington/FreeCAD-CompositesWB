import FreeCAD
import FreeCADGui
from . import (
    LAMINATE_TOOL_ICON,
)
from .mechanics import StackModelType
from .util.fem_util import (
    get_layers_ccx,
    write_lamina_materials_ccx,
    write_shell_section_ccx,
)
from .util.bom_util import (
    get_layers_bom,
)
from .objects import (
    Laminate,
    SymmetryType,
)
from .VPCompositeBase import VPCompositeBase
from .Command import BaseCommand


# import Plot
# Fem::MaterialMechanicalNonlinear
# App::DocumentObjectGroup

# from femtaskpanels import task_material_reinforced


def get_model_layers(obj):
    return [o.Proxy.get_model(o) for o in obj.Layers]


def is_laminate(obj):
    if obj.TypeId != "App::FeaturePython":
        return False
    if not obj.Proxy:
        return False
    if obj.Proxy.Type != "Fem::MaterialMechanicalLaminate":
        return False
    return True


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
            "App::PropertyMap",
            "StackAssembly",
            "Composition",
            "Assembly BOM stack",
            hidden=True,
        ).StackAssembly = {}

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

        if not hasattr(obj, "StackModelType"):
            return

        self.FEMLayers = get_layers_ccx(
            laminate=laminate,
            model_type=StackModelType[obj.StackModelType],
        )
        obj.StackOrientation = {
            o.material["Name"]: f"{int(o.orientation_display):+03d}"
            for o in self.FEMLayers
        }
        obj.StackAssembly = get_layers_bom(laminate=laminate)
        if laminate:
            obj.Thickness = FreeCAD.Units.Quantity(laminate.thickness)
        else:
            obj.Thickness = FreeCAD.Units.Quantity(0.0)

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

    def get_model(self, obj) -> Laminate:
        if model_layers := get_model_layers(obj):
            return self.make_model(obj, model_layers)
        return None  # noqa

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


class LaminateCommand(BaseCommand):

    icon = LAMINATE_TOOL_ICON
    menu_text = "Laminate"
    tool_tip = "Create laminate"
    sel_args = []
    type_id = "Part::FeaturePython"
    instance_name = "LaminatedShell"
    cls_fp = LaminateFP
    cls_vp = ViewProviderLaminate


FreeCADGui.addCommand("Composites_Laminate", LaminateCommand())
