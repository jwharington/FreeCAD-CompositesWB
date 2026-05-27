# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from FreeCAD import Vector

from .base_taskpanel import _BaseTaskPanel


class _TaskPanel(_BaseTaskPanel):
    UI_FILENAME = "FishnetDrape.ui"

    def __init__(self, obj):
        super().__init__(obj)
        self.parameter_widget.spin_fabric_spacing.setValue(float(obj.FabricSpacing))
        self.parameter_widget.spin_relax_weight.setValue(float(obj.RelaxWeight))
        self.parameter_widget.spin_solve_steps.setValue(int(obj.SolveSteps))

        self.parameter_widget.spin_max_length.setValue(float(getattr(obj, "MaxLength", 0.0)))
        algorithm = str(getattr(obj, "DrapingAlgorithm", "kindrape_constructive"))
        algorithm_idx = self.parameter_widget.combo_algorithm.findText(algorithm)
        if algorithm_idx >= 0:
            self.parameter_widget.combo_algorithm.setCurrentIndex(algorithm_idx)
        self.parameter_widget.check_auto_direction.setChecked(bool(getattr(obj, "AutoDrapingDirection", True)))
        self.parameter_widget.spin_mesh_size.setValue(float(getattr(obj, "MeshSize", 0.0)))
        material_model = str(getattr(obj, "MaterialModel", "woven"))
        model_idx = self.parameter_widget.combo_material_model.findText(material_model)
        if model_idx >= 0:
            self.parameter_widget.combo_material_model.setCurrentIndex(model_idx)
        self.parameter_widget.spin_ud_coefficient.setValue(float(getattr(obj, "UDCoefficient", 0.0)))
        self.parameter_widget.check_thickness_correction.setChecked(bool(getattr(obj, "ThicknessCorrection", False)))

        seed = getattr(obj, "SeedPoint", None)
        if seed is not None:
            self.parameter_widget.spin_seed_x.setValue(float(seed.x))
            self.parameter_widget.spin_seed_y.setValue(float(seed.y))
            self.parameter_widget.spin_seed_z.setValue(float(seed.z))

        direction = getattr(obj, "DrapingDirection", None)
        if direction is not None:
            self.parameter_widget.spin_dir_x.setValue(float(direction.x))
            self.parameter_widget.spin_dir_y.setValue(float(direction.y))
            self.parameter_widget.spin_dir_z.setValue(float(direction.z))

    def accept(self):
        self.obj.FabricSpacing = self.parameter_widget.spin_fabric_spacing.value()
        self.obj.RelaxWeight = self.parameter_widget.spin_relax_weight.value()
        self.obj.SolveSteps = self.parameter_widget.spin_solve_steps.value()

        self.obj.MaxLength = self.parameter_widget.spin_max_length.value()
        selected_algorithm = self.parameter_widget.combo_algorithm.currentText()
        self.obj.DrapingAlgorithm = selected_algorithm
        self.obj.AutoDrapingDirection = self.parameter_widget.check_auto_direction.isChecked()
        self.obj.MeshSize = self.parameter_widget.spin_mesh_size.value()
        self.obj.MaterialModel = self.parameter_widget.combo_material_model.currentText()
        self.obj.UDCoefficient = self.parameter_widget.spin_ud_coefficient.value()
        self.obj.ThicknessCorrection = self.parameter_widget.check_thickness_correction.isChecked()

        self.obj.SeedPoint = Vector(
            self.parameter_widget.spin_seed_x.value(),
            self.parameter_widget.spin_seed_y.value(),
            self.parameter_widget.spin_seed_z.value(),
        )

        self.obj.DrapingDirection = Vector(
            self.parameter_widget.spin_dir_x.value(),
            self.parameter_widget.spin_dir_y.value(),
            self.parameter_widget.spin_dir_z.value(),
        )

        return super().accept()
