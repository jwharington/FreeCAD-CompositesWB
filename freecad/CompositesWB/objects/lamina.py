from dataclasses import dataclass
from ..mechanics.stack_model_type import StackModelType


@dataclass
class Lamina:
    core: bool = False
    thickness: float = 1.0

    @staticmethod
    def set_missing_child_props(parent, children, items):
        for la in children:
            for item in items:
                if hasattr(la, item) and not getattr(la, item):
                    value = getattr(parent, item)
                    setattr(la, item, value)

    def get_layers(
        self,
        model_type: StackModelType = StackModelType.Discrete,
    ):
        return [self]
