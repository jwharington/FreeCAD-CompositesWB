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

        from . import Mould  # noqa
        from . import Seam  # noqa
        from . import PartPlane  # noqa
        from . import Laminate  # noqa
        from . import CompositeLaminate  # noqa
        from . import HomogeneousLamina  # noqa
        from . import FibreCompositeLamina  # noqa
        from . import CompositeShell  # noqa
        from . import TexturePlan  # noqa

        self.list = [
            "Composites_Mould",
            "Composites_PartPlane",
            "Composites_Seam",
            "Composites_Laminate",
            "Composites_CompositeLaminate",
            "Composites_HomogeneousLamina",
            "Composites_FibreCompositeLamina",
            "Composites_CompositeShell",
            "Composites_TexturePlan",
        ]
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
