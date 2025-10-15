import FreeCAD
import FreeCADGui
from . import getCompositesContainer
from typing import ClassVar

# from .selection_utils import find_face_in_selection_object


class BaseCommand:

    icon: ClassVar[str]
    menu_text: ClassVar[str]
    tool_tip: ClassVar[str]
    sel_args: ClassVar[list]
    type_id: ClassVar[str]
    instance_name: ClassVar[str]
    cls_fp: ClassVar[type]
    cls_vp: ClassVar[type]

    def GetResources(self):
        return {
            "Pixmap": self.icon,
            "MenuText": self.menu_text,
            "ToolTip": self.tool_tip,
        }

    def check_sel(self, report: bool = False):
        sel = FreeCADGui.Selection.getSelection()
        present = []
        missing = []

        if report:
            for s in sel:
                print(f"{type(s)} {s.TypeId}")

        def check_match(item):
            for k, s in enumerate(sel):
                found = True
                if ("type" in item) and not s.isDerivedFrom(item["type"]):
                    found = False
                elif ("test" in item) and not item["test"](s):
                    found = False
                if not found:
                    continue
                it = item | {"value": s}
                present.append(it)
                if report:
                    print(f"found {it}")
                del sel[k]
                return True
            return False

        ok = True
        for item in self.sel_args:
            if check_match(item):
                continue
            missing.append(item)
            if "optional" not in item:
                if report:
                    print(f"missing non-optional {item['key']}")
                ok = False

        if ok:
            return {p["key"]: p["value"] for p in present}
        return None

    def Activated(self):
        if (sel := self.check_sel(True)) is None:
            return

        doc = FreeCAD.ActiveDocument
        obj = doc.addObject(
            self.type_id,
            self.instance_name,
        )
        cls = self.cls_fp
        cls(obj, **sel)
        if FreeCAD.GuiUp:
            cls = self.cls_vp
            cls(obj.ViewObject)
            # FreeCADGui.ActiveDocument.setEdit(doc.ActiveObject)
        getCompositesContainer().addObject(obj)
        FreeCADGui.Selection.clearSelection()
        doc.recompute()

    def IsActive(self):
        return (FreeCAD.ActiveDocument is not None) and (
            self.check_sel(False) is not None
        )
