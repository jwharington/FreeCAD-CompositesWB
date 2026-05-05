# SPDX-License-Identifier: LGPL-2.1-or-later

import importlib
import importlib.util
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def load_plotting_module():
    path = os.path.join(
        _REPO_ROOT,
        "freecad",
        "Composites",
        "compositestests",
        "plotting.py",
    )
    spec = importlib.util.spec_from_file_location("fishnet_plotting", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_fishnet_module():
    import Part  # ensure native Part types are initialized before loading extension

    return importlib.import_module("freecad.Composites.fishnet")
