# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright 2025 John Wharington jwharington@gmail.com

"""Shared helpers for shell-geometry composite examples."""

import sys
import time
import types

from ...objects import (
    CompositeLaminate,
    FibreCompositeLamina,
    SimpleFabric,
    SymmetryType,
    WeaveType,
)


def _carbon_material():
    return {
        "Name": "Carbon",
        "Density": "1750.0 kg/m^3",
        "PoissonRatioXY": "0.27",
        "PoissonRatioXZ": "0.27",
        "PoissonRatioYZ": "0.45",
        "ShearModulusXY": "5000 MPa",
        "ShearModulusXZ": "5000 MPa",
        "ShearModulusYZ": "3500 MPa",
        "YoungsModulusX": "135 GPa",
        "YoungsModulusY": "9.5 GPa",
        "YoungsModulusZ": "9.5 GPa",
    }


def _resin_material():
    return {
        "Name": "Epoxy",
        "Density": "1180.0 kg/m^3",
        "YoungsModulus": "3.300 GPa",
        "PoissonRatio": "0.35",
    }


def make_demo_laminate():
    """Return a lightweight quasi-isotropic laminate stack."""

    def _make_ply(orientation):
        ply = SimpleFabric(
            material_fibre=_carbon_material(),
            orientation=orientation,
            weave=WeaveType.UD,
        )
        ply.thickness = 0.2
        return FibreCompositeLamina(fibre=ply)

    return CompositeLaminate(
        symmetry=SymmetryType.Assymmetric,
        layers=[
            _make_ply(0),
            _make_ply(45),
            _make_ply(-45),
            _make_ply(90),
        ],
        volume_fraction_fibre=0.55,
        material_matrix=_resin_material(),
    )


def ensure_document(doc, name):
    if doc is not None:
        return doc

    try:
        import FreeCAD
    except ImportError:
        return None

    return FreeCAD.newDocument(name)


def import_geometry_modules():
    """Try importing FreeCAD geometry modules, returning ``(FreeCAD, Part)``."""

    try:
        import FreeCAD  # noqa: F401
        import Part
    except ImportError:
        return None, None

    return FreeCAD, Part


def largest_face(shape):
    """Return the largest-area face for a shell-like generated shape."""

    faces = getattr(shape, "Faces", None)
    if not faces:
        return shape
    return max(faces, key=lambda face: getattr(face, "Area", 0.0))


def create_support_feature(doc, name, shape):
    if doc is None:
        return None
    support = doc.addObject("Part::Feature", name)
    support.Shape = shape
    return support


def _ensure_freecadgui_stub():
    try:
        import FreeCADGui  # noqa: F401
        return
    except Exception:
        pass

    mod = types.ModuleType("FreeCADGui")
    mod.addCommand = lambda *args, **kwargs: None
    mod.Selection = types.SimpleNamespace(
        addObserver=lambda *args, **kwargs: None,
        removeObserver=lambda *args, **kwargs: None,
    )
    mod.Control = types.SimpleNamespace(
        showDialog=lambda *args, **kwargs: None,
        closeDialog=lambda *args, **kwargs: None,
    )
    mod.getDocument = lambda *args, **kwargs: types.SimpleNamespace(
        getInEdit=lambda: False,
        setEdit=lambda *a, **k: None,
    )
    sys.modules["FreeCADGui"] = mod


def _ensure_taskpanel_stub(module_name):
    if module_name in sys.modules:
        return
    task_mod = types.ModuleType(module_name)
    task_mod._TaskPanel = object
    sys.modules[module_name] = task_mod


def _prepare_feature_import_environment():
    _ensure_freecadgui_stub()
    _ensure_taskpanel_stub(
        "freecad.Composites.taskpanels.task_fibre_composite_lamina",
    )
    _ensure_taskpanel_stub(
        "freecad.Composites.taskpanels.task_composite_laminate",
    )


def _to_length_mm(freecad_mod, value_mm):
    if hasattr(freecad_mod, "Units"):
        return freecad_mod.Units.Quantity(f"{value_mm} mm")
    return value_mm


def _configure_lcs_for_shell(freecad_mod, lcs_obj, support):
    if lcs_obj is None or support is None:
        return
    if not hasattr(lcs_obj, "Placement"):
        return

    shape = getattr(support, "Shape", None)
    bbox = getattr(shape, "BoundBox", None)
    if bbox is None:
        return

    base = freecad_mod.Vector(
        getattr(bbox, "XMax", 0.0),
        0.0,
        0.5 * (getattr(bbox, "ZMin", 0.0) + getattr(bbox, "ZMax", 0.0)),
    )

    # Project the LCS origin onto the support shell so the rosette is visibly
    # on-surface (important for conical segments).
    try:
        import Part

        vert = Part.Vertex(base.x, base.y, base.z)
        _, points, _ = shape.distToShape(vert)
        if points and points[0]:
            base = points[0][0]
    except Exception:
        pass

    # Keep local XY approximately tangent-friendly for draping.
    rot = freecad_mod.Rotation(freecad_mod.Vector(0, 1, 0), -90)
    lcs_obj.Placement = freecad_mod.Placement(base, rot)


def _hide_support_shape(support):
    """Hide support geometry once the CompositeShell exists."""

    try:
        if hasattr(support, "Visibility"):
            support.Visibility = False
    except Exception:
        pass

    try:
        support_vo = getattr(support, "ViewObject", None)
        if support_vo is not None:
            support_vo.Visibility = False
    except Exception:
        pass


def _configure_shell_visuals(shell_obj, support):
    """Make shader-based fibre orientation view obvious by default."""

    # Hide raw support surface to avoid z-fighting over the Grid shader.
    _hide_support_shape(support)

    shell_vo = getattr(shell_obj, "ViewObject", None)
    if shell_vo is None:
        return

    try:
        shell_vo.Visibility = True
        if "Grid" in list(getattr(shell_vo, "listDisplayModes", lambda: [])()):
            shell_vo.DisplayMode = "Grid"
        if hasattr(shell_vo, "ShowRosette"):
            shell_vo.ShowRosette = True

        proxy = getattr(shell_vo, "Proxy", None)
        if proxy and hasattr(proxy, "reload_shader"):
            proxy.reload_shader()
    except Exception:
        pass


def make_diagnostics(debug_options=None):
    opts = dict(debug_options or {})
    return {
        "enabled": bool(opts.get("diagnostics", False) or opts),
        "options": opts,
        "events": [],
        "_t0": time.monotonic(),
    }


def record_diagnostic_event(diagnostics, stage, **data):
    if not diagnostics or not diagnostics.get("enabled", False):
        return
    t0 = diagnostics.get("_t0", time.monotonic())
    event = {
        "stage": stage,
        "elapsed_s": round(time.monotonic() - t0, 6),
        **data,
    }
    diagnostics["events"].append(event)

    log_path = diagnostics.get("options", {}).get("log_path")
    if log_path:
        try:
            import json

            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, sort_keys=True) + "\n")
        except Exception:
            pass


def create_composite_feature_stack(
    doc,
    support,
    *,
    name_prefix="Example",
    skip_draper=False,
    skip_recompute=False,
    skip_view_providers=False,
    diagnostics=None,
):
    """Create FeaturePython composite objects for property-panel visibility.

    This is GUI-aware: in headless mode it still creates lamina/laminate
    FeaturePython objects, while GUI-only shell/view-provider wiring is best-effort.
    """

    record_diagnostic_event(
        diagnostics,
        "feature_stack.start",
        has_doc=doc is not None,
        has_support=support is not None,
        skip_draper=bool(skip_draper),
        skip_recompute=bool(skip_recompute),
        skip_view_providers=bool(skip_view_providers),
    )

    if doc is None or support is None or not hasattr(doc, "addObject"):
        return {
            "created": False,
            "reason": "missing document/support",
            "laminae": [],
            "laminate": None,
            "shell": None,
        }

    try:
        import FreeCAD
    except Exception:
        return {
            "created": False,
            "reason": "FreeCAD import failed",
            "laminae": [],
            "laminate": None,
            "shell": None,
        }

    gui_up = bool(getattr(FreeCAD, "GuiUp", False))
    attach_view_providers = gui_up and not skip_view_providers

    try:
        _prepare_feature_import_environment()
        from ...features.CompositeLaminate import (  # noqa: WPS433
            CompositeLaminateFP,
            ViewProviderCompositeLaminate,
        )
        from ...features.FibreCompositeLamina import (  # noqa: WPS433
            FibreCompositeLaminaFP,
            ViewProviderFibreCompositeLamina,
        )
    except Exception as exc:
        return {
            "created": False,
            "reason": f"feature import failed: {exc}",
            "laminae": [],
            "laminate": None,
            "shell": None,
        }

    laminae = []
    record_diagnostic_event(diagnostics, "feature_stack.laminae.begin")
    for idx, angle in enumerate((0.0, 45.0, -45.0, 90.0), start=1):
        lam_obj = doc.addObject(
            "App::FeaturePython",
            f"{name_prefix}Lamina{idx:02d}",
        )
        FibreCompositeLaminaFP(lam_obj)
        if attach_view_providers and getattr(lam_obj, "ViewObject", None):
            ViewProviderFibreCompositeLamina(lam_obj.ViewObject)
        lam_obj.FibreMaterial = _carbon_material()
        lam_obj.FibreVolumeFraction = 55
        lam_obj.Thickness = _to_length_mm(FreeCAD, 0.2)
        lam_obj.Angle = angle
        lam_obj.WeaveType = WeaveType.UD.name
        laminae.append(lam_obj)

    record_diagnostic_event(
        diagnostics,
        "feature_stack.laminae.done",
        count=len(laminae),
    )

    lam_name = f"{name_prefix}Laminate"
    laminate_obj = doc.addObject("App::FeaturePython", lam_name)
    CompositeLaminateFP(laminate_obj, laminae=laminae)
    if attach_view_providers and getattr(laminate_obj, "ViewObject", None):
        ViewProviderCompositeLaminate(laminate_obj.ViewObject)
    laminate_obj.ResinMaterial = _resin_material()
    laminate_obj.FibreVolumeFraction = 55
    laminate_obj.Symmetry = SymmetryType.Assymmetric.name
    record_diagnostic_event(diagnostics, "feature_stack.laminate.done")

    lcs_obj = None
    try:
        lcs_obj = doc.addObject("Part::LocalCoordinateSystem", f"{name_prefix}LCS")
        _configure_lcs_for_shell(FreeCAD, lcs_obj, support)
    except Exception:
        lcs_obj = None
    record_diagnostic_event(
        diagnostics,
        "feature_stack.lcs.done",
        has_lcs=lcs_obj is not None,
    )

    shell_obj = None
    shell_error = None
    if gui_up:
        try:
            record_diagnostic_event(diagnostics, "feature_stack.shell.import.begin")
            from ...features.CompositeShell import (  # noqa: WPS433
                CompositeShellFP,
                ViewProviderCompositeShell,
            )
            record_diagnostic_event(diagnostics, "feature_stack.shell.import.done")

            record_diagnostic_event(diagnostics, "feature_stack.shell.add_object.begin")
            shell_obj = doc.addObject("Part::FeaturePython", f"{name_prefix}Shell")
            record_diagnostic_event(diagnostics, "feature_stack.shell.add_object.done")

            record_diagnostic_event(diagnostics, "feature_stack.shell.fp_ctor.begin")
            CompositeShellFP(
                shell_obj,
                support=support,
                laminate=laminate_obj,
                lcs=lcs_obj,
            )
            record_diagnostic_event(diagnostics, "feature_stack.shell.fp_ctor.done")

            # Configure drape behavior. In skip_recompute mode, avoid writing
            # properties that trigger fp.recompute() through onChanged.
            proxy = getattr(shell_obj, "Proxy", None)
            if proxy is not None:
                setattr(proxy, "_force_skip_draper", bool(skip_draper))

            if hasattr(shell_obj, "SkipDraper") and not skip_recompute:
                shell_obj.SkipDraper = bool(skip_draper)

            # Finer drape mesh for examples so fibre-path preview is clearer.
            if not skip_recompute:
                shell_obj.MaxLength = 0.1

            if attach_view_providers and getattr(shell_obj, "ViewObject", None):
                record_diagnostic_event(
                    diagnostics,
                    "feature_stack.shell.view_provider.begin",
                )
                ViewProviderCompositeShell(shell_obj.ViewObject)
                record_diagnostic_event(
                    diagnostics,
                    "feature_stack.shell.view_provider.done",
                )
        except Exception as exc:
            shell_error = str(exc)

    record_diagnostic_event(
        diagnostics,
        "feature_stack.shell.done",
        has_shell=shell_obj is not None,
        shell_error=shell_error,
    )

    if hasattr(doc, "recompute") and not skip_recompute:
        record_diagnostic_event(diagnostics, "feature_stack.recompute.begin")
        doc.recompute()
        record_diagnostic_event(diagnostics, "feature_stack.recompute.done")

    if shell_obj is not None:
        _hide_support_shape(support)

    if shell_obj is not None and attach_view_providers:
        _configure_shell_visuals(shell_obj, support)

    record_diagnostic_event(diagnostics, "feature_stack.done")

    return {
        "created": True,
        "reason": None,
        "gui_up": gui_up,
        "laminae": laminae,
        "laminate": laminate_obj,
        "lcs": lcs_obj,
        "shell": shell_obj,
        "shell_error": shell_error,
    }


def _try_make(objects_fem, factory_names, doc, name):
    for factory_name in factory_names:
        factory = getattr(objects_fem, factory_name, None)
        if not callable(factory):
            continue

        # FreeCAD factory signatures vary by version/build.
        for args in ((doc, name), (doc,), ()):  # pragma: no branch
            try:
                return factory(*args)
            except TypeError:
                continue
            except Exception:
                # Some builds reject explicit names when an object already
                # exists; keep trying alternate signatures/factories.
                continue
    return None


def _edge_metrics(shape):
    rows = []
    for idx, edge in enumerate(getattr(shape, "Edges", []), start=1):
        points = [vertex.Point for vertex in edge.Vertexes]
        zs = [p.z for p in points] if points else [0.0]
        rs = [((p.x**2 + p.y**2) ** 0.5) for p in points] if points else [0.0]
        rows.append(
            {
                "name": f"Edge{idx}",
                "z_avg": sum(zs) / len(zs),
                "z_span": max(zs) - min(zs),
                "r_avg": sum(rs) / len(rs),
            }
        )
    return rows


def _pick_edge_by(metric_rows, key, pick_max):
    if not metric_rows:
        return None
    row = max(metric_rows, key=lambda r: r[key]) if pick_max else min(
        metric_rows,
        key=lambda r: r[key],
    )
    return row["name"]


def _pick_longitudinal_edges(metric_rows):
    rows = sorted(metric_rows, key=lambda r: r["z_span"], reverse=True)
    return [r["name"] for r in rows[:2]]


def _add_analysis_member(analysis, obj):
    if analysis is None or obj is None:
        return
    add_object = getattr(analysis, "addObject", None)
    if callable(add_object):
        add_object(obj)


def _set_constraint_refs(constraint, refs):
    if constraint is None:
        return
    if hasattr(constraint, "References"):
        constraint.References = refs


def _add_shell_section_and_material(doc, analysis, support, tag):
    import ObjectsFem

    thickness_obj = None
    make_elem_2d = getattr(ObjectsFem, "makeElementGeometry2D", None)
    if callable(make_elem_2d):
        try:
            thickness_obj = make_elem_2d(doc, 0.8, f"{tag}_ShellThickness")
        except TypeError:
            try:
                thickness_obj = make_elem_2d(doc, 0.8)
            except TypeError:
                thickness_obj = make_elem_2d(doc)

    material_obj = _try_make(
        ObjectsFem,
        ["makeMaterialSolid"],
        doc,
        f"{tag}_Material",
    )

    if material_obj is not None and hasattr(material_obj, "Material"):
        mat = dict(getattr(material_obj, "Material", {}) or {})
        mat.setdefault("Name", "CompositeEquivalent")
        mat.setdefault("YoungsModulus", "70000 MPa")
        mat.setdefault("PoissonRatio", "0.3")
        mat.setdefault("Density", "1600 kg/m^3")
        material_obj.Material = mat

    if material_obj is not None:
        _set_constraint_refs(material_obj, [(support, "Face1")])

    _add_analysis_member(analysis, thickness_obj)
    _add_analysis_member(analysis, material_obj)

    return thickness_obj, material_obj


def _create_fem_base(doc, tag):
    try:
        import ObjectsFem
    except ImportError as exc:
        raise RuntimeError("ObjectsFem is required for run_solver=True") from exc

    analysis = _try_make(ObjectsFem, ["makeAnalysis"], doc, f"{tag}_Analysis")
    solver = _try_make(
        ObjectsFem,
        [
            "makeSolverCalculiXCcxTools",
            "makeSolverCalculixCcxTools",
            "makeSolverCalculiXCcx",
            "makeSolverCalculixCcx",
        ],
        doc,
        f"{tag}_SolverCcx",
    )
    mesh_obj = _try_make(
        ObjectsFem,
        ["makeMeshGmsh", "makeMeshNetgen"],
        doc,
        f"{tag}_FEMMesh",
    )

    if analysis is None or solver is None or mesh_obj is None:
        raise RuntimeError(
            "Unable to create FEM analysis/solver/mesh objects. "
            "Check this FreeCAD build has FEM + CalculiX + mesher factories.",
        )

    _add_analysis_member(analysis, solver)
    _add_analysis_member(analysis, mesh_obj)
    return analysis, solver, mesh_obj


def _mesh_support(mesh_obj, support):
    if hasattr(mesh_obj, "Part"):
        mesh_obj.Part = support
    elif hasattr(mesh_obj, "Shape"):
        mesh_obj.Shape = support

    def _mesh_generated(obj):
        fem_mesh = getattr(obj, "FemMesh", None)
        if fem_mesh is None:
            return False
        node_count = getattr(fem_mesh, "NodeCount", 0)
        face_count = getattr(fem_mesh, "FaceCount", 0)
        volume_count = getattr(fem_mesh, "VolumeCount", 0)
        return bool(node_count) and bool(face_count or volume_count)

    def _tool_stderr(tool):
        proc = getattr(tool, "process", None)
        if proc is None:
            return ""
        err = bytes(proc.readAllStandardError()).decode("utf-8", "ignore").strip()
        out = bytes(proc.readAllStandardOutput()).decode("utf-8", "ignore").strip()
        return err or out

    def _import_tool(module_names, class_name):
        for module_name in module_names:
            try:
                mod = __import__(module_name, fromlist=[class_name])
                return getattr(mod, class_name)
            except Exception:
                continue
        raise ImportError(f"{class_name} not available in {module_names}")

    def _run_tool_process(tool, label, timeout_ms=120000):
        if not hasattr(tool, "run"):
            raise RuntimeError(f"{label} tool has no run() method")

        tool.run(blocking=False)
        proc = getattr(tool, "process", None)
        if proc is not None and not proc.waitForFinished(timeout_ms):
            try:
                proc.kill()
            except Exception:
                pass
            raise RuntimeError(f"{label} mesher timed out after {timeout_ms/1000:.0f}s")

        if hasattr(tool, "update_properties"):
            tool.update_properties()

        if proc is not None and getattr(proc, "exitCode", lambda: 0)() != 0:
            msg = _tool_stderr(tool)
            raise RuntimeError(msg or f"{label} process exit code {proc.exitCode()}")

    def _run_gmsh(obj):
        GmshTools = _import_tool(
            ("femmesh.gmsh.gmshtools", "femmesh.gmshtools"),
            "GmshTools",
        )
        tool = GmshTools(obj)
        if hasattr(tool, "create_mesh"):
            err = tool.create_mesh()
            if err:
                raise RuntimeError(str(err))
        else:
            _run_tool_process(tool, "gmsh")
        if not _mesh_generated(obj):
            raise RuntimeError("gmsh produced empty mesh")

    def _run_netgen(obj):
        NetgenTools = _import_tool(
            ("femmesh.netgen.netgentools", "femmesh.netgentools"),
            "NetgenTools",
        )
        tool = NetgenTools(obj)
        _run_tool_process(tool, "netgen")
        if not _mesh_generated(obj):
            raise RuntimeError("netgen produced empty mesh")

    try:
        _run_gmsh(mesh_obj)
        return "gmsh"
    except Exception as gmsh_exc:
        try:
            _run_netgen(mesh_obj)
            return "netgen"
        except Exception as netgen_exc:
            raise RuntimeError(
                "Mesh generation failed: "
                f"gmsh={gmsh_exc}; netgen={netgen_exc}"
            ) from netgen_exc


def _add_fixed_constraint(doc, analysis, support, edge_name, tag):
    import ObjectsFem

    fixed = _try_make(
        ObjectsFem,
        ["makeConstraintFixed"],
        doc,
        f"{tag}_Fixed",
    )
    _set_constraint_refs(fixed, [(support, edge_name)])
    _add_analysis_member(analysis, fixed)
    return fixed


def _add_force_constraint(doc, analysis, support, edge_name, tag, force=1000.0):
    import ObjectsFem

    force_obj = _try_make(
        ObjectsFem,
        ["makeConstraintForce"],
        doc,
        f"{tag}_Force",
    )
    _set_constraint_refs(force_obj, [(support, edge_name)])
    if hasattr(force_obj, "Force"):
        force_obj.Force = force
    _add_analysis_member(analysis, force_obj)
    return force_obj


def _add_pressure_constraint(doc, analysis, support, tag, pressure=0.1):
    import ObjectsFem

    pressure_obj = _try_make(
        ObjectsFem,
        ["makeConstraintPressure"],
        doc,
        f"{tag}_Pressure",
    )
    _set_constraint_refs(pressure_obj, [(support, "Face1")])
    if hasattr(pressure_obj, "Pressure"):
        pressure_obj.Pressure = pressure
    _add_analysis_member(analysis, pressure_obj)
    return pressure_obj


def _analysis_has_material(analysis):
    group = getattr(analysis, "Group", []) or []
    for obj in group:
        type_id = getattr(obj, "TypeId", "")
        props = set(getattr(obj, "PropertiesList", []) or [])
        if "Material" in type_id or "Material" in props:
            return True
    return False


def _mesh_has_shell_or_volume_elements(mesh_obj):
    fem_mesh = getattr(mesh_obj, "FemMesh", None)
    if fem_mesh is None:
        return False
    face_count = getattr(fem_mesh, "FaceCount", 0)
    volume_count = getattr(fem_mesh, "VolumeCount", 0)
    return bool(face_count or volume_count)


def _run_ccx(analysis, solver, mesh_obj):
    if not _mesh_has_shell_or_volume_elements(mesh_obj):
        raise RuntimeError(
            "FEM mesh has no shell/volume elements. Regenerate mesh before solve.",
        )
    if not _analysis_has_material(analysis):
        raise RuntimeError("No material object defined in the analysis.")

    try:
        from femtools.ccxtools import FemToolsCcx
    except ImportError as exc:
        raise RuntimeError("femtools.ccxtools is required to run CalculiX") from exc

    fem = FemToolsCcx(analysis=analysis, solver=solver)
    if hasattr(fem, "purge_results"):
        fem.purge_results()
    if hasattr(fem, "reset_all"):
        fem.reset_all()
    if hasattr(fem, "update_objects"):
        fem.update_objects()

    result = fem.run() if hasattr(fem, "run") else None
    return result


DEFAULT_FAILURE_OPTIONS = {
    "XT": 1000.0,
    "XC": 800.0,
    "YT": 60.0,
    "YC": 200.0,
    "ZT": 60.0,
    "ZC": 200.0,
    "S12": 80.0,
    "S13": 80.0,
    "S23": 60.0,
    "f12": 0.0,
    "f13": 0.0,
    "f23": 0.0,
}


def _list_result_objects(analysis):
    group = getattr(analysis, "Group", []) or []
    out = []
    for obj in group:
        type_id = getattr(obj, "TypeId", "")
        props = set(getattr(obj, "PropertiesList", []) or [])
        if (
            "FemResult" in type_id
            or "StressXX" in props
            or "NodeStressXX" in props
        ):
            out.append(obj)
    return out


def _series_from_value(obj, value):
    if isinstance(value, dict):
        try:
            return {int(k): float(v) for k, v in value.items()}
        except Exception:
            return {}

    if isinstance(value, (list, tuple)):
        ids = None
        for key in ("NodeNumbers", "ElementNumbers", "Numbers"):
            if hasattr(obj, key):
                ids = list(getattr(obj, key))
                break
        if not ids:
            ids = list(range(1, len(value) + 1))
        return {int(i): float(v) for i, v in zip(ids, value)}

    return {}


def _component(result_obj, names):
    for name in names:
        if hasattr(result_obj, name):
            series = _series_from_value(result_obj, getattr(result_obj, name))
            if series:
                return series
    return {}


def _collect_stress_tensors(result_obj):
    sxx = _component(result_obj, ["StressXX", "NodeStressXX", "SXX", "SigXX"])
    syy = _component(result_obj, ["StressYY", "NodeStressYY", "SYY", "SigYY"])
    szz = _component(result_obj, ["StressZZ", "NodeStressZZ", "SZZ", "SigZZ"])
    sxy = _component(result_obj, ["StressXY", "NodeStressXY", "SXY", "SigXY"])
    sxz = _component(result_obj, ["StressXZ", "NodeStressXZ", "SXZ", "SigXZ"])
    syz = _component(result_obj, ["StressYZ", "NodeStressYZ", "SYZ", "SigYZ"])

    ids = set(sxx.keys()) & set(syy.keys())
    if not ids:
        return []

    tensors = []
    for eid in sorted(ids):
        tensors.append(
            (
                eid,
                [
                    sxx.get(eid, 0.0),
                    syy.get(eid, 0.0),
                    szz.get(eid, 0.0),
                    sxy.get(eid, 0.0),
                    sxz.get(eid, 0.0),
                    syz.get(eid, 0.0),
                ],
            )
        )
    return tensors


def evaluate_failure_criteria(analysis, model_options=None, top_n=10):
    """Evaluate Tsai-Wu and Hashin indices from FEM result stresses.

    Returns a report dict with max indices and hotspot element IDs.
    """

    try:
        import numpy as np
    except Exception:
        return {
            "available": False,
            "reason": "numpy not available",
            "hotspots": [],
        }

    from ...fem.failure_models_composites import (
        calc_failure_hashin,
        calc_failure_tsai_wu,
    )

    options = dict(DEFAULT_FAILURE_OPTIONS)
    if model_options:
        options.update(model_options)

    rows = []
    for result_obj in _list_result_objects(analysis):
        tensors = _collect_stress_tensors(result_obj)
        for elem_id, stress_vec in tensors:
            s = np.array(stress_vec, dtype=float)
            e = np.zeros(6, dtype=float)
            tsai = float(calc_failure_tsai_wu(s, e, options))
            hashin = float(calc_failure_hashin(s, e, options))
            rows.append(
                {
                    "result_object": getattr(result_obj, "Name", "Result"),
                    "element_id": int(elem_id),
                    "tsai_wu": tsai,
                    "hashin": hashin,
                    "max_index": max(tsai, hashin),
                }
            )

    if not rows:
        return {
            "available": False,
            "reason": "no stress result components found",
            "hotspots": [],
        }

    rows.sort(key=lambda r: r["max_index"], reverse=True)
    max_tsai = max(r["tsai_wu"] for r in rows)
    max_hashin = max(r["hashin"] for r in rows)

    return {
        "available": True,
        "model_options": options,
        "max_tsai_wu": max_tsai,
        "max_hashin": max_hashin,
        "max_failure_index": max(max_tsai, max_hashin),
        "hotspots": rows[:top_n],
    }


def run_full_shell_job(doc, support, *, case_id, boundary_conditions, solve=True):
    """Create analysis, mesh, constraints, and execute CalculiX.

    Parameters
    ----------
    doc
        Active FreeCAD document.
    support
        Part::Feature carrying the shell midsurface as ``Face1``.
    case_id
        One of ``tubular_shell``, ``cylindrical_panel_segment``,
        ``conical_panel_segment``.
    boundary_conditions
        Human-readable condition dictionary attached to result metadata.
    """

    if doc is None or support is None:
        raise RuntimeError(
            "run_solver=True requires a valid FreeCAD document and support shape",
        )

    analysis, solver, mesh_obj = _create_fem_base(doc, case_id)
    shell_section, material_obj = _add_shell_section_and_material(
        doc,
        analysis,
        support,
        case_id,
    )
    mesher = _mesh_support(mesh_obj, support)

    metrics = _edge_metrics(support.Shape)
    min_z = _pick_edge_by(metrics, "z_avg", pick_max=False)
    max_z = _pick_edge_by(metrics, "z_avg", pick_max=True)
    long_edges = _pick_longitudinal_edges(metrics)
    min_r = _pick_edge_by(metrics, "r_avg", pick_max=False)

    constraints = []
    if case_id == "tubular_shell":
        constraints.append(_add_fixed_constraint(doc, analysis, support, min_z, case_id))
        constraints.append(_add_force_constraint(doc, analysis, support, max_z, case_id))
    elif case_id == "cylindrical_panel_segment":
        for idx, edge_name in enumerate(long_edges, start=1):
            constraints.append(
                _add_fixed_constraint(
                    doc,
                    analysis,
                    support,
                    edge_name,
                    f"{case_id}_{idx}",
                )
            )
        constraints.append(_add_pressure_constraint(doc, analysis, support, case_id))
    elif case_id == "conical_panel_segment":
        for idx, edge_name in enumerate(long_edges, start=1):
            constraints.append(
                _add_fixed_constraint(
                    doc,
                    analysis,
                    support,
                    edge_name,
                    f"{case_id}_{idx}",
                )
            )
        constraints.append(_add_pressure_constraint(doc, analysis, support, case_id))
    else:
        raise ValueError(f"Unsupported shell solver case '{case_id}'")

    if hasattr(doc, "recompute"):
        doc.recompute()

    if not solve:
        solve_result = None
        failure_report = {
            "available": False,
            "reason": "solve skipped (mesh-only mode)",
            "hotspots": [],
        }
    else:
        solve_result = _run_ccx(analysis, solver, mesh_obj)
        failure_report = evaluate_failure_criteria(analysis)

    return {
        "analysis": analysis,
        "solver": solver,
        "mesh": mesh_obj,
        "constraints": [obj for obj in constraints if obj is not None],
        "mesher": mesher,
        "shell_section": shell_section,
        "material": material_obj,
        "solve_result": solve_result,
        "failure_report": failure_report,
        "boundary_conditions": boundary_conditions,
    }
