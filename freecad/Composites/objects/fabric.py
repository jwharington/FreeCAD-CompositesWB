# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from dataclasses import dataclass, field
from .ply import Ply
from .weave_type import WeaveType


@dataclass
class Fabric(Ply):
    weave: WeaveType = WeaveType.UD
    material_fibre: dict = field(default_factory=dict)
    volume_fraction_fibre: float = 0

    @property
    def area_density(self) -> float:
        return self.calc_area_density()

    @area_density.setter
    def area_density(self, value: float):
        self.set_area_density(value)

    def calc_area_density(self) -> float:
        return self.thickness * self.material_fibre["Density"]

    def set_area_density(self, value):
        self.thickness = value / self.material_fibre["Density"]
