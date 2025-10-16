import FreeCADGui as Gui
from . import WB_ICON


class CompositesWorkbench(Gui.Workbench):

    MenuText = "Composites"
    ToolTip = "Tools for composite structures"
    Icon = WB_ICON

    def Initialize(self):
        """This function is executed when the workbench is first activated.
        It is executed once in a FreeCAD session followed by the Activated
        function.
        """

        from . import Laminate  # noqa
        from . import CompositeLaminate  # noqa
        from . import FibreCompositeLamina  # noqa
        from . import HomogeneousLamina  # noqa

        from . import CompositeShell  # noqa
        from . import Seam  # noqa

        from . import TransferLCS  # noqa
        from . import WrapLCS  # noqa
        from . import AlignFibreLCS  # noqa

        from . import TexturePlan  # noqa
        from . import PartPlane  # noqa
        from . import Mould  # noqa

        cmds_section = [
            "Composites_Laminate",
            "Composites_CompositeLaminate",
            "Composites_FibreCompositeLamina",
            "Composites_HomogeneousLamina",
        ]
        cmds_structure = [
            "Composites_CompositeShell",
            "Composites_Seam",
        ]
        cmds_lcs = [
            "Composites_TransferLCS",
            "Composites_WrapLCS",
            "Composites_AlignFibreLCS",
        ]
        cmds_manufacturing = [
            "Composites_TexturePlan",
            "Composites_PartPlane",
            "Composites_Mould",
        ]
        self.list = (
            cmds_section
            + ["Separator"]
            + cmds_structure
            + ["Separator"]
            + cmds_lcs
            + ["Separator"]
            + cmds_manufacturing
        )
        self.appendToolbar("Composites", self.list)
        self.appendMenu("Composites", self.list)

    def Activated(self):
        """This function is executed whenever the workbench is activated"""
        return

    def Deactivated(self):
        """This function is executed whenever the workbench is deactivated"""
        return

    def ContextMenu(self, recipient):
        """This function is executed whenever the user right-clicks on
        screen"""
        # "recipient" will be either "view" or "tree"
        self.appendContextMenu("Composites", self.list)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


Gui.addWorkbench(CompositesWorkbench())
