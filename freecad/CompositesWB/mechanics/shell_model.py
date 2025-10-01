from .material_properties import (
    Material,
    ortho_material2dict,
    iso_material2dict,
    material_from_dict,
    is_orthotropic,
)
import numpy as np


def rotation_matrix_zaxis(angle_rad: float):
    """Matrix for rotating lamina coordinates around the z-axis."""
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    c2 = c * c
    s2 = s * s
    cs = c * s
    # Barbero:2008 p. 12 & 15
    T = np.eye(6)
    T[0, 0] = c2
    T[0, 1] = s2
    T[0, 5] = cs
    T[1, 0] = s2
    T[1, 1] = c2
    T[1, 5] = -cs
    T[3, 3] = c
    T[3, 4] = -s
    T[4, 3] = s
    T[4, 4] = c
    T[5, 0] = -2 * cs
    T[5, 1] = 2 * cs
    T[5, 5] = c2 - s2
    return T


def stiffness_matrix_to_engineering_properties(C):
    mat = {}
    Sp = np.linalg.inv(C)
    mat["YoungsModulusX"] = 1 / Sp[0, 0]
    mat["YoungsModulusY"] = 1 / Sp[1, 1]
    mat["YoungsModulusZ"] = 1 / Sp[2, 2]

    mat["PoissonRatioXY"] = -mat["YoungsModulusX"] * Sp[0, 1]
    mat["PoissonRatioYZ"] = -mat["YoungsModulusY"] * Sp[1, 2]
    mat["PoissonRatioXZ"] = -mat["YoungsModulusX"] * Sp[0, 2]

    mat["ShearModulusYZ"] = 1 / Sp[3, 3]
    mat["ShearModulusXZ"] = 1 / Sp[4, 4]
    mat["ShearModulusXY"] = 1 / Sp[5, 5]
    return mat


def compliance_matrix(
    material: Material,
    reduced: bool = False,
):
    # Sp = S'
    Sp = np.zeros((6, 6))

    if is_orthotropic(material):
        mat = ortho_material2dict(material)

        # Barbero FEM/Abaqus eq 1.91 p27
        Sp[0, 0] = 1 / mat["YoungsModulusX"]
        Sp[0, 1] = -mat["PoissonRatioXY"] / mat["YoungsModulusX"]
        Sp[1, 0] = Sp[0, 1]
        Sp[1, 1] = 1 / mat["YoungsModulusY"]

        if not reduced:
            Sp[1, 2] = -mat["PoissonRatioYZ"] / mat["YoungsModulusY"]
            Sp[0, 2] = -mat["PoissonRatioXZ"] / mat["YoungsModulusX"]
            Sp[2, 0] = Sp[0, 2]
            Sp[2, 1] = Sp[1, 2]

        Sp[2, 2] = 1 / mat["YoungsModulusZ"]
        Sp[3, 3] = 1 / mat["ShearModulusYZ"]
        Sp[4, 4] = 1 / mat["ShearModulusXZ"]
        Sp[5, 5] = 1 / mat["ShearModulusXY"]

    else:
        mat = iso_material2dict(material)

        for i in range(3):
            Sp[i, i] = 1 / mat["YoungsModulus"]
            Sp[i + 3, i + 3] = (1 + mat["PoissonRatio"]) / mat["YoungsModulus"]
        Sp[0, 1] = -mat["PoissonRatio"] / mat["YoungsModulus"]
        Sp[0, 2] = -mat["PoissonRatio"] / mat["YoungsModulus"]
        Sp[1, 0] = -mat["PoissonRatio"] / mat["YoungsModulus"]
        Sp[1, 2] = -mat["PoissonRatio"] / mat["YoungsModulus"]
        Sp[2, 0] = -mat["PoissonRatio"] / mat["YoungsModulus"]
        Sp[2, 1] = -mat["PoissonRatio"] / mat["YoungsModulus"]
    return Sp


def material_stiffness_matrix(
    material: Material,
    reduced: bool = False,
):
    Sp = compliance_matrix(material, reduced=reduced)
    return np.linalg.inv(Sp)


def rotate_stiffness_matrix(C: np.array, Tbar: np.array):
    return Tbar.T @ C @ Tbar


def material_shell_properties(material: Material, angle_rad: float):
    Cp = material_stiffness_matrix(material, reduced=False)
    Qp = material_stiffness_matrix(material, reduced=True)
    if is_orthotropic(material):
        Tbar = rotation_matrix_zaxis(angle_rad)
        C = rotate_stiffness_matrix(Cp, Tbar)
        Qbar = rotate_stiffness_matrix(Qp, Tbar)
        return C, Qbar
    else:
        return Cp, Qp


def material_rotate(material: Material, angle_rad: float):
    if not is_orthotropic(material):
        return material
    mat_old = ortho_material2dict(material)
    Tbar = rotation_matrix_zaxis(angle_rad)
    Cp = material_stiffness_matrix(material, reduced=False)
    C = rotate_stiffness_matrix(Cp, Tbar)
    mat = stiffness_matrix_to_engineering_properties(C)
    mat["Density"] = mat_old["Density"]
    return material_from_dict(mat, orthotropic=True)

    # out = {}
    # m, n = np.cos(angle_rad), np.sin(angle_rad)
    # # The powers of the sine and cosine are often used later.
    # m2 = m * m
    # m3, m4 = m2 * m, m2 * m2
    # n2 = n * n
    # n3, n4 = n2 * n, n2 * n2
    # out["CTEX"] = mat["CTEX"] * m2 + mat["CTEY"] * n2
    # out["CTEY"] = mat["CTEX"] * n2 + mat["CTEY"] * m2
    # out["CTEZ"] = mat["CTEZ"]
    # out["CTEXY"] = 2 * (mat["CTEX"] - mat["CTEY"]) * m * n

    # thickness_fibre = area_weight_fibre / fibre.density
    # fiber_thickness = fiber_weight / (fiber.ρ * 1000)
    # thickness = fiber_thickness * (1 + vm / vf)
    # resin_weight = thickness * vm * resin.ρ * 1000  # Resin [g/m²]
