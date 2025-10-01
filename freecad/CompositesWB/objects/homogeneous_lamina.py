from dataclasses import dataclass
from .ply import Ply
from ..mechanics.material_properties import (
    Material,
    is_orthotropic,
)
from ..mechanics.stack_model_type import StackModelType
from ..util.geometry_util import (
    format_orientation,
)


@dataclass
class HomogeneousLamina(Ply):
    # e.g. core foam, aluminium, etc, or merged
    material: Material = None

    @property
    def description(self):
        desc = self.material.Name
        if is_orthotropic(self.material):
            return desc + format_orientation(self.orientation)
        else:
            return desc

    def get_layers(
        self,
        model_type: StackModelType = StackModelType.Discrete,
    ):
        return [self]
