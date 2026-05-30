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
_freecad_mock.GuiUp = False

sys.modules["FreeCAD"] = _freecad_mock
sys.modules["CompositesWB"] = MagicMock()
sys.modules.setdefault("Part", MagicMock())

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path so package imports work.
# ---------------------------------------------------------------------------

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from freecad.Composites.compositeexamples import registry, runner  # noqa: E402
from freecad.Composites.compositeexamples.examples import (  # noqa: E402
    _shell_example_common,
    tubular_shell,
)


class TestCompositeExamplesRegistry(unittest.TestCase):
    def test_list_examples_is_sorted(self):
        examples = registry.list_examples()
        self.assertEqual(examples, sorted(examples))
        self.assertIn("ud_plate_basic", examples)
        self.assertIn("quasi_iso_laminate_plate", examples)
        self.assertIn("tubular_shell", examples)
        self.assertIn("flat_panel_spline_hole", examples)
        self.assertIn("double_curvature_panel", examples)
        self.assertIn("cylindrical_panel_segment", examples)
        self.assertIn("conical_panel_segment", examples)

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

    def test_run_forwards_build_kwargs(self):
        doc = object()
        expected = {"ok": True}
        module = types.SimpleNamespace(build=MagicMock(return_value=expected))

        with patch.object(
            registry,
            "get_example_module",
            return_value=module,
        ):
            result = runner.run(
                "dummy",
                run_solver=True,
                doc=doc,
                debug_options={"skip_draper": True},
            )

        module.build.assert_called_once_with(
            doc=doc,
            run_solver=True,
            debug_options={"skip_draper": True},
        )
        self.assertIs(result, expected)

    def test_run_raises_when_build_not_callable(self):
        module = types.SimpleNamespace(build=None)

        with patch.object(registry, "get_example_module", return_value=module):
            with self.assertRaises(AttributeError):
                runner.run("dummy", run_solver=False, doc=None)


class TestFailurePostprocess(unittest.TestCase):
    def test_evaluate_failure_criteria_returns_hotspots(self):
        result_obj = types.SimpleNamespace(
            TypeId="Fem::FemResultMechanical",
            Name="ResultMechanical",
            PropertiesList=["StressXX", "StressYY", "StressXY"],
            StressXX={1: 100.0, 2: 250.0},
            StressYY={1: 10.0, 2: 25.0},
            StressXY={1: 5.0, 2: 12.0},
        )
        analysis = types.SimpleNamespace(Group=[result_obj])

        report = _shell_example_common.evaluate_failure_criteria(analysis)

        self.assertTrue(report["available"])
        self.assertGreater(report["max_failure_index"], 0.0)
        self.assertTrue(report["hotspots"])
        self.assertEqual(report["hotspots"][0]["element_id"], 2)


class TestCompositeExamplesSmoke(unittest.TestCase):
    def test_shell_example_run_solver_invokes_full_fem_job(self):
        doc = MagicMock()
        support = MagicMock()
        fake_job = {"status": "ok"}
        fake_shape = types.SimpleNamespace(Faces=[])
        fake_part = types.SimpleNamespace(makeCylinder=lambda *args, **kwargs: fake_shape)

        with patch.object(
            tubular_shell,
            "import_geometry_modules",
            return_value=(_freecad_mock, fake_part),
        ), patch.object(
            tubular_shell,
            "create_support_feature",
            return_value=support,
        ), patch.object(
            tubular_shell,
            "run_full_shell_job",
            return_value=fake_job,
        ) as fem_run:
            result = tubular_shell.build(doc=doc, run_solver=True)

        fem_run.assert_called_once_with(
            doc,
            support,
            case_id="tubular_shell",
            boundary_conditions=tubular_shell.BOUNDARY_CONDITIONS,
            solve=True,
        )
        self.assertIs(result["fem_job"], fake_job)

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
