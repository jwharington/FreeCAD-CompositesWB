# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

from FreeCAD import Console

try:
    import BOPTools.SplitAPI

    splitAPI = BOPTools.SplitAPI
except ImportError:
    Console.PrintError("Failed importing BOPTools. Fallback to Part API\n")
    import Part

    splitAPI = Part.BOPTools.SplitAPI
