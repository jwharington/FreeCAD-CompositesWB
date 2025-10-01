from ..objects import (
    SymmetryType,
    CompositeLaminate,
    HomogeneousLamina,
    FibreCompositeLamina,
    SimpleFabric,
    WeaveType,
)
from .example_materials import (
    resin,
    glass,
    foam,
)


def make_laminate():
    f1 = SimpleFabric(
        material_fibre=glass,
        orientation=0,
        weave=WeaveType.BIAX090,
    )
    f1.thickness = 0.1

    f2 = SimpleFabric(
        material_fibre=glass,
        orientation=45,
        weave=WeaveType.BIAX090,
    )
    f2.thickness = 0.2

    fc1 = FibreCompositeLamina(fibre=f1)
    fc2 = FibreCompositeLamina(fibre=f2)
    f3 = HomogeneousLamina(
        orientation=0,
        thickness=1,
        material=foam,
        core=True,
    )

    return CompositeLaminate(
        symmetry=SymmetryType.Odd,
        layers=[
            fc1,
            fc2,
            f3,
        ],
        volume_fraction_fibre=0.5,
        material_matrix=resin,
    )
