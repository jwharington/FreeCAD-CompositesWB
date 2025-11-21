# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from dataclasses import dataclass, field
from typing import List

from ..mechanics.stack_model_type import StackModelType
from .composite_lamina import CompositeLamina
from .lamina import Lamina
from .laminate import Laminate
from .ply import Ply


@dataclass
class CompositeLaminate(Laminate, CompositeLamina):
    layers: List[Lamina] = field(default_factory=list)

    def get_layers(
        self,
        model_type: StackModelType = StackModelType.Discrete,
    ):
        Ply.set_missing_child_props(
            self,
            self.layers,
            [
                "volume_fraction_fibre",
                "material_matrix",
            ],
        )
        return Laminate.get_layers(self, model_type)
