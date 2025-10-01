from dataclasses import dataclass


@dataclass
class Lamina:
    core: bool = False
    thickness: float = 1
