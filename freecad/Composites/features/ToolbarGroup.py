import FreeCADGui

from . import (
    AlignFibreLCS,  # noqa
    CompositeLaminate,  # noqa
    FibreCompositeLamina,  # noqa
    HomogeneousLamina,  # noqa
    Laminate,  # noqa
    Mould,  # noqa
    PartPlane,  # noqa
    Rosette,  # noqa
    Seam,  # noqa
    Stiffener,  # noqa
    TransferLCS,  # noqa
    WrapLCS,  # noqa
)


class CommandGroup:
    # https://forum.freecad.org/viewtopic.php?t=44684

    def __init__(self, cmdlist, menu, TypeId=None, tooltip=None):
        self.cmdlist = cmdlist
        self.menu = menu
        self.TypeId = TypeId
        if tooltip is None:
            self.tooltip = menu
        else:
            self.tooltip = tooltip

    def GetCommands(self):
        return tuple(self.cmdlist)

    def GetResources(self):
        return {"MenuText": self.menu, "ToolTip": self.tooltip}


FreeCADGui.addCommand(
    "Composites_LaminaTools",
    CommandGroup(
        [
            "Composites_FibreCompositeLamina",
            "Composites_HomogeneousLamina",
        ],
        menu="Lamina",
        tooltip="Lamina construction tools",
    ),
)

FreeCADGui.addCommand(
    "Composites_LaminateTools",
    CommandGroup(
        [
            "Composites_Laminate",
            "Composites_CompositeLaminate",
        ],
        menu="Laminate",
        tooltip="Laminate construction tools",
    ),
)

FreeCADGui.addCommand(
    "Composites_StructureTools",
    CommandGroup(
        [
            "Composites_Seam",
            "Composites_Stiffener",
        ],
        menu="Structure",
        tooltip="Shell structure construction tools",
    ),
)

FreeCADGui.addCommand(
    "Composites_MouldTools",
    CommandGroup(
        [
            "Composites_PartPlane",
            "Composites_Mould",
        ],
        menu="Mould",
        tooltip="Mould construction tools",
    ),
)

FreeCADGui.addCommand(
    "Composites_LCSTools",
    CommandGroup(
        [
            "Composites_TransferLCS",
            "Composites_WrapLCS",
            "Composites_AlignFibreLCS",
            "Composites_Rosette",
        ],
        menu="Material LCS",
        tooltip="Material local coordinate system tools",
    ),
)
