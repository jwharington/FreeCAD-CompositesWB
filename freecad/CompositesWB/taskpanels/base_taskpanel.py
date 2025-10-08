# based on base_femtaskpanel.py


class _BaseTaskPanel:
    """
    Base task panel
    """

    def __init__(self, obj):
        self.obj = obj

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
