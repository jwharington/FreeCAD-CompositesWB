# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Run real-FreeCAD integration tests and return a proper process exit code."""

import os
import sys
import traceback
import unittest


def _repo_root_from_here():
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    )


def main():
    try:
        repo_root = _repo_root_from_here()
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)

        import freecad.Composites.compositestests.test_integration_freecad as test_module

        suite = unittest.defaultTestLoader.loadTestsFromModule(test_module)
        print(f"Loaded {suite.countTestCases()} integration test(s)")
        result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(
            suite
        )
        raise SystemExit(0 if result.wasSuccessful() else 1)
    except Exception:  # pragma: no cover - integration script diagnostics
        traceback.print_exc()
        raise SystemExit(1)


main()
