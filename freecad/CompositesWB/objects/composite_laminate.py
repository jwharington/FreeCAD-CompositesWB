from dataclasses import dataclass, field
from typing import List
from .ply import Ply
from .laminate import Laminate
from .lamina import Lamina
from .composite_lamina import CompositeLamina
from ..mechanics.stack_model_type import StackModelType


@dataclass  # (frozen=True)
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
