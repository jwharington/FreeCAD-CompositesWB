# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com


from ..mechanics.material_properties import (
    material_from_dict,
)


def make_glass():
    material = material_from_dict({}, orthotropic=True)
    material["Name"] = "Glass"
    material["Density"] = "2580.0 kg/m^3"
    material["PoissonRatioXY"] = "0.28"
    material["PoissonRatioXZ"] = "0.28"
    material["PoissonRatioYZ"] = "0.50"
    material["ShearModulusXY"] = "4500 MPa"
    material["ShearModulusXZ"] = "4500 MPa"
    material["ShearModulusYZ"] = "3500 MPa"
    material["YoungsModulusX"] = "130 GPa"
    material["YoungsModulusY"] = "10 GPa"
    material["YoungsModulusZ"] = "10 GPa"
    # material.setPhysicalValue("ThermalExpansionCoefficientX", "5.3e-6 1/K")
    # material.setPhysicalValue("ThermalExpansionCoefficientY", "0.0 1/K")
    # material.setPhysicalValue("ThermalExpansionCoefficientZ", "0.0 1/K")
    return material


def make_resin():
    material = material_from_dict({}, orthotropic=False)
    material["Name"] = "Epoxy"
    material["Density"] = "1100.0 kg/m^3"
    material["YoungsModulus"] = "3.500 GPa"
    material["PoissonRatio"] = "0.36"
    # material.setPhysicalValue("ThermalExpansionCoefficient", "40.0e-6 1/K")
    return material


def make_foam():
    material = material_from_dict({}, orthotropic=False)
    material["Name"] = "Foam"
    material["Density"] = "75.0 kg/m^3"
    material["YoungsModulus"] = "105 MPa"
    material["PoissonRatio"] = "0.40"
    # material.setPhysicalValue("ThermalExpansionCoefficient", "40.0e-6 1/K")
    return material


glass = make_glass()
resin = make_resin()
foam = make_foam()
