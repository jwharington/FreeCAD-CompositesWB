from ..mechanics.material_properties import (
    mgr,
    material_from_dict,
)


def make_glass():
    material = material_from_dict({}, orthotropic=True)
    material.Name = "Glass"
    material.setPhysicalValue("Density", "2580.0 kg/m^3")
    material.setPhysicalValue("PoissonRatioXY", "0.28")
    material.setPhysicalValue("PoissonRatioXZ", "0.28")
    material.setPhysicalValue("PoissonRatioYZ", "0.5")
    material.setPhysicalValue("ShearModulusXY", "4500 MPa")
    material.setPhysicalValue("ShearModulusXZ", "4500 MPa")
    material.setPhysicalValue("ShearModulusYZ", "3500 MPa")
    material.setPhysicalValue("YoungsModulusX", "130 GPa")
    material.setPhysicalValue("YoungsModulusY", "10 GPa")
    material.setPhysicalValue("YoungsModulusZ", "10 GPa")
    # material.setPhysicalValue("ThermalExpansionCoefficientX", "5.3e-6 1/K")
    # material.setPhysicalValue("ThermalExpansionCoefficientY", "0.0 1/K")
    # material.setPhysicalValue("ThermalExpansionCoefficientZ", "0.0 1/K")
    mgr.save("User", material, "Glass.FCMat", overwrite=True)
    return material


def make_resin():
    material = material_from_dict({}, orthotropic=False)
    material.Name = "Epoxy"
    material.setPhysicalValue("Density", "1100.0 kg/m^3")
    material.setPhysicalValue("YoungsModulus", "3.500 GPa")
    material.setPhysicalValue("PoissonRatio", "0.36")
    # material.setPhysicalValue("ThermalExpansionCoefficient", "40.0e-6 1/K")
    mgr.save("User", material, "Epoxy.FCMat", overwrite=True)
    return material


def make_foam():
    material = material_from_dict({}, orthotropic=False)
    material.Name = "Foam"
    material.setPhysicalValue("Density", "75.0 kg/m^3")
    material.setPhysicalValue("YoungsModulus", "105 MPa")
    material.setPhysicalValue("PoissonRatio", "0.40")
    # material.setPhysicalValue("ThermalExpansionCoefficient", "40.0e-6 1/K")
    mgr.save("User", material, "Rohacell71.FCMat", overwrite=True)
    return material


glass = make_glass()
resin = make_resin()
foam = make_foam()
carbon = mgr.getMaterial("92589471-a6cb-4bbc-b748-d425a17dea7d")
aluminium = mgr.getMaterial("a02bf9d7-6e3e-4e36-881b-10779ee9f706")
