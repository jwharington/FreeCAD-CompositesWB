from dataclasses import dataclass
from .ply import Ply
from .weave_type import WeaveType


@dataclass
class Fabric(Ply):
    weave: WeaveType = WeaveType.UD
    material_fibre: dict = None
    volume_fraction_fibre: float = None

    @property
    def area_density(self) -> float:
        return self.calc_area_density()

    @area_density.setter
    def area_density(self, value: float):
        self.set_area_density(value)

    def calc_area_density(self) -> float:
        return self.thickness * self.material_fibre.Density

    def set_area_density(self, value):
        self.thickness = value / self.material_fibre.Density
