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

    f3 = SimpleFabric(
        material_fibre=glass,
        orientation=0,
        weave=WeaveType.BIAX45,
    )
    f3.thickness = 0.3

    fc1 = FibreCompositeLamina(fibre=f1)
    fc2 = FibreCompositeLamina(fibre=f2)
    fc3 = FibreCompositeLamina(fibre=f3)
    fcore = HomogeneousLamina(
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
            fc3,
            fcore,
        ],
        volume_fraction_fibre=0.5,
        material_matrix=resin,
    )
