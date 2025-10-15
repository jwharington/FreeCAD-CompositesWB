from .VPCompositeBase import VPCompositeBase
from .objects import Lamina


def is_lamina(obj):
    if obj.TypeId != "Part::FeaturePython":
        return False
    if not obj.Proxy:
        return False
    if obj.Proxy.Type != "Fem::MaterialMechanicalLamina":
        return False
    return True


class BaseLaminaFP:

    Type = "Fem::MaterialMechanicalLamina"

    def __init__(self, obj):
        obj.Proxy = self
        obj.addExtension("App::SuppressibleExtensionPython")

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

    def get_model(self, obj) -> Lamina:
        return None

    def __getstate__(self):
        return {}

    def __setstate__(self, state):
        return None


class BaseViewProviderLamina(VPCompositeBase):

    def updateData(self, vobj, prop):
        # Update visual data based on feature properties
        pass
