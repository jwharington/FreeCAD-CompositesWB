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
    "x_min": 0.0,
    "x_max": 0.5,
    "y_min": 0.0,
    "y_max": 0.5,
    "grid_n": 12,
}

BOUNDARY_CONDITIONS = {
    "support": "Constrain panel boundary edges",
    "load": "Apply uniform normal pressure on curved surface",
}


def _z_poly(x: float, y: float) -> float:
    return (
        1.004 * x
        + 1.089 * y
        - 3.667 * x**2
        - 4.4 * x * y
        - 3.75 * y**2
        + 3.086 * x**3
        + 8.889 * x**2 * y
        + 4.321 * y**3
    )


def _linspace(a: float, b: float, n: int) -> list[float]:
    if n <= 1:
        return [a]
    step = (b - a) / float(n - 1)
    return [a + step * i for i in range(n)]


def _make_double_curvature_surface(FreeCAD, Part):
    xs = _linspace(GEOMETRY["x_min"], GEOMETRY["x_max"], GEOMETRY["grid_n"])
    ys = _linspace(GEOMETRY["y_min"], GEOMETRY["y_max"], GEOMETRY["grid_n"])

    poles = [
        [FreeCAD.Vector(x, y, _z_poly(x, y)) for y in ys]
        for x in xs
    ]

    # Preferred: interpolate a BSpline surface through sampled poles.
    try:
        surf = Part.BSplineSurface()
        surf.interpolate(poles)
        return surf.toShape()
    except Exception:
        # Conservative fallback for limited Part APIs.
        return Part.makePlane(
            GEOMETRY["x_max"] - GEOMETRY["x_min"],
            GEOMETRY["y_max"] - GEOMETRY["y_min"],
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
