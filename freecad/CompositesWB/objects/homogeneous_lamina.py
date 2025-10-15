from dataclasses import dataclass
from .ply import Ply
from ..mechanics.material_properties import (
    is_orthotropic,
)
from ..util.geometry_util import (
    format_orientation,
)


@dataclass
class HomogeneousLamina(Ply):
    # e.g. core foam, aluminium, etc, or merged
    material: dict = {}
    orientation_display: float = 0

    @property
    def description(self):
        desc = self.material["Name"]
        if is_orthotropic(self.material):
            return desc + format_orientation(self.orientation)
        else:
            return desc

    def get_product(self):
        return [(f"{self.description} {self.thickness}", 0)]
