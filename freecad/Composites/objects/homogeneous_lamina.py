# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from dataclasses import dataclass, field
from .ply import Ply
from ..mechanics.material_properties import (
    is_orthotropic,
)
from ..util.geometry_util import (
    format_orientation,
)


@dataclass
class HomogeneousLamina(Ply):
    # e.g. core foam, aluminium, etc, or merged
    material: dict = field(default_factory=dict)
    orientation_display: float = 0

    @property
    def description(self) -> str:
        desc = self.material["Name"]
        if is_orthotropic(self.material):
            return desc + format_orientation(self.orientation)
        else:
            return desc

    def get_product(self):
        return [(f"{self.description} {self.thickness}", 0)]

    def get_fibres(self):
        return None
