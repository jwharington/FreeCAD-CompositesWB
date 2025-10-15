from .symmetry_type import SymmetryType
from .weave_type import WeaveType
from .fabric import Fabric
from ..util.geometry_util import (
    format_orientation,
    expand_symmetry,
    normalise_orientation,
)


class SimpleFabric(Fabric):

    @property
    def description(self) -> str:
        return f"{self.weave.name}{format_orientation(self.orientation)}"

    def get_plies(self):
        ply_orientations, sym = self.get_ply_orientations()

        layers = expand_symmetry(ply_orientations, sym)
        n_layers = len(layers)

        def make_ply(o):
            this_orientation = normalise_orientation(o + self.orientation)
            return Fabric(
                thickness=self.thickness / n_layers,
                material_fibre=self.material_fibre,
                orientation=this_orientation,
            )

        return [make_ply(o) for o in layers]

    def get_ply_orientations(self):
        match self.weave:
            case WeaveType.UD:
                return [0], SymmetryType.Even
            case WeaveType.HOOP:
                return [90], SymmetryType.Even
            case WeaveType.BIAX090:
                return [0, 90], SymmetryType.Even
            case WeaveType.BIAX45:
                return [45, -45], SymmetryType.Even
            case WeaveType.BIAX15:
                return [-15, 15], SymmetryType.Even
            case WeaveType.TRIAX45:
                return [0, 45, 90, -45, 0], SymmetryType.Assymmetric
            case WeaveType.TRIAX30:
                return [0, 30, 90, -30, 0], SymmetryType.Assymmetric
        raise ValueError(f"Unhandled weave type {self.weave}")
