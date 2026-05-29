# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2026

"""Double-curvature panel example using a polynomial midsurface."""

from ._shell_example_common import (
    create_composite_feature_stack,
    create_support_feature,
    ensure_document,
    import_geometry_modules,
    largest_face,
    make_demo_laminate,
    make_diagnostics,
    record_diagnostic_event,
    run_full_shell_job,
)

GEOMETRY = {
    # Input polynomial is defined in meters; this example stores geometry in mm.
    "x_min_mm": 0.0,
    "x_max_mm": 500.0,
    "y_min_mm": 0.0,
    "y_max_mm": 500.0,
    "grid_n": 12,
}

BOUNDARY_CONDITIONS = {
    "support": "Constrain panel boundary edges",
    "load": "Apply uniform normal pressure on curved surface",
}


def _z_poly_m(x_m: float, y_m: float) -> float:
    """Double-curvature polynomial in meters (input source units)."""

    return (
        1.004 * x_m
        + 1.089 * y_m
        - 3.667 * x_m**2
        - 4.4 * x_m * y_m
        - 3.75 * y_m**2
        + 3.086 * x_m**3
        + 8.889 * x_m**2 * y_m
        + 4.321 * y_m**3
    )


def _linspace(a: float, b: float, n: int) -> list[float]:
    if n <= 1:
        return [a]
    step = (b - a) / float(n - 1)
    return [a + step * i for i in range(n)]


def _make_double_curvature_surface(FreeCAD, Part):
    xs_mm = _linspace(GEOMETRY["x_min_mm"], GEOMETRY["x_max_mm"], GEOMETRY["grid_n"])
    ys_mm = _linspace(GEOMETRY["y_min_mm"], GEOMETRY["y_max_mm"], GEOMETRY["grid_n"])

    def _z_mm(x_mm: float, y_mm: float) -> float:
        x_m = x_mm / 1000.0
        y_m = y_mm / 1000.0
        return _z_poly_m(x_m, y_m) * 1000.0

    poles = [
        [FreeCAD.Vector(x_mm, y_mm, _z_mm(x_mm, y_mm)) for y_mm in ys_mm]
        for x_mm in xs_mm
    ]

    # Preferred: interpolate a BSpline surface through sampled poles.
    try:
        surf = Part.BSplineSurface()
        surf.interpolate(poles)
        return surf.toShape()
    except Exception:
        # Conservative fallback for limited Part APIs.
        return Part.makePlane(
            GEOMETRY["x_max_mm"] - GEOMETRY["x_min_mm"],
            GEOMETRY["y_max_mm"] - GEOMETRY["y_min_mm"],
        )


def build(doc=None, run_solver=False, debug_options=None):
    diagnostics = make_diagnostics(debug_options)
    record_diagnostic_event(diagnostics, "build.start", run_solver=bool(run_solver))

    opts = diagnostics["options"]
    doc = ensure_document(doc, "Composites_Double_Curvature_Panel")
    laminate = make_demo_laminate()

    support = None
    FreeCAD, Part = import_geometry_modules()
    record_diagnostic_event(
        diagnostics,
        "build.geometry_modules",
        freecad=FreeCAD is not None,
        part=Part is not None,
    )

    if doc is not None and FreeCAD is not None and Part is not None:
        shell_like = _make_double_curvature_surface(FreeCAD, Part)
        midsurface = largest_face(shell_like)
        support = create_support_feature(doc, "DoubleCurvaturePanelSupport", midsurface)

    record_diagnostic_event(
        diagnostics,
        "build.support.done",
        has_support=support is not None,
    )

    feature_stack = create_composite_feature_stack(
        doc,
        support,
        name_prefix="DoubleCurvature",
        skip_draper=bool(opts.get("skip_draper", False)),
        skip_recompute=bool(opts.get("skip_recompute", False)),
        skip_view_providers=bool(opts.get("skip_view_providers", False)),
        diagnostics=diagnostics,
    )

    fem_job = None
    if run_solver:
        record_diagnostic_event(diagnostics, "build.fem.begin")
        fem_job = run_full_shell_job(
            doc,
            support,
            case_id="double_curvature_panel",
            boundary_conditions=BOUNDARY_CONDITIONS,
            solve=not bool(opts.get("mesh_only", False)),
        )
        record_diagnostic_event(diagnostics, "build.fem.done")

    record_diagnostic_event(diagnostics, "build.done")

    return {
        "doc": doc,
        "laminate": laminate,
        "support": support,
        "geometry": GEOMETRY,
        "analysis_setup": BOUNDARY_CONDITIONS,
        "feature_stack": feature_stack,
        "fem_job": fem_job,
        "diagnostics": diagnostics if diagnostics.get("enabled", False) else None,
    }
