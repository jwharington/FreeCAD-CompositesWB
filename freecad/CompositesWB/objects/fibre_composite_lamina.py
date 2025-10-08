from dataclasses import dataclass, field
from .ply import Ply
from .composite_lamina import CompositeLamina
from .homogeneous_lamina import HomogeneousLamina
from .simple_fabric import SimpleFabric
from ..mechanics.stack_model_type import StackModelType
from ..mechanics.fibre_composite_model import calc_fibre_composite_model
from ..util.geometry_util import format_orientation


@dataclass
class FibreCompositeLamina(CompositeLamina):
    fibre: SimpleFabric = field(default_factory=SimpleFabric)

    @property
    def description(self):
        return (
            f"{self.fibre.description}-{self.material_matrix.Name}"
            f"?{format_orientation(self.orientation)}"
        )

    def get_layers(
        self,
        model_type: StackModelType = StackModelType.Discrete,
    ):
        def props(la: CompositeLamina):
            Ply.set_missing_child_props(
                self,
                [la],
                [
                    "volume_fraction_fibre",
                ],
            )

            material = calc_fibre_composite_model(
                material_fibre=la.material_fibre,
                material_matrix=self.material_matrix,
                volume_fraction_fibre=la.volume_fraction_fibre,
            )
            return HomogeneousLamina(
                material=material,
                thickness=la.thickness,
                orientation=la.orientation,
                orientation_display=la.orientation,
            )

        return [[props(lay) for lay in self.fibre.get_plies()]]
