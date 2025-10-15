from dataclasses import dataclass
from .lamina import Lamina


@dataclass
class Ply(Lamina):
    orientation: float = 0
