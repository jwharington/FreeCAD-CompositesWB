# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from FreeCAD import Console
import FreeCADGui
from typing import ClassVar
from .Container import getCompositesContainer
from .. import debug

# from .util.selection_utils import find_face_in_selection_object


class BaseCommand:

    icon: ClassVar[str]
    menu_text: ClassVar[str]
    tool_tip: ClassVar[str]
    sel_args: ClassVar[list]
    type_id: ClassVar[str]
    instance_name: ClassVar[str]
    cls_fp: ClassVar[type]
    cls_vp: ClassVar[type]

    debug: bool = False

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

                def check_match(o, item, entry):
                    if imatch(o, item):
                        if "array" in item:
                            add_array(entry, item, present)
                        else:
                            add_scalar(entry, item, present)
                        return True
                    return False

                ok |= check_match(s.Object, item, s.Object)
                if (not ok) and s.HasSubObjects:
                    for sub, name in zip(s.SubObjects, s.SubElementNames):
                        if check_match(sub, item, (s.Object, name)):
                            ok = True
                            if "array" in item:
                                continue
                            else:
                                break
                if ok:
                    if "array" in item:
                        continue
                    else:
                        break
                else:
                    neglected.append(s)
            if neglected:
                sel.extend(neglected)
            return ok

        sel = FreeCADGui.Selection.getSelectionEx()
        if debug or self.debug:
            sel_objs = [s.Object for s in sel]
            Console.PrintLog(f"selected {sel_objs}")

        present = []
        missing = []

        ok = True
        for item in self.sel_args:
            if check_match(sel, item, present):
                continue
            missing.append(item)
            if "optional" not in item:
                if report and (debug or self.debug):
                    Console.PrintLog(f"missing non-optional {item['key']}")
                ok = False

        res = {p["key"]: p["value"] for p in present}
        if report and (debug or self.debug):
            Console.PrintLog(f"{self.__class__} res: {res}")
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
            if hasattr(cls, "_taskPanel") and cls._taskPanel:
                FreeCADGui.ActiveDocument.setEdit(doc.ActiveObject)
        getCompositesContainer().addObject(obj)
        FreeCADGui.Selection.clearSelection()
        doc.recompute()

    def IsActive(self):
        if FreeCAD.ActiveDocument is None:
            return False
        return self.check_sel(False or self.debug) is not None
