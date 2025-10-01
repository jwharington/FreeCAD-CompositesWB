from .material_properties import (
    Material,
    ortho_material2dict,
    iso_material2dict,
    material_from_dict,
)


def calc_fibre_composite_model(
    material_fibre: Material,
    material_matrix: Material,
    volume_fraction_fibre: float,
    thermal: bool = False,
) -> Material:

    assert material_fibre, "no fibre material"
    assert material_matrix, "no matrix material"

    def mix(val_a, val_b):
        vf = volume_fraction_fibre
        return vf * val_a + (1 - vf) * val_b

    fibre = ortho_material2dict(material_fibre)
    matrix = iso_material2dict(material_matrix)

    matdict = {}
    matdict["Density"] = mix(fibre["Density"], matrix["Density"])

    # Hyer:1998, p. 115, (3.32)
    matdict["YoungsModulusX"] = mix(
        fibre["YoungsModulusX"],
        matrix["YoungsModulus"],
    )

    # Use the Halpin-Tsai formula for E2.

    # Giner, 2014
    ξ = 1.5
    valid_range = (0.25, 0.56)
    if (volume_fraction_fibre > valid_range[1]) or (
        volume_fraction_fibre < valid_range[0]
    ):
        raise ValueError(
            f"Volume fraction fibre {volume_fraction_fibre}"
            f" out of bounds {valid_range}"
        )

    t = fibre["YoungsModulusX"] / matrix["YoungsModulus"]
    η = (t - 1) / (t + ξ)
    t = (1 + ξ * η * volume_fraction_fibre) / (1 - η * volume_fraction_fibre)

    # Barbero:2018, p. 117
    matdict["YoungsModulusY"] = matrix["YoungsModulus"] * t

    # Barbero:2018, p. 118
    matdict["PoissonRatioXY"] = mix(
        fibre["PoissonRatioXY"],
        matrix["PoissonRatio"],
    )

    # The matrix-dominated cylindrical assemblage model is used for G12.
    t = 2 * (1 + matrix["PoissonRatio"])
    Gm = matrix["YoungsModulus"] / t

    t = (1 + volume_fraction_fibre) / (1 - volume_fraction_fibre)
    matdict["ShearModulusXY"] = Gm * t

    # Nettles:1994, p. 4, used temporarily
    t = matdict["YoungsModulusY"] / matdict["YoungsModulusX"]
    matdict["PoissonRatioYX"] = matdict["PoissonRatioXY"] * t

    # Calculate G23, necessary for Qs44.
    def get_K(E, nu):
        t = 3 * (1 - 2 * nu)
        return E / t

    Kf = get_K(fibre["YoungsModulusX"], fibre["PoissonRatioXY"])
    Km = get_K(matrix["YoungsModulus"], matrix["PoissonRatio"])
    K = 1.0 / mix(1.0 / Kf, 1.0 / Km)
    t = matdict["YoungsModulusY"] / (3 * K)

    # Barbero:2008, p. 23, Barbero:2018, p. 504
    matdict["PoissonRatioYZ"] = 1 - matdict["PoissonRatioYX"] - t

    t = 2 * (1 + matdict["PoissonRatioYZ"])
    matdict["ShearModulusYZ"] = matdict["YoungsModulusY"] / t

    # Assumed for UD layers.
    matdict["YoungsModulusZ"] = matdict["YoungsModulusY"]
    matdict["PoissonRatioXZ"] = matdict["PoissonRatioXY"]
    matdict["ShearModulusXZ"] = matdict["ShearModulusXY"]

    del matdict["PoissonRatioYX"]

    if thermal:
        matdict["ThermalExpansionCoefficientX"] = (
            mix(
                fibre["ThermalExpansionCoefficientX"] * fibre["YoungsModulusX"],
                matrix["ThermalExpansionCoefficient"] * matrix["YoungsModulus"],
            )
            / fibre["YoungsModulusX"]
        )

        # Since α2 properties of fibers are hard to come by,
        # we have to estimate.it
        # This is based on our own measurements.
        # α2 = vf * resin.α  # This is not 100% accurate, but simple.

        t = volume_fraction_fibre * matrix["ThermalExpansionCoefficient"]

        matdict["ThermalExpansionCoefficientY"] = t
        matdict["ThermalExpansionCoefficientZ"] = t

    # vfrac = int(volume_fraction_fibre * 100)
    material = material_from_dict(matdict, orthotropic=True)
    material.Name = f"{material_fibre.Name}-{material_matrix.Name}"
    return material
