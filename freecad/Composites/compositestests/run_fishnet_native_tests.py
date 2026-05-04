"""Run test_fishnet_native.py via FreeCADCmd (Python 3.11 + flatmesh available)."""

import os
import sys
import unittest


def main():
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    )
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    import freecad.Composites.compositestests.test_fishnet_native as test_module

    suite = unittest.defaultTestLoader.loadTestsFromModule(test_module)
    print(f"Loaded {suite.countTestCases()} fishnet native test(s)", flush=True)
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


main()
