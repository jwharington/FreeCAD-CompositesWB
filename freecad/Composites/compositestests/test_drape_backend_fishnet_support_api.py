# SPDX-License-Identifier: LGPL-2.1-or-later

"""Focused CS1 tests for fishnet support/projection typed result contract."""

from __future__ import annotations

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

from freecad.Composites.tools.drape_backend_fishnet import (  # noqa: E402
    FishnetDrapeBackend,
    FishnetSupportProjectionResult,
)


class _ShapeNoFaces:
    pass


class _ShapeProjectionFailure:
    Faces = [object()]

    @staticmethod
    def project_uv_for_point(_point):
        raise ValueError("projection unavailable")


class _ShapeProjectionUnexpectedFailure:
    Faces = [object()]

    @staticmethod
    def project_uv_for_point(_point):
        raise RuntimeError("unexpected failure")


class _ShapeProjectionOk:
    Faces = [object()]

    @staticmethod
    def project_uv_for_point(_point):
        return (0.0, 0.0)


class _ShapeProjectionOkWithStrictMetrics(_ShapeProjectionOk):
    fishnet_metric_payload = {
        "covered_area_3d": 8.0,
        "support_area_3d": 10.0,
        "duplicate_point_count": 2,
        "total_point_count": 10,
        "hole_crossing_cell_count": 0,
        "uv_edge_scale_consistency_ratio": 0.95,
        "uv_edge_scale_error_p95": 0.07,
        "linear_strain_min": -0.00008,
        "linear_strain_max": 0.00009,
        "shear_angle_abs_max_deg": 8.5,
        "strain_heatmap_coordinates_3d": [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ],
        "strain_heatmap_coordinates_uv": [
            [0.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 1.0],
        ],
        "strain_heatmap_linear_values": [-0.00008, -0.00001, 0.0, 0.00009],
        "strain_heatmap_shear_values_deg": [1.0, 2.0, 4.0, 8.5],
    }


class _ShapeProjectionOkWithLegacyMetrics(_ShapeProjectionOk):
    fishnet_metric_payload = {
        "solved_fraction": 0.9,
    }


class _MeshWithNeighbors:
    Topology = ([], [(0, 1, 2)])


class _MeshWithoutNeighbors:
    Topology = ([], [])


class _Point:
    def __init__(self, x: float, y: float, z: float):
        self.x = x
        self.y = y
        self.z = z


class _RuntimeSurface:
    @staticmethod
    def parameter(point):
        if not hasattr(point, "x") or not hasattr(point, "y"):
            raise TypeError("expects point-like object")
        return (float(point.x), float(point.y))


class _RuntimeFace:
    Surface = _RuntimeSurface()
    CenterOfMass = _Point(10.0, 20.0, 0.0)
    Area = 100.0


class _RuntimeShapeNoProjector:
    Faces = [_RuntimeFace()]


class _RuntimeShapeConstantProjector:
    Faces = [_RuntimeFace()]

    @staticmethod
    def project_uv_for_point(_point):
        return (123.0, 456.0)


class _RuntimeShapeConstantProjectorNoSurface:
    Faces = [object()]

    @staticmethod
    def project_uv_for_point(_point):
        return (123.0, 456.0)


class _MeshWithNeighborsAndPoints:
    Topology = ([], [(0, 1, 2)])
    Points = [
        _Point(0.0, 0.0, 0.0),
        _Point(1.0, 0.0, 0.0),
        _Point(0.0, 1.0, 0.0),
    ]


class _SparseMeshWithNeighbors:
    Topology = ([], [(0, 1, 2)])
    Points = [
        _Point(0.0, 0.0, 0.0),
        _Point(1.0, 0.0, 0.0),
        _Point(0.0, 1.0, 0.0),
        _Point(1.0, 1.0, 0.0),
    ]


class _OuterEdge:
    @staticmethod
    def discretize(_n):
        return [
            _Point(0.0, 0.0, 0.0),
            _Point(1.0, 0.0, 0.0),
            _Point(1.0, 1.0, 0.0),
            _Point(0.0, 1.0, 0.0),
        ]


class _InnerEdge:
    @staticmethod
    def discretize(_n):
        return [
            _Point(0.35, 0.35, 0.0),
            _Point(0.65, 0.35, 0.0),
            _Point(0.65, 0.65, 0.0),
            _Point(0.35, 0.65, 0.0),
        ]


class _OuterWire:
    Edges = [_OuterEdge()]


class _InnerWire:
    Edges = [_InnerEdge()]


class _RuntimeFaceWithWire(_RuntimeFace):
    Wires = [_OuterWire(), _InnerWire()]


class _RuntimeSparseShape(_RuntimeShapeNoProjector):
    Faces = [_RuntimeFaceWithWire()]

    @staticmethod
    def tessellate(_deflection):
        return (
            [
                _Point(0.0, 0.0, 0.0),
                _Point(1.0, 0.0, 0.0),
                _Point(1.0, 1.0, 0.0),
                _Point(0.0, 1.0, 0.0),
                _Point(0.5, 0.5, 0.0),
            ],
            [],
        )

    @staticmethod
    def isInside(point, *_args):
        x = float(getattr(point, "x", 0.0))
        y = float(getattr(point, "y", 0.0))
        dx = x - 0.5
        dy = y - 0.5
        hole_r2 = 0.2 * 0.2
        return (dx * dx + dy * dy) >= hole_r2


class _RuntimeSparseShapeNoInside(_RuntimeShapeNoProjector):
    Faces = [_RuntimeFaceWithWire()]

    @staticmethod
    def tessellate(_deflection):
        return (
            [
                _Point(0.0, 0.0, 0.0),
                _Point(1.0, 0.0, 0.0),
                _Point(1.0, 1.0, 0.0),
                _Point(0.0, 1.0, 0.0),
                _Point(0.5, 0.5, 0.0),
            ],
            [],
        )


def test_result_dataclass_ok_and_failure_helpers():
    ok = FishnetSupportProjectionResult.ok(uv=(1.0, 2.0))
    fail = FishnetSupportProjectionResult.failed("invalid_support")

    assert ok.status == "ok"
    assert ok.failure_reason is None
    assert ok.uv == (1.0, 2.0)

    assert fail.status == "invalid"
    assert fail.failure_reason == "invalid_support"
    assert fail.uv is None


def test_backend_maps_invalid_support_failure_reason():
    backend = FishnetDrapeBackend(mesh=object(), lcs=object(), shape=_ShapeNoFaces())
    diag = backend.diagnostics()

    assert backend.is_valid() is False
    assert diag["status"] == "invalid"
    assert diag["failure_reason"] == "invalid_support"


def test_backend_maps_projection_failed_failure_reason():
    backend = FishnetDrapeBackend(
        mesh=object(),
        lcs=object(),
        shape=_ShapeProjectionFailure(),
    )
    diag = backend.diagnostics()

    assert backend.is_valid() is False
    assert diag["status"] == "invalid"
    assert diag["failure_reason"] == "projection_failed"


def test_backend_maps_solver_unsolved_after_support_and_projection_pass():
    backend = FishnetDrapeBackend(
        mesh=_MeshWithNeighbors(),
        lcs=object(),
        shape=_ShapeProjectionOk(),
    )
    diag = backend.diagnostics()

    assert backend.is_valid() is False
    assert diag["status"] == "invalid"
    assert diag["failure_reason"] == "solver_unsolved"
    assert diag["solve_status"] == "failed_not_implemented"


def test_backend_no_neighbor_path_fails_without_rescue_branch():
    backend = FishnetDrapeBackend(
        mesh=_MeshWithoutNeighbors(),
        lcs=object(),
        shape=_ShapeProjectionOk(),
    )
    diag = backend.diagnostics()

    assert backend.is_valid() is False
    assert diag["status"] == "invalid"
    assert diag["failure_reason"] == "solver_unsolved"
    assert diag["solve_status"] == "failed_no_neighbors"
    assert diag["solved_node_count"] == 0


def test_backend_unsolved_output_path_has_no_synthetic_uv_or_boundaries():
    backend = FishnetDrapeBackend(
        mesh=_MeshWithNeighbors(),
        lcs=object(),
        shape=_ShapeProjectionOk(),
    )

    diag = backend.diagnostics()
    assert diag["output_ready"] is False

    assert backend.get_tex_coords() is None
    assert backend.get_tex_coord_at_point((0.0, 0.0, 0.0)) is None
    assert backend.get_boundaries() is None


def test_backend_diagnostics_compute_strict_coverage_metric_when_payload_present():
    backend = FishnetDrapeBackend(
        mesh=_MeshWithNeighbors(),
        lcs=object(),
        shape=_ShapeProjectionOkWithStrictMetrics(),
    )

    diag = backend.diagnostics()
    assert diag["coverage_metric_status"] == "ok"
    assert diag["coverage_ratio_3d"] == 0.8
    assert diag["coverage_metric_error"] is None

    assert diag["duplicate_metric_status"] == "ok"
    assert diag["duplicate_point_ratio"] == 0.2
    assert diag["unique_point_ratio"] == 0.8

    assert diag["hole_metric_status"] == "ok"
    assert diag["hole_crossing_cell_count"] == 0

    assert diag["uv_metric_status"] == "ok"
    assert diag["uv_edge_scale_consistency_ratio"] == 0.95
    assert diag["uv_edge_scale_error_p95"] == 0.07

    assert diag["linear_metric_status"] == "ok"
    assert diag["linear_strain_min"] == -0.00008
    assert diag["linear_strain_max"] == 0.00009

    assert diag["shear_metric_status"] == "ok"
    assert diag["shear_angle_abs_max_deg"] == 8.5

    assert diag["strain_heatmap_3d_status"] == "ok"
    assert len(diag["strain_heatmap_3d"]["coordinates"]) == 4
    assert diag["strain_heatmap_flat_status"] == "ok"
    assert len(diag["strain_heatmap_flat"]["coordinates_uv"]) == 4

    assert diag["linear_strain_warning_exceeded"] is False
    assert diag["shear_strain_warning_exceeded"] is False


def test_backend_diagnostics_reject_legacy_metric_payload():
    backend = FishnetDrapeBackend(
        mesh=_MeshWithNeighbors(),
        lcs=object(),
        shape=_ShapeProjectionOkWithLegacyMetrics(),
    )

    diag = backend.diagnostics()
    assert diag["coverage_metric_status"] == "invalid_payload"
    assert diag["coverage_ratio_3d"] is None
    assert "legacy solved-fraction payload" in str(diag["coverage_metric_error"])

    assert diag["duplicate_metric_status"] == "invalid_payload"
    assert diag["hole_metric_status"] == "invalid_payload"
    assert diag["uv_metric_status"] == "invalid_payload"
    assert diag["linear_metric_status"] == "invalid_payload"
    assert diag["shear_metric_status"] == "invalid_payload"
    assert diag["strain_heatmap_3d_status"] == "invalid_payload"
    assert diag["strain_heatmap_flat_status"] == "invalid_payload"


def test_runtime_metric_payload_derives_non_degenerate_uv_from_mesh_points():
    backend = FishnetDrapeBackend(
        mesh=_MeshWithNeighborsAndPoints(),
        lcs=object(),
        shape=_RuntimeShapeNoProjector(),
        derive_runtime_metric_payload=True,
    )

    diag = backend.diagnostics()
    assert diag["strain_heatmap_flat_status"] == "ok"
    coords_uv = diag["strain_heatmap_flat"]["coordinates_uv"]
    assert len(coords_uv) == 3
    assert len({tuple(row) for row in coords_uv}) == 3


def test_runtime_metric_payload_prefers_surface_projection_over_constant_projector():
    backend = FishnetDrapeBackend(
        mesh=_MeshWithNeighborsAndPoints(),
        lcs=object(),
        shape=_RuntimeShapeConstantProjector(),
        derive_runtime_metric_payload=True,
    )

    diag = backend.diagnostics()
    coords_uv = diag["strain_heatmap_flat"]["coordinates_uv"]
    assert len({tuple(row) for row in coords_uv}) == 3
    assert coords_uv[0] != [123.0, 456.0]


def test_runtime_metric_payload_falls_back_to_xyz_uv_when_projection_is_degenerate():
    backend = FishnetDrapeBackend(
        mesh=_MeshWithNeighborsAndPoints(),
        lcs=object(),
        shape=_RuntimeShapeConstantProjectorNoSurface(),
        derive_runtime_metric_payload=True,
    )

    diag = backend.diagnostics()
    coords_uv = diag["strain_heatmap_flat"]["coordinates_uv"]
    assert len({tuple(row) for row in coords_uv}) == 3


def test_runtime_metric_payload_augments_sparse_mesh_from_shape_sampling():
    backend = FishnetDrapeBackend(
        mesh=_SparseMeshWithNeighbors(),
        lcs=object(),
        shape=_RuntimeSparseShape(),
        derive_runtime_metric_payload=True,
    )

    diag = backend.diagnostics()
    coords_3d = diag["strain_heatmap_3d"]["coordinates"]
    coords_uv = diag["strain_heatmap_flat"]["coordinates_uv"]
    assert len(coords_3d) >= 4
    assert len(coords_uv) == len(coords_3d)

    # Hole exclusion: center sample from sparse mesh/tessellation should be filtered.
    assert [0.5, 0.5, 0.0] not in coords_3d


def test_runtime_metric_payload_filters_hole_without_isinside_via_wire_loops():
    backend = FishnetDrapeBackend(
        mesh=_SparseMeshWithNeighbors(),
        lcs=object(),
        shape=_RuntimeSparseShapeNoInside(),
        derive_runtime_metric_payload=True,
    )

    diag = backend.diagnostics()
    coords_3d = diag["strain_heatmap_3d"]["coordinates"]
    assert [0.5, 0.5, 0.0] not in coords_3d


def test_unexpected_projection_exception_is_not_masked():
    try:
        FishnetDrapeBackend(
            mesh=object(),
            lcs=object(),
            shape=_ShapeProjectionUnexpectedFailure(),
        )
    except RuntimeError as exc:
        assert "unexpected failure" in str(exc)
    else:
        raise AssertionError("RuntimeError should bubble for unexpected exceptions")
