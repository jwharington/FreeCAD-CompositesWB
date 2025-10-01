from dataclasses import dataclass


@dataclass
class Lamina:
    core: bool = False
    thickness: float = 1

    @staticmethod
    def set_missing_child_props(parent, children, items):
        for la in children:
            for item in items:
                if hasattr(la, item) and not getattr(la, item):
                    value = getattr(parent, item)
                    setattr(la, item, value)
