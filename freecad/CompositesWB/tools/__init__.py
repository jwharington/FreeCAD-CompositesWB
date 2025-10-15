from FreeCAD import Console

try:
    import BOPTools.SplitAPI

    splitAPI = BOPTools.SplitAPI
except ImportError:
    Console.PrintError("Failed importing BOPTools. Fallback to Part API\n")
    import Part

    splitAPI = Part.BOPTools.SplitAPI
