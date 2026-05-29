# SPDX-License-Identifier: LGPL-2.1-or-later

"""CS0 harness anchor for fishnet gate policy and stage scopes.

This stage intentionally validates gate policy wiring first, before fishnet
solver implementation changes land.
"""

from __future__ import annotations

import os
import sys
import types
from unittest.mock import MagicMock

# FreeCAD must be mocked before importing freecad.Composites packages.
_freecad_mock = MagicMock()
_freecad_mock.__unit_test__ = []
_freecad_mock.Base = types.SimpleNamespace(
    Precision=types.SimpleNamespace(
        confusion=lambda: 1e-7,
        parametric=lambda _tol: 1e-9,
    )
)
sys.modules.setdefault("FreeCAD", _freecad_mock)
sys.modules.setdefault("CompositesWB", MagicMock())
sys.modules.setdefault("Part", MagicMock())

_boptools = types.ModuleType("BOPTools")
_boptools_split = types.ModuleType("BOPTools.SplitAPI")
_boptools.SplitAPI = _boptools_split
sys.modules.setdefault("BOPTools", _boptools)
sys.modules.setdefault("BOPTools.SplitAPI", _boptools_split)

from freecad.Composites.compositeexamples import registry
from freecad.Composites.compositestests.fishnet_gate_profiles import load_gate_profiles
from freecad.Composites.tools.drape_backend_fishnet import FishnetDrapeBackend


EXPECTED_GATE_CATEGORIES = [
    "support_adherence",
    "coverage",
    "duplicate_collapse",
    "hole_crossing",
    "uv_physical_scale",
]

EXPECTED_CS0_TRIAD = [
    "ud_plate_basic",
    "cylindrical_panel_segment",
    "flat_panel_spline_hole",
]


def test_gate_profile_categories_are_strict_and_complete():
    profiles = load_gate_profiles()
    assert profiles["gate_categories"] == EXPECTED_GATE_CATEGORIES


def test_gate_profile_policies_are_blocking():
    profiles = load_gate_profiles()
    policies = profiles["policies"]

    assert policies["gate_blocking"] is True
    assert policies["flake_zero"] is True
    assert policies["determinism_required"] is True
    assert policies["material_divergence_delta_pct"] == 5.0


def test_cs0_geometry_triad_is_locked():
    profiles = load_gate_profiles()
    assert profiles["stages"]["cs0"]["examples"] == EXPECTED_CS0_TRIAD


def test_stage_examples_exist_in_registry():
    profiles = load_gate_profiles()
    known = set(registry.list_examples())

    for stage_name, stage_cfg in profiles["stages"].items():
        for example_id in stage_cfg["examples"]:
            assert example_id in known, (
                f"Stage {stage_name} references unknown example '{example_id}'"
            )


def test_runner_stage_env_matches_profile():
    profiles = load_gate_profiles()
    stage = os.environ.get("FISHNET_GATE_STAGE", "cs0")
    assert stage in profiles["stages"], f"Unknown FISHNET_GATE_STAGE='{stage}'"

    targets = profiles["stages"][stage]["pytest_targets"]
    assert any(t.endswith("test_drape_backend_fishnet_gates.py") for t in targets)


class _GateShapeStrictCoverage:
    Faces = [object()]
    fishnet_metric_payload = {
        "covered_area_3d": 3.0,
        "support_area_3d": 4.0,
    }

    @staticmethod
    def project_uv_for_point(_point):
        return (0.0, 0.0)


class _GateShapeLegacyCoverage:
    Faces = [object()]
    fishnet_metric_payload = {
        "solved_fraction": 0.75,
    }

    @staticmethod
    def project_uv_for_point(_point):
        return (0.0, 0.0)


class _GateMeshWithNeighbors:
    Topology = ([], [(0, 1, 2)])


def test_gate_coverage_consumes_strict_support_aware_metric_path():
    backend = FishnetDrapeBackend(
        mesh=_GateMeshWithNeighbors(),
        lcs=object(),
        shape=_GateShapeStrictCoverage(),
    )
    diag = backend.diagnostics()

    assert diag["coverage_metric_status"] == "ok"
    assert diag["coverage_ratio_3d"] == 0.75


def test_gate_coverage_rejects_legacy_payload_shim_path():
    backend = FishnetDrapeBackend(
        mesh=_GateMeshWithNeighbors(),
        lcs=object(),
        shape=_GateShapeLegacyCoverage(),
    )
    diag = backend.diagnostics()

    assert diag["coverage_metric_status"] == "invalid_payload"
    assert diag["coverage_ratio_3d"] is None
