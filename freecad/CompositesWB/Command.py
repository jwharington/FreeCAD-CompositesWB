import FreeCAD
import FreeCADGui
from . import getCompositesContainer
from typing import ClassVar

# from .selection_utils import find_face_in_selection_object

debug: bool = True


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

        def add_scalar(s, item, present):
            it = item | {"value": s}
            present.append(it)

        def add_array(s, item, present):
            for q in present:
                if q["key"] == item["key"]:
                    q["value"].append(s)
                    return
            add_scalar([s], item, present)

        def imatch(s, item):
            if ("type" in item) and not s.isDerivedFrom(item["type"]):
                return False
            if ("test" in item) and not item["test"](s):
                return False
            return True

        def check_match(sel, item, present):
            ok = False
            neglected = []
            while len(sel):
                s = sel.pop(0)
                if imatch(s, item):
                    if "array" in item:
                        add_array(s, item, present)
                    else:
                        add_scalar(s, item, present)
                    ok = True
                else:
                    neglected.append(s)
            if neglected:
                sel.extend(neglected)
            return ok

        sel = FreeCADGui.Selection.getSelection()

        present = []
        missing = []

        ok = True
        for item in self.sel_args:
            if check_match(sel, item, present):
                continue
            missing.append(item)
            if "optional" not in item:
                if report and debug:
                    print(f"missing non-optional {item['key']}")
                ok = False

        res = {p["key"]: p["value"] for p in present}
        if report and debug:
            print(f"res: {res}")
        if ok:
            return res
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
            FreeCADGui.ActiveDocument.setEdit(doc.ActiveObject)
        getCompositesContainer().addObject(obj)
        FreeCADGui.Selection.clearSelection()
        doc.recompute()

    def IsActive(self):
        if FreeCAD.ActiveDocument is None:
            return False
        return self.check_sel(False or debug) is not None
