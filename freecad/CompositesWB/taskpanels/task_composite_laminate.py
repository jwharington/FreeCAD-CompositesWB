from .base_material import _MaterialTaskPanel


class _TaskPanel(_MaterialTaskPanel):

    UI_FILENAME = "CompositeLaminate.ui"

    def get_materials(self, obj, parameter_widget):
        return [
            {
                "material": obj.ResinMaterial,
                "uuid": obj.ResinMaterialUUID,
                "tree_wgt": parameter_widget.wgt_resin_material_tree,
                "label_wgt": parameter_widget.lbl_resin_material_descr,
            }
        ]

    def accept(self):
        self.obj.ResinMaterial = self.materials[0]["material"]
        self.obj.ResinMaterialUUID = self.materials[0]["uuid"]

        return super().accept()
