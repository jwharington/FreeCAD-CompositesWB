from pivy import coin


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

    def get_model(self, obj, parent):
        return None

    def __getstate__(self):
        return {}

    def __setstate__(self, state):
        return None


class BaseViewProviderLamina:
    def __init__(self, obj):
        obj.Proxy = self

    def attach(self, obj):
        self.standard = coin.SoGroup()
        obj.addDisplayMode(self.standard, "Standard")
        self.ViewObject = obj
        self.Object = obj.Object

    def getDisplayModes(self, obj):
        return ["Standard"]

    def getDefaultDisplayMode(self):
        return "Standard"

    def setDisplayMode(self, mode):
        return mode

    def updateData(self, vobj, prop):
        # Update visual data based on feature properties
        pass

    def __getstate__(self):
        return {}

    def __setstate__(self, state):
        return None
