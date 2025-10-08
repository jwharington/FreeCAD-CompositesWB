# based on fem task_panel_reinforced.py

from PySide import QtCore

# import FreeCAD
import FreeCADGui
import Materials
import MatGui
from os import path

from .base_taskpanel import _BaseTaskPanel
from .. import UIPATH


class _TaskPanel(_BaseTaskPanel):

    def __init__(self, obj):
        super().__init__(obj)

        self.material_manager = Materials.MaterialManager()

        # parameter widget
        self.parameter_widget = FreeCADGui.PySideUic.loadUi(
            path.join(UIPATH, "FibreCompositeLamina.ui")
        )

        self.materials = [
            {
                "material": self.obj.ResinMaterial,
                "uuid": self.obj.ResinMaterialUUID,
                "tree_wgt": self.parameter_widget.wgt_resin_material_tree,
                "label_wgt": self.parameter_widget.lbl_resin_material_descr,
            },
            {
                "material": self.obj.FibreMaterial,
                "uuid": self.obj.FibreMaterialUUID,
                "tree_wgt": self.parameter_widget.wgt_fibre_material_tree,
                "label_wgt": self.parameter_widget.lbl_fibre_material_descr,
            },
        ]

        def add_tree(material):
            material_tree = MatGui.MaterialTreeWidget(material["tree_wgt"])
            material_tree.expanded = False
            material_tree.IncludeEmptyFolders = False
            material_tree.IncludeEmptyLibraries = False
            material_tree.UUID = material["uuid"]

            def set_material(value):
                if not value:
                    return
                mat = self.material_manager.getMaterial(value)
                material["uuid"] = mat.UUID
                props = mat.Properties
                material["label_wgt"].setText(props["Description"])
                material["material"] = props

            QtCore.QObject.connect(
                material["tree_wgt"],
                QtCore.SIGNAL("onMaterial(QString)"),
                set_material,
            )

        for material in self.materials:
            add_tree(material)

        self.form = self.parameter_widget

    def accept(self):
        self.obj.ResinMaterial = self.materials[0]["material"]
        self.obj.ResinMaterialUUID = self.materials[0]["uuid"]
        self.obj.FibreMaterial = self.materials[1]["material"]
        self.obj.FibreMaterialUUID = self.materials[1]["uuid"]

        return super().accept()
