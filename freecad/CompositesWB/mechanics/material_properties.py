from typing import List
from Materials import (
    MaterialManager,
    Material,
    UUIDs,
)
from FreeCAD import Units


common_items = [("Density", "t/mm^3")]  # "kg/m^3")]


iso_items = [
    ("YoungsModulus", "MPa"),
    ("PoissonRatio", ""),
    # "ThermalExpansionCoefficient",
] + common_items


ortho_items = [
    ("YoungsModulusX", "MPa"),
    ("YoungsModulusY", "MPa"),
    ("YoungsModulusZ", "MPa"),
    ("PoissonRatioXY", ""),
    ("PoissonRatioXZ", ""),
    ("PoissonRatioYZ", ""),
    ("ShearModulusXY", "MPa"),
    ("ShearModulusXZ", "MPa"),
    ("ShearModulusYZ", "MPa"),
    # "ThermalExpansionCoefficientX",
    # "ThermalExpansionCoefficientY",
    # "ThermalExpansionCoefficientZ",
] + common_items


mgr = MaterialManager()
uuids = UUIDs()


def material2dict(material: Material, items: List[str]):
    def value(item, units):
        val = material.getPhysicalValue(item)
        if val is None:
            raise ValueError(f"No {item} defined in {material.Name}")
        if units:
            return float(Units.Quantity(val).getValueAs(units))
        else:
            return float(val)

    return {item: value(item, units) for item, units in items}


def dict2material(material: Material, items: List[str], d: dict):
    for k, u in items:
        if k in d:
            v = d[k]
            if u:
                material.setPhysicalValue(k, f"{v} {u}")
            else:
                material.setPhysicalValue(k, f"{v}")


def iso_material2dict(material: Material):
    return material2dict(material, iso_items)


def ortho_material2dict(material: Material):
    return material2dict(material, ortho_items)


def common_material2dict(material: Material):
    return material2dict(material, common_items)


def iso_dict2material(material: Material, d: dict):
    return dict2material(material, iso_items, d)


def ortho_dict2material(material: Material, d: dict):
    return dict2material(material, ortho_items, d)


def is_orthotropic(material: Material):
    return material.hasPhysicalModel(uuids.OrthotropicLinearElastic)


def material_from_dict(mat, orthotropic=False):
    material = Material()
    material.addPhysicalModel(uuids.LinearElastic)
    if orthotropic:
        material.addPhysicalModel(uuids.OrthotropicLinearElastic)
        ortho_dict2material(material, mat)
    else:
        iso_dict2material(material, mat)
    return material
