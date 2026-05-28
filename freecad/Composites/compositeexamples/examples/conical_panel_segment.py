# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Conical shell panel example (open frustum arc midsurface)."""

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
    "radius_small_mm": 260.0,
    "radius_large_mm": 360.0,
    "length_mm": 900.0,
    "arc_deg": 60.0,
}

BOUNDARY_CONDITIONS = {
    "support": "Constrain both straight longitudinal edges",
    "load": "Apply uniform external pressure normal to the conical midsurface",
}


def build(doc=None, run_solver=False, debug_options=None):
    diagnostics = make_diagnostics(debug_options)
    record_diagnostic_event(diagnostics, "build.start", run_solver=bool(run_solver))

    opts = diagnostics["options"]
    doc = ensure_document(doc, "Composites_Conical_Panel")
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
        axis_origin = FreeCAD.Vector(0.0, 0.0, 0.0)
        axis_dir = FreeCAD.Vector(0.0, 0.0, 1.0)
        shell_like = Part.makeCone(
            GEOMETRY["radius_small_mm"],
            GEOMETRY["radius_large_mm"],
            GEOMETRY["length_mm"],
            axis_origin,
            axis_dir,
            GEOMETRY["arc_deg"],
        )
        midsurface = largest_face(shell_like)
        support = create_support_feature(doc, "ConicalPanelSupport", midsurface)
    record_diagnostic_event(
        diagnostics,
        "build.support.done",
        has_support=support is not None,
    )

    feature_stack = create_composite_feature_stack(
        doc,
        support,
        name_prefix="ConicalPanel",
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
            case_id="conical_panel_segment",
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
