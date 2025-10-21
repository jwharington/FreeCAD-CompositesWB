# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from dataclasses import dataclass, field
from typing import List
from .symmetry_type import SymmetryType
from .lamina import Lamina
from ..mechanics.stack_model_type import StackModelType
from ..mechanics.stack_expansion import calc_stack_model
from ..util.geometry_util import expand_symmetry


@dataclass
class Laminate(Lamina):
    name: str = "Laminate"
    layers: List[Lamina] = field(default_factory=list)
    symmetry: SymmetryType = SymmetryType.Assymmetric

    def get_layers(
        self,
        model_type: StackModelType = StackModelType.Discrete,
    ):
        layers = [lay.get_layers(model_type) for lay in self.layers]
        expanded_layers = expand_symmetry(layers, self.symmetry)
        prefix = StackModelType.merged_name(model_type)
        model = calc_stack_model(
            prefix,
            model_type,
            expanded_layers,
        )
        self.thickness = sum([layer.thickness for layer in model])
        return model

    def get_product(self):
        res = []
        expanded_layers = expand_symmetry(self.layers, self.symmetry)
        for lay in expanded_layers:
            if product := lay.get_product():
                res.extend(product)
        return res
