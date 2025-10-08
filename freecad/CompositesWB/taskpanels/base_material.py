from PySide import QtCore

import Materials
import MatGui
from .base_taskpanel import _BaseTaskPanel


class _MaterialTaskPanel(_BaseTaskPanel):

    def __init__(self, obj):
        super().__init__(obj)
        self.attach_material_ui(obj, self.parameter_widget)

    def attach_material_ui(self, obj, parameter_widget):
        material_manager = Materials.MaterialManager()

        def add_tree(material):
            material_tree = MatGui.MaterialTreeWidget(material["tree_wgt"])
            material_tree.expanded = False
            material_tree.IncludeEmptyFolders = False
            material_tree.IncludeEmptyLibraries = False
            material_tree.UUID = material["uuid"]

            def set_material(value):
                if not value:
                    return
                mat = material_manager.getMaterial(value)
                material["uuid"] = mat.UUID
                props = mat.Properties
                material["label_wgt"].setText(props["Description"])
                material["material"] = props

            QtCore.QObject.connect(
                material["tree_wgt"],
                QtCore.SIGNAL("onMaterial(QString)"),
                set_material,
            )

        self.materials = self.get_materials(obj, parameter_widget)

        for material in self.materials:
            add_tree(material)

    def get_materials(self, obj, parameter_widget):
        return []
