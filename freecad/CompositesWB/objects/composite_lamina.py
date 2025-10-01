from dataclasses import dataclass
from .ply import Ply
from ..mechanics.material_properties import Material


@dataclass
class CompositeLamina(Ply):
    material_matrix: Material = None
    volume_fraction_fibre: float = None
