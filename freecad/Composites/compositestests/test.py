# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com


from ..util.plot_util import illustrateLayup
from ..mechanics import StackModelType
from ..mechanics.fibre_composite_model import calc_fibre_composite_model
import numpy as np
from pprint import pprint
from .examples import make_laminate
from .example_materials import (
    resin,
    glass,
)

from ..mechanics.shell_model import (
    material_shell_properties,
    stiffness_matrix_to_engineering_properties,
)


def test_A():
    np.set_printoptions(
        precision=3,
        formatter={"float": "{: 0.3g}".format},
        suppress=True,
    )
    m = calc_fibre_composite_model(glass, resin, 0.5)
    C, Qbar = material_shell_properties(m, np.radians(0))
    print(np.array_str(C))
    print(np.array_str(Qbar))
    mat = stiffness_matrix_to_engineering_properties(C)
    print(mat)


def test_B():
    laminate = make_laminate()
    #
    for i in StackModelType:
        print(f"----- {i}")
        # test_ccx(laminate, model_type=i, prefix="ZZ")
        layers = laminate.get_layers(model_type=i)
        pprint(layers)
        illustrateLayup(layers, label=i.name)
        # materials = get_materials(la, model_type=i)

    product = laminate.get_product()
    pprint(product)


test_B()
