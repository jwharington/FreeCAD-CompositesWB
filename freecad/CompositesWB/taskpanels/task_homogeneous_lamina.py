from .base_material import _MaterialTaskPanel


class _TaskPanel(_MaterialTaskPanel):

    UI_FILENAME = "HomogeneousLamina.ui"

    def get_materials(self, obj, parameter_widget):
        return [
            {
                "material": obj.Material,
                "uuid": obj.MaterialUUID,
                "tree_wgt": parameter_widget.wgt_material_tree,
                "label_wgt": parameter_widget.lbl_material_descr,
            }
        ]

    def accept(self):
        self.obj.Material = self.materials[0]["material"]
        self.obj.MaterialUUID = self.materials[0]["uuid"]

        return super().accept()
