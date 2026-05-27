# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Unit/smoke coverage for the compositeexamples framework.

These tests validate registry and runner behaviour and ensure example build
paths run with ``run_solver=False`` without requiring a hard solver/runtime.
"""

import builtins
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# FreeCAD mock — must be installed before importing freecad.Composites.
# ---------------------------------------------------------------------------

_freecad_mock = MagicMock()
_freecad_mock.__unit_test__ = []
_freecad_mock.Base = types.SimpleNamespace(
    Precision=types.SimpleNamespace(
        confusion=lambda: 1e-7,
        parametric=lambda _tol: 1e-9,
    )
)
_freecad_mock.ParamGet.return_value = MagicMock()

sys.modules["FreeCAD"] = _freecad_mock
sys.modules["CompositesWB"] = MagicMock()

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path so package imports work.
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from freecad.Composites.compositeexamples import registry, runner  # noqa: E402


class TestCompositeExamplesRegistry(unittest.TestCase):
    def test_list_examples_is_sorted(self):
        examples = registry.list_examples()
        self.assertEqual(examples, sorted(examples))
        self.assertIn("ud_plate_basic", examples)
        self.assertIn("quasi_iso_laminate_plate", examples)

    def test_get_example_module_unknown_raises(self):
        with self.assertRaises(ValueError) as ctx:
            registry.get_example_module("does_not_exist")

        msg = str(ctx.exception)
        self.assertIn("Unknown example 'does_not_exist'", msg)
        self.assertIn("Available examples", msg)


class TestCompositeExamplesRunner(unittest.TestCase):
    def test_run_calls_example_build_with_arguments(self):
        doc = object()
        expected = {"ok": True}
        module = types.SimpleNamespace(build=MagicMock(return_value=expected))

        with patch.object(
            registry,
            "get_example_module",
            return_value=module,
        ) as get_example:
            result = runner.run("dummy", run_solver=False, doc=doc)

        get_example.assert_called_once_with("dummy")
        module.build.assert_called_once_with(doc=doc, run_solver=False)
        self.assertIs(result, expected)

    def test_run_raises_when_build_not_callable(self):
        module = types.SimpleNamespace(build=None)

        with patch.object(registry, "get_example_module", return_value=module):
            with self.assertRaises(AttributeError):
                runner.run("dummy", run_solver=False, doc=None)


class TestCompositeExamplesSmoke(unittest.TestCase):
    def test_build_paths_do_not_require_solver_when_disabled(self):
        doc = MagicMock()
        doc.recompute.side_effect = AssertionError(
            "recompute must not be called when run_solver=False",
        )

        for example_id in registry.list_examples():
            with self.subTest(example=example_id):
                result = runner.run(example_id, run_solver=False, doc=doc)
                self.assertIn("laminate", result)
                self.assertIs(result["doc"], doc)
                doc.recompute.assert_not_called()

    def test_build_paths_work_without_freecad_import(self):
        original_import = builtins.__import__

        def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "FreeCAD":
                raise ImportError("simulated missing FreeCAD")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=_guarded_import):
            for example_id in registry.list_examples():
                with self.subTest(example=example_id):
                    result = runner.run(example_id, run_solver=False, doc=None)
                    self.assertIn("laminate", result)
                    self.assertIsNone(result["doc"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
