# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

import FreeCAD
import FreeCADGui
from pivy import coin


class FPBase:
    def __init__(self, obj):
        obj.addExtension("App::SuppressibleExtensionPython")
        obj.Proxy = self

    def __getstate__(self):
        return {}

    def __setstate__(self, state):
        return None

    def onDocumentRestored(self, obj):
        if not obj.hasExtension("App::SuppressibleExtensionPython"):
            obj.addExtension("App::SuppressibleExtensionPython")
        obj.recompute()


class VPCompositeBase:
    # based on view_base_femobject.py
    _taskPanel = None

    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = (
            vobj.Object
        )  # used on various places, claim childreens, get icon, etc.
        self.ViewObject = vobj
        self.standard = coin.SoGroup()
        vobj.addDisplayMode(self.standard, "Standard")

    def setEdit(self, vobj, mode=0):
        if self._taskPanel is None:
            # avoid edit mode by return False
            # https://forum.freecad.org/viewtopic.php?t=12139&start=10#p161062
            return False
        # show task panel
        task = self._taskPanel(vobj.Object)
        FreeCADGui.Control.showDialog(task)
        return True

    def unsetEdit(self, vobj, mode=0):
        FreeCADGui.Control.closeDialog()
        return True

    def doubleClicked(self, vobj):
        guidoc = FreeCADGui.getDocument(vobj.Object.Document)
        # check if another VP is in edit mode
        # https://forum.freecad.org/viewtopic.php?t=13077#p104702
        if not guidoc.getInEdit():
            guidoc.setEdit(vobj.Object.Name)
        else:
            from PySide.QtGui import QMessageBox

            message = (
                "Active Task Dialog found! "
                "Please close this one before opening a new one!"
            )
            QMessageBox.critical(None, "Error in tree view", message)
            FreeCAD.Console.PrintError(message + "\n")
        return True

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

    # they are needed, see:
    # https://forum.freecad.org/viewtopic.php?f=18&t=44021
    # https://forum.freecad.org/viewtopic.php?f=18&t=44009
    def dumps(self):
        return None

    def loads(self, state):
        return None

    def claimChildren(self):
        return []
