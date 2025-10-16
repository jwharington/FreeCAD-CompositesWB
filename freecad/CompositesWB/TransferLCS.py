import FreeCAD
import FreeCADGui
import Part
from . import (
    TRANSFER_LCS_TOOL_ICON,
)
from .Command import BaseCommand
from .tools.lcs import (
    transfer_lcs_to_edge,
    transfer_lcs_to_face,
    transfer_lcs_to_point,
)

# from .CompositeShell import is_composite_shell


class TransferLCSFP:

    Type = "Composite::TransferLCS"

    def __init__(self, obj, shell=None):
        obj.Proxy = self
        obj.addExtension("App::SuppressibleExtensionPython")

        obj.addProperty(
            type="App::PropertyLinkGlobal",
            name="CompositeShell",
            group="References",
            doc="Primary composite shell",
        ).CompositeShell = shell

    def execute(self, fp):
        pass

    def onDocumentRestored(self, fp):
        # super().onDocumentRestored(fp)
        fp.recompute()

    # def onChanged(self, fp, prop):
    #     match prop:
    #         case "CompositeShell":
    #             fp.recompute()


class ViewProviderTransferLCS:

    def __init__(self, obj):
        obj.Proxy = self

    def getDisplayModes(self, obj):
        return []

    def getDefaultDisplayMode(self):
        return "Wireframe"

    def getIcon(self):
        return TRANSFER_LCS_TOOL_ICON

    def attach(self, vobj):
        self.Object = vobj.Object
        self.ViewObject = vobj

    # def updateData(self, fp, prop):
    #     match prop:
    #         case _:
    #             return

    # def onChanged(self, vobj, prop):
    #     match prop:
    #         case _:
    #             pass

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class TransferLCSCommand(BaseCommand):

    icon = TRANSFER_LCS_TOOL_ICON
    menu_text = "Transfer LCS"
    tool_tip = "Transfer LCS along composite shell"
    sel_args = []
    type_id = "App::FeaturePython"
    instance_name = "TransferLCS"
    cls_fp = TransferLCSFP
    cls_vp = ViewProviderTransferLCS


FreeCADGui.addCommand(
    "Composites_TransferLCS",
    TransferLCSCommand(),
)
