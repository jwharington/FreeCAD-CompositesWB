import FreeCAD
from .VPCompositeBase import (
    VPCompositeBase,
    CompositeBaseFP,
)
from .. import WB_ICON

container_name = "CompositesContainer"


class CompositesContainerFP(CompositeBaseFP):

    def __init__(self, obj):

        obj.addProperty(
            "App::PropertyFloatConstraint",
            "MaxStrainTension",
            "Draping",
            "Strain limit in tension for draping",
        )
        obj.setExpression("MaxStrainTension", "1e-3")

        obj.addProperty(
            "App::PropertyFloatConstraint",
            "MaxStrainCompression",
            "Draping",
            "Strain limit in compression for draping",
        )
        obj.setExpression("MaxStrainCompression", "1e-3")

        obj.addProperty(
            "App::PropertyFloatConstraint",
            "MaxStrainShear",
            "Draping",
            "Strain limit in shear for draping",
        )
        obj.setExpression("MaxStrainShear", "1e-1")

        super().__init__(obj)


class ViewProviderCompositesContainer(VPCompositeBase):

    _taskPanel = None

    def getIcon(self):
        return WB_ICON

    def claimChildren(self):
        return self.Object.Group


def getCompositesContainer() -> FreeCAD.Document:
    for obj in FreeCAD.ActiveDocument.Objects:
        if obj.Name == container_name:
            return obj

    obj = FreeCAD.ActiveDocument.addObject(
        "App::DocumentObjectGroupPython",
        container_name,
    )
    if not obj:
        return None
    CompositesContainerFP(obj)
    obj.Label = "Composites"
    if FreeCAD.GuiUp:
        ViewProviderCompositesContainer(obj.ViewObject)
    return obj


# def getDocumentCompositeLaminates():
#     for obj in FreeCAD.ActiveDocument.Objects:
#         if obj.Name == container_name:
#             res = []
#             for o in obj.Group:
#                 if o.isDerivedFrom("App::FeaturePython"):
#                     res.append(o)
#             return res
#     return []


# import FreeCADGui
# import PySide
# from PySide import QtCore, QtGui

# mw = FreeCADGui.getMainWindow()
# m_tab = mw.findChild(QtGui.QTabBar)

# c_tab = mw.findChild(QtGui.QTabWidget, "combiTab")
# p_tab = c_tab.findChild(QtGui.QTabWidget, "propertyTab")

# print(c_tab)
# print(p_tab)
# print(m_tab)
