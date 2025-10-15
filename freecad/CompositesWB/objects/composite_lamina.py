from dataclasses import dataclass
from .ply import Ply


@dataclass
class CompositeLamina(Ply):
    material_matrix: dict = {}
    volume_fraction_fibre: float = 0
