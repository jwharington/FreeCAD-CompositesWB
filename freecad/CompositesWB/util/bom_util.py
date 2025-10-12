from ..mechanics.stack_model_type import StackModelType
from ..objects.laminate import Laminate


def get_layers_bom(laminate: Laminate):
    if not laminate:
        return {}

    layers = laminate.get_layers(model_type=StackModelType.SmearedFabric)

    def name(k, lay):
        return f"{k:02d}:{lay.material['Name']}"

    def orientation(lay):
        return f"{lay.orientation_display:+03d}"

    return {name(k, lay): orientation(lay) for k, lay in enumerate(layers)}
