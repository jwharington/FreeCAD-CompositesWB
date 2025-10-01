from dataclasses import dataclass
from .lamina import Lamina


@dataclass  # (frozen=True)
class Ply(Lamina):
    orientation: float = 0
