from ..mechanics.stack_model_type import StackModelType
from ..objects.homogeneous_lamina import HomogeneousLamina
from ..objects.laminate import Laminate
from ..mechanics.stack_model import merge_single
from ..mechanics.material_properties import (
    is_orthotropic,
    ortho_material2dict,
    iso_material2dict,
)
from typing import List


def get_layers_ccx(
    laminate: Laminate,
    model_type: StackModelType = StackModelType.Discrete,
):
    if not laminate:
        return []

    layers = laminate.get_layers(model_type=model_type)
    n = len(layers)

    def merge(k, lay):
        if n < 100:
            prefix = f"{k:02d}"
        else:
            prefix = f"{k:03d}"
        return merge_single(prefix, lay)

    return [merge(k, lay) for k, lay in enumerate(layers)]


def format_material_name(name: str, prefix: str = ""):
    if len(name) >= 80:
        raise ValueError(
            f"Name '{name}' invalid, exceeds maximum " "length 80 chars",
        )
    if "." in name:
        raise ValueError(
            f"Name {name} contains invalid character",
        )
    return f"{prefix}:{name}".upper()


def write_lamina_material_ccx(
    layer: HomogeneousLamina,
    prefix: str = "",
):
    material_name = format_material_name(layer.description, prefix)
    res = f"*MATERIAL,NAME={material_name}\n"
    res += "*ELASTIC,"
    if is_orthotropic(layer.material):
        mat = ortho_material2dict(layer.material)
        res += "TYPE=ENGINEERING CONSTANTS\n"
        res += f"{mat['YoungsModulusX']:.12G},"
        res += f"{mat['YoungsModulusY']:.12G},"
        res += f"{mat['YoungsModulusZ']:.12G},"
        res += f"{mat['PoissonRatioXY']:.12G},"
        res += f"{mat['PoissonRatioXZ']:.12G},"
        res += f"{mat['PoissonRatioYZ']:.12G},"
        res += f"{mat['ShearModulusXY']:.12G},"
        res += f"{mat['ShearModulusXZ']:.12G},\n"
        res += f"{mat['ShearModulusYZ']:.12G},"
    else:
        mat = iso_material2dict(layer.material)
        res += "TYPE=ISO\n"
        res += f"{mat['YoungsModulus']:.12G},"
        res += f"{mat['PoissonRatio']:.12G},"
    res += "293.15\n\n"

    res += "*DENSITY\n"
    res += f"{mat['Density']:.12G}\n"
    return res


def write_lamina_materials_ccx(
    layers: List[HomogeneousLamina],
    prefix: str = "",
):
    res = ""
    for la in layers:
        res += write_lamina_material_ccx(la, prefix=prefix)
    return res


def write_shell_section_ccx(
    prefix: str,
    layers: List[HomogeneousLamina],
):
    res = ""
    for layer in layers:
        res += f"{layer.thickness:.13G}"
        material_name = format_material_name(
            layer.description,
            prefix=prefix,
        )
        res += f",,{material_name}\n"
    res += "\n"
    return res


def test_ccx(
    la: Laminate,
    model_type: StackModelType = StackModelType.Discrete,
    prefix: str = "",
):
    res = ""
    layers = get_layers_ccx(la, model_type=model_type)
    res += write_lamina_materials_ccx(
        layers,
        prefix=prefix,
    )
    # this happens for each element and orientation
    res += write_shell_section_ccx(
        prefix=prefix,
        layers=layers,
    )
    print(res)


# composite only used if more than one

# name of the material to be used for this layer (required)
# name of the orientation to be used for this layer (optional)
