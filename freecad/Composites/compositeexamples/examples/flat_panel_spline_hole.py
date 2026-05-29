# SPDX-License-Identifier: LGPL-2.1-or-later

"""Flat irregular panel with a central hole (shell-style example)."""

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
    "length_mm": 900.0,
    "width_mm": 700.0,
    "hole_radius_mm": 90.0,
}

BOUNDARY_CONDITIONS = {
    "support": "Clamp one short edge of panel",
    "load": "Apply uniform normal pressure over panel surface",
}


def _make_panel_with_hole(FreeCAD, Part):
    """Build a best-effort irregular flat panel with a central hole."""

    try:
        # Mildly irregular outer boundary.
        pts = [
            FreeCAD.Vector(-450.0, -320.0, 0.0),
            FreeCAD.Vector(460.0, -300.0, 0.0),
            FreeCAD.Vector(430.0, 310.0, 0.0),
            FreeCAD.Vector(-420.0, 330.0, 0.0),
            FreeCAD.Vector(-450.0, -320.0, 0.0),
        ]
        outer = Part.Wire(Part.makePolygon(pts))

        circle = Part.Circle(
            FreeCAD.Vector(0.0, 0.0, 0.0),
            FreeCAD.Vector(0.0, 0.0, 1.0),
            GEOMETRY["hole_radius_mm"],
        )
        inner = Part.Wire(circle.toShape())

        # Part.Face can accept outer wire and inner-wire list for hole.
        return Part.Face(outer, [inner])
    except Exception:
        # Conservative fallback used only for non-standard Part APIs in tests.
        return Part.makePlane(GEOMETRY["length_mm"], GEOMETRY["width_mm"])


def build(doc=None, run_solver=False, debug_options=None):
    diagnostics = make_diagnostics(debug_options)
    record_diagnostic_event(diagnostics, "build.start", run_solver=bool(run_solver))

    opts = diagnostics["options"]
    doc = ensure_document(doc, "Composites_FlatPanel_Spline_Hole")
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
        panel_shape = _make_panel_with_hole(FreeCAD, Part)
        midsurface = largest_face(panel_shape)
        support = create_support_feature(doc, "FlatPanelSplineHoleSupport", midsurface)

    record_diagnostic_event(
        diagnostics,
        "build.support.done",
        has_support=support is not None,
    )

    feature_stack = create_composite_feature_stack(
        doc,
        support,
        name_prefix="FlatSplineHole",
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
            case_id="flat_panel_spline_hole",
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
