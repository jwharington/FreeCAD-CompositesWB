# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from .base_material import _MaterialTaskPanel


class _TaskPanel(_MaterialTaskPanel):

    UI_FILENAME = "FibreCompositeLamina.ui"

    def get_materials(self, obj, parameter_widget):
        return [
            {
                "material": obj.ResinMaterial,
                "uuid": obj.ResinMaterialUUID,
                "tree_wgt": parameter_widget.wgt_resin_material_tree,
                "label_wgt": parameter_widget.lbl_resin_material_descr,
            },
            {
                "material": obj.FibreMaterial,
                "uuid": obj.FibreMaterialUUID,
                "tree_wgt": parameter_widget.wgt_fibre_material_tree,
                "label_wgt": parameter_widget.lbl_fibre_material_descr,
            },
        ]

    def accept(self):
        self.obj.ResinMaterial = self.materials[0]["material"]
        self.obj.ResinMaterialUUID = self.materials[0]["uuid"]
        self.obj.FibreMaterial = self.materials[1]["material"]
        self.obj.FibreMaterialUUID = self.materials[1]["uuid"]

        return super().accept()
