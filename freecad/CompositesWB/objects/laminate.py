from dataclasses import dataclass, field
from typing import List
from .symmetry_type import SymmetryType
from .lamina import Lamina
from ..mechanics.stack_model_type import StackModelType
from ..mechanics.stack_expansion import calc_stack_model
from ..util.geometry_util import expand_symmetry


@dataclass  # (frozen=True)
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
        return calc_stack_model(
            prefix,
            model_type,
            expanded_layers,
        )
