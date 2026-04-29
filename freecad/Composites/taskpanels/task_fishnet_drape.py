# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from .base_taskpanel import _BaseTaskPanel


class _TaskPanel(_BaseTaskPanel):
    UI_FILENAME = "FishnetDrape.ui"

    def __init__(self, obj):
        super().__init__(obj)
        self.parameter_widget.spin_fabric_spacing.setValue(float(obj.FabricSpacing))
        self.parameter_widget.spin_relax_weight.setValue(float(obj.RelaxWeight))
        self.parameter_widget.spin_solve_steps.setValue(int(obj.SolveSteps))

    def accept(self):
        self.obj.FabricSpacing = self.parameter_widget.spin_fabric_spacing.value()
        self.obj.RelaxWeight = self.parameter_widget.spin_relax_weight.value()
        self.obj.SolveSteps = self.parameter_widget.spin_solve_steps.value()
        return super().accept()
