# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com


from typing import List
import numpy as np
from ..objects.lamina import Lamina
from ..objects.homogeneous_lamina import HomogeneousLamina

from .material_properties import (
    common_material2dict,
    material_from_dict,
)
from .shell_model import (
    material_shell_properties,
    stiffness_matrix_to_engineering_properties,
    material_rotate,
)


# Refer:
# - https://nilspv.folk.ntnu.no/TMM4175/computational-procedures.html
# - lamprop
# - Barbero


def calc_z(layers: List[Lamina]):
    thicknesses = [lay.thickness for lay in layers]
    total_thickness = sum(thicknesses)

    zbar = []
    z0 = -total_thickness / 2
    for lay in layers:
        t = lay.thickness
        zbar.append(z0 + t / 2)
        z0 += t
    return zbar, total_thickness


def layer_density(layer: Lamina):
    mat = common_material2dict(layer.material)
    density = mat["Density"]
    assert density, f"density must be positive {density}"
    return density


def merge_clt(
    prefix: str,
    layers: List[Lamina],
    sandwich: bool = False,
) -> HomogeneousLamina:

    zbar, total_thickness = calc_z(layers)

    # initialise accumulators
    A = np.zeros((3, 3))
    B = np.zeros((3, 3))
    D = np.zeros((3, 3))
    H = np.zeros((2, 2))
    C = np.zeros((6, 6))
    density = 0

    def accumulate_ABD(t_k, zbar_k, Qbar_k, is_core: bool):
        # Barbero eq 3.9
        s = zbar_k**2 + t_k**2 / 12

        def ind(i):
            if i == 2:
                return 5
            return i

        coords = [0, 1, 2]
        for i in coords:
            for j in coords:

                Qbar_t = Qbar_k[ind(i), ind(j)] * t_k

                A[i, j] += Qbar_t
                B[i, j] += Qbar_t * zbar_k
                D[i, j] += Qbar_t * s

    def accumulate_H(t_k, zbar_k, Qbar_k, is_core: bool):
        s = zbar_k**2 + t_k**2 / 12
        if sandwich:
            if is_core:
                h = t_k
            else:
                h = 0
        else:
            h = (5.0 / 4) * t_k * (1.0 - 4 / total_thickness**2 * s)

        def ind(i):
            return i - 3

        coords = [3, 4]
        for i in coords:
            for j in coords:

                # TODO: Qbarstar
                H[ind(i), ind(j)] += Qbar_k[i, j] * h

    # iterate through layers
    for k, (zbar_k, lay) in enumerate(zip(zbar, layers)):

        t_k = lay.thickness
        p_k = t_k / total_thickness

        C_k, Qbar_k = material_shell_properties(
            lay.material,
            np.radians(lay.orientation),
        )
        C += p_k * C_k

        density += p_k * layer_density(lay)

        is_core = lay.core and sandwich

        accumulate_ABD(t_k, zbar_k, Qbar_k, is_core)
        accumulate_H(t_k, zbar_k, Qbar_k, is_core)

    # assemble full matrix
    ABD = np.block(
        [
            [A, B],
            [B, D],
        ]
    )

    def delete_row_col(row: int, col: int):
        a1 = np.delete(ABD, row, axis=0)
        return np.delete(a1, col, axis=1)

    def det_red(i, j):
        return np.linalg.det(delete_row_col(i, j))

    mat = {}
    det_ABD = np.linalg.det(ABD)

    dets = [det_red(i, i) for i in range(3)]
    mat["YoungsModulusX"] = det_ABD / (dets[0] * total_thickness)
    mat["YoungsModulusY"] = det_ABD / (dets[1] * total_thickness)
    mat["ShearModulusXY"] = det_ABD / (dets[2] * total_thickness)
    mat["PoissonRatioXY"] = det_red(0, 1) / dets[0]  # negative?
    mat["PoissonRatioYX"] = det_red(1, 0) / dets[1]  # negative?
    mat["ShearModulusYZ"] = H[0, 0] / total_thickness
    mat["ShearModulusXZ"] = H[1, 1] / total_thickness

    mat_thin = stiffness_matrix_to_engineering_properties(C)

    mat["Density"] = density
    mat["YoungsModulusZ"] = mat_thin["YoungsModulusZ"]
    mat["PoissonRatioXZ"] = mat_thin["PoissonRatioXZ"]  # ?
    mat["PoissonRatioYZ"] = mat_thin["PoissonRatioYZ"]  # ?

    del mat["PoissonRatioYX"]

    material = material_from_dict(mat, orthotropic=True)
    material["Name"] = prefix
    return HomogeneousLamina(
        material=material,
        thickness=total_thickness,
        orientation=0,
        orientation_display=0,
    )


def merge_single(
    prefix: str,
    layer: Lamina,
) -> HomogeneousLamina:

    # if not hasattr(layer, "orientation") or (layer.orientation == 0):
    #     return layer

    material = material_rotate(
        layer.material,
        np.radians(layer.orientation),
    )
    material["Name"] = prefix + ": " + layer.description
    return HomogeneousLamina(
        material=material,
        thickness=layer.thickness,
        orientation=0,
        orientation_display=layer.orientation,
    )
