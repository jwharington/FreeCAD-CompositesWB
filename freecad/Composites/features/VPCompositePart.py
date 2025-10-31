from VPCompositeBase import (
    CompositeBaseFP,
    VPCompositeBase,
)


class CompositePartFP(CompositeBaseFP):
    pass


class VPCompositePart(VPCompositeBase):

    def attach(self, vobj):
        self.Object = vobj.Object
        self.ViewObject = vobj

    def getDisplayModes(self, obj):
        modes = []
        return modes

    def getDefaultDisplayMode(self) -> str:
        return "Flat Lines"

    def setDisplayMode(self, mode):
        return mode
