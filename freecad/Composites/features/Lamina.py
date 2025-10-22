# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from .. import is_comp_type
from ..objects import Lamina
from .VPCompositeBase import VPCompositeBase, BaseFP


def is_lamina(obj):
    return is_comp_type(
        obj,
        "App::FeaturePython",
        "Fem::MaterialMechanicalLamina",
    )


class BaseLaminaFP(BaseFP):

    Type = "Fem::MaterialMechanicalLamina"

    def __init__(self, obj):

        obj.addProperty(
            "App::PropertyBool",
            "Core",
            "Model",
            "Model as core or thin structure",
        ).Core = False

        obj.addProperty(
            "App::PropertyAngle",
            "Angle",
            "Model",
            "Planar angular offset",
        ).Angle = False

        obj.addProperty(
            "App::PropertyLength",
            "Thickness",
            "Model",
            "Thickness of layer",
        ).Thickness = 0.1

        super().__init__(obj)

    def get_model(self, obj) -> Lamina:
        return None


class BaseViewProviderLamina(VPCompositeBase):
    pass
