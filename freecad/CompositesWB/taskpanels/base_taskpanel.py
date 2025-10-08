# based on base_femtaskpanel.py
import FreeCADGui
from os import path
from .. import UIPATH


class _BaseTaskPanel:
    """
    Base task panel
    """

    UI_FILENAME = "FibreCompositeLamina.ui"

    def __init__(self, obj):
        self.obj = obj

        # parameter widget
        self.parameter_widget = FreeCADGui.PySideUic.loadUi(
            path.join(UIPATH, self.UI_FILENAME)
        )
        self.form = self.parameter_widget

    def accept(self):
        gui_doc = self.obj.ViewObject.Document
        gui_doc.Document.recompute()
        gui_doc.resetEdit()
        gui_doc.Document.commitTransaction()

        return True

    def reject(self):
        gui_doc = self.obj.ViewObject.Document
        gui_doc.Document.abortTransaction()
        gui_doc.resetEdit()
        gui_doc.Document.recompute()

        return True
