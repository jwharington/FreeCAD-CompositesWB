from enum import Enum, auto


class StackModelType(Enum):
    Discrete = auto()
    SmearedFabric = auto()
    SmearedCore = auto()
    Smeared = auto()

    def merged_name(item):
        match item:
            case StackModelType.SmearedFabric:
                return "Fabric"
            case StackModelType.SmearedCore:
                return "Sublaminate"
            case StackModelType.Smeared:
                return "Laminate"
            case _:
                return ""
