from dataclasses import dataclass, field
from .ply import Ply


@dataclass
class CompositeLamina(Ply):
    material_matrix: dict = field(default_factory=dict)
    volume_fraction_fibre: float = 0
