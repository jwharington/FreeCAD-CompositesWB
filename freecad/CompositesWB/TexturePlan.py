import FreeCAD
import FreeCADGui
import Part
from . import TEXTURE_PLAN_TOOL_ICON


class TexturePlanFP:

    Type = "Composite::TexturePlan"

    def __init__(self, obj):
        obj.Proxy = self
        obj.addExtension("App::SuppressibleExtensionPython")

        obj.addProperty(
            type="App::PropertyLinkListGlobal",
            name="CompositeShell",
            group="References",
            doc="Composite Shells to unwrap",
        ).CompositeShell = []

    def execute(self, fp):
        for obj in fp.CompositeShell:
            if "Composite::Shell" != obj.Proxy.Type:
                FreeCAD.Console.PrintError(f"Incorrect type {obj.Name}\n")
                continue
            # TODO: lay out separate shapes for each layer in the composites
            for key, orientation in obj.Laminate.StackAssembly.items():
                print(f"name {obj.Name} key {key} orientation {orientation}")
                boundaries = obj.Proxy.get_boundaries(offset_angle_deg=int(orientation))
                if not boundaries:
                    continue
                for w in boundaries:
                    fp.Shape = Part.Wire(Part.makePolygon(w))

        # fp.ViewObject.update()

    def onDocumentRestored(self, fp):
        # super().onDocumentRestored(fp)
        fp.recompute()

    def onChanged(self, fp, prop):
        match prop:
            case "CompositeShell":
                fp.recompute()


class ViewProviderTexturePlan:

    def __init__(self, obj):
        obj.Proxy = self

    def getDisplayModes(self, obj):
        return []

    def getDefaultDisplayMode(self):
        return "Wireframe"

    def getIcon(self):
        return TEXTURE_PLAN_TOOL_ICON

    def attach(self, vobj):
        self.Object = vobj.Object
        self.ViewObject = vobj

    # def updateData(self, fp, prop):
    #     match prop:
    #         case _:
    #             return

    # def onChanged(self, vobj, prop):
    #     match prop:
    #         case _:
    #             pass

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None


class TexturePlanCommand:
    def GetResources(self):
        return {
            "Pixmap": TEXTURE_PLAN_TOOL_ICON,
            "MenuText": "TexturePlan",
            "ToolTip": "Composite shell",
        }

    def Activated(self):
        doc = FreeCAD.ActiveDocument
        obj = doc.addObject(
            "Part::FeaturePython",
            "TexturePlan",
        )
        # selection = FreeCADGui.Selection.getSelectionEx()
        TexturePlanFP(obj)
        if FreeCAD.GuiUp:
            ViewProviderTexturePlan(obj.ViewObject)
            # FreeCADGui.Selection.clearSelection()
            # FreeCADGui.ActiveDocument.setEdit(doc.ActiveObject)
        doc.recompute()

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None


FreeCADGui.addCommand(
    "Composites_TexturePlan",
    TexturePlanCommand(),
)
