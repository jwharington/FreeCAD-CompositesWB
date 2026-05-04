#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <limits>
#include <queue>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include <BRepAdaptor_Surface.hxx>
#include <BRepBndLib.hxx>
#include <BRepClass_FaceClassifier.hxx>
#include <BRepTools.hxx>
#include <BRep_Tool.hxx>
#include <Bnd_Box.hxx>
#include <GeomLProp_SLProps.hxx>
#include <Precision.hxx>
#include <gp_Vec.hxx>
#include <TopAbs_State.hxx>
#include <TopExp_Explorer.hxx>
#include <TopoDS.hxx>
#include <TopoDS_Face.hxx>
#include <TopoDS_Shape.hxx>

#include <Mod/Part/App/TopoShapePy.h>

#include "_fishnet_algorithm_types.hpp"

namespace {

#include "_fishnet_relaxation_objective.inc"

static bool parse_point(PyObject *obj, Vec3 &out) {
    PyObject *seq = PySequence_Fast(obj, "point must be a sequence");
    if (!seq) {
        return false;
    }
    Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    if (n < 3) {
        Py_DECREF(seq);
        PyErr_SetString(PyExc_ValueError, "point must have 3 coordinates");
        return false;
    }
    PyObject **items = PySequence_Fast_ITEMS(seq);
    out.x = PyFloat_AsDouble(items[0]);
    out.y = PyFloat_AsDouble(items[1]);
    out.z = PyFloat_AsDouble(items[2]);
    Py_DECREF(seq);
    return !PyErr_Occurred();
}

static bool parse_face(PyObject *obj, std::array<int, 3> &out) {
    PyObject *seq = PySequence_Fast(obj, "face must be a sequence");
    if (!seq) {
        return false;
    }
    Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    if (n < 3) {
        Py_DECREF(seq);
        PyErr_SetString(PyExc_ValueError, "face must have at least 3 vertices");
        return false;
    }
    PyObject **items = PySequence_Fast_ITEMS(seq);
    out[0] = static_cast<int>(PyLong_AsLong(items[0]));
    out[1] = static_cast<int>(PyLong_AsLong(items[1]));
    out[2] = static_cast<int>(PyLong_AsLong(items[2]));
    Py_DECREF(seq);
    return !PyErr_Occurred();
}

static PyObject *build_vec3_tuple(const Vec3 &v) {
    PyObject *tuple = PyTuple_New(3);
    if (!tuple) {
        return nullptr;
    }
    PyObject *x = PyFloat_FromDouble(v.x);
    PyObject *y = PyFloat_FromDouble(v.y);
    PyObject *z = PyFloat_FromDouble(v.z);
    if (!x || !y || !z) {
        Py_XDECREF(x);
        Py_XDECREF(y);
        Py_XDECREF(z);
        Py_DECREF(tuple);
        return nullptr;
    }
    PyTuple_SET_ITEM(tuple, 0, x);
    PyTuple_SET_ITEM(tuple, 1, y);
    PyTuple_SET_ITEM(tuple, 2, z);
    return tuple;
}

static PyObject *build_vec3_list(const std::vector<Vec3> &values) {
    PyObject *list = PyList_New(static_cast<Py_ssize_t>(values.size()));
    if (!list) {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(values.size()); ++i) {
        PyObject *item = build_vec3_tuple(values[static_cast<size_t>(i)]);
        if (!item) {
            Py_DECREF(list);
            return nullptr;
        }
        PyList_SET_ITEM(list, i, item);
    }
    return list;
}

static PyObject *build_loop_list(const std::vector<std::vector<Vec3>> &loops) {
    PyObject *outer = PyList_New(static_cast<Py_ssize_t>(loops.size()));
    if (!outer) {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(loops.size()); ++i) {
        const auto &loop = loops[static_cast<size_t>(i)];
        PyObject *inner = PyList_New(static_cast<Py_ssize_t>(loop.size()));
        if (!inner) {
            Py_DECREF(outer);
            return nullptr;
        }
        for (Py_ssize_t j = 0; j < static_cast<Py_ssize_t>(loop.size()); ++j) {
            PyObject *item = build_vec3_tuple(loop[static_cast<size_t>(j)]);
            if (!item) {
                Py_DECREF(inner);
                Py_DECREF(outer);
                return nullptr;
            }
            PyList_SET_ITEM(inner, j, item);
        }
        PyList_SET_ITEM(outer, i, inner);
    }
    return outer;
}

static PyObject *build_quad_list(const std::vector<std::vector<int>> &quads) {
    PyObject *outer = PyTuple_New(static_cast<Py_ssize_t>(quads.size()));
    if (!outer) {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(quads.size()); ++i) {
        const auto &quad = quads[static_cast<size_t>(i)];
        PyObject *inner = PyTuple_New(static_cast<Py_ssize_t>(quad.size()));
        if (!inner) {
            Py_DECREF(outer);
            return nullptr;
        }
        for (Py_ssize_t j = 0; j < static_cast<Py_ssize_t>(quad.size()); ++j) {
            PyObject *item = PyLong_FromLong(quad[static_cast<size_t>(j)]);
            if (!item) {
                Py_DECREF(inner);
                Py_DECREF(outer);
                return nullptr;
            }
            PyTuple_SET_ITEM(inner, j, item);
        }
        PyTuple_SET_ITEM(outer, i, inner);
    }
    return outer;
}

static PyObject *build_strain_list(const std::vector<std::array<double, 3>> &strains) {
    PyObject *outer = PyList_New(static_cast<Py_ssize_t>(strains.size()));
    if (!outer) {
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(strains.size()); ++i) {
        const auto &s = strains[static_cast<size_t>(i)];
        PyObject *item = Py_BuildValue("(ddd)", s[0], s[1], s[2]);
        if (!item) {
            Py_DECREF(outer);
            return nullptr;
        }
        PyList_SET_ITEM(outer, i, item);
    }
    return outer;
}

static PyObject *build_double_list(const std::vector<double> &values) {
    PyObject *list = PyList_New(static_cast<Py_ssize_t>(values.size()));
    if (!list) {
        return nullptr;
    }
    for (size_t i = 0; i < values.size(); ++i) {
        PyObject *v = PyFloat_FromDouble(values[i]);
        if (!v) {
            Py_DECREF(list);
            return nullptr;
        }
        PyList_SET_ITEM(list, static_cast<Py_ssize_t>(i), v);
    }
    return list;
}

#include "_fishnet_geometry_sampling.inc"

#include "_fishnet_diagnostics_result.inc"

static PyObject *solve_geometry(PyObject *geometry_obj, PyObject *params_obj) {
    ensure_part_module_loaded();

    PyObject *params_copy = (!params_obj || params_obj == Py_None)
        ? PyDict_New()
        : PyDict_Copy(params_obj);
    if (!params_copy) {
        return nullptr;
    }
    if (!PyDict_Check(params_copy)) {
        Py_DECREF(params_copy);
        PyErr_SetString(PyExc_TypeError, "parameters must be a dict or None");
        return nullptr;
    }

    std::vector<PyObject *> faces;
    PyObject *faces_attr = PyObject_GetAttrString(geometry_obj, "Faces");
    if (faces_attr) {
        PyObject *faces_seq = PySequence_Fast(faces_attr, "Faces must be a sequence");
        Py_DECREF(faces_attr);
        if (faces_seq) {
            faces.reserve(static_cast<size_t>(PySequence_Fast_GET_SIZE(faces_seq)));
            for (Py_ssize_t i = 0; i < PySequence_Fast_GET_SIZE(faces_seq); ++i) {
                PyObject *item = PySequence_Fast_GET_ITEM(faces_seq, i);
                Py_INCREF(item);
                faces.push_back(item);
            }
            Py_DECREF(faces_seq);
        } else {
            PyErr_Clear();
        }
    } else {
        PyErr_Clear();
    }

    if (faces.empty() && PyObject_HasAttrString(geometry_obj, "ParameterRange") > 0) {
        Py_INCREF(geometry_obj);
        faces.push_back(geometry_obj);
    }

    if (faces.empty()) {
        return build_empty_geometry_result("fishnet solver needs at least one face", params_copy);
    }

    std::vector<TopoDS_Face> native_faces;
    native_faces.reserve(faces.size());
    for (PyObject *face_obj : faces) {
        TopoDS_Face native_face;
        if (!extract_native_face(face_obj, native_face)) {
            for (PyObject *face : faces) {
                Py_DECREF(face);
            }
            faces.clear();
            return build_empty_geometry_result("fishnet solver needs native Part.Face geometry", params_copy);
        }
        native_faces.push_back(native_face);
    }

    const std::string algorithm = solver_algorithm_from_params(params_copy);
    const bool acp_energy_mode = (algorithm == "acp_energy_v1");

    CurrentNodeSolverMode solver_mode = acp_energy_mode
        ? CurrentNodeSolverMode::SphereSurfaceExperimental
        : CurrentNodeSolverMode::UvNewton;
    if (PyObject *solver_obj = PyDict_GetItemString(params_copy, "current_node_solver")) {
        const char *solver_name = PyUnicode_Check(solver_obj) ? PyUnicode_AsUTF8(solver_obj) : nullptr;
        if (solver_name) {
            if (std::strcmp(solver_name, "spheresurface") == 0) {
                solver_mode = CurrentNodeSolverMode::SphereSurfaceExperimental;
            }
        } else {
            PyErr_Clear();
        }
    }
    bool single_face_run = (native_faces.size() == 1);
    double max_adjacent_normal_angle =
        (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental)
            ? (single_face_run ? 1.5707963267948966 : 0.0)
            : 1.5707963267948966;
    if (PyObject *angle_obj = PyDict_GetItemString(params_copy, "max_adjacent_normal_angle")) {
        double parsed_angle = PyFloat_AsDouble(angle_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_angle) && parsed_angle > 0.0) {
            max_adjacent_normal_angle = parsed_angle;
        } else {
            PyErr_Clear();
        }
    }
    bool strict_inside_updates =
        (solver_mode != CurrentNodeSolverMode::SphereSurfaceExperimental) || single_face_run;
    if (PyObject *strict_obj = PyDict_GetItemString(params_copy, "strict_inside_updates")) {
        int parsed_bool = PyObject_IsTrue(strict_obj);
        if (parsed_bool >= 0) {
            strict_inside_updates = (parsed_bool != 0);
        } else {
            PyErr_Clear();
        }
    }
    double max_local_fold_ratio =
        (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental && single_face_run) ? 1.7 : 0.0;
    if (PyObject *ratio_obj = PyDict_GetItemString(params_copy, "max_local_fold_ratio")) {
        double parsed_ratio = PyFloat_AsDouble(ratio_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_ratio) && parsed_ratio > 1.0) {
            max_local_fold_ratio = parsed_ratio;
        } else {
            PyErr_Clear();
        }
    }
    double max_shear_angle =
        (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental && single_face_run)
            ? 0.5235987755982988  // 30 deg
            : -1.0;
    if (PyObject *shear_obj = PyDict_GetItemString(params_copy, "max_shear_angle_deg")) {
        double parsed_deg = PyFloat_AsDouble(shear_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_deg) && parsed_deg >= 0.0) {
            max_shear_angle = parsed_deg * 0.017453292519943295;
        } else {
            PyErr_Clear();
        }
    }
    double max_inextensible_rel_error =
        (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental && single_face_run) ? 0.05 : 0.0;
    if (PyObject *inext_obj = PyDict_GetItemString(params_copy, "max_inextensible_rel_error")) {
        double parsed_rel = PyFloat_AsDouble(inext_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_rel) && parsed_rel > 0.0) {
            max_inextensible_rel_error = parsed_rel;
        } else {
            PyErr_Clear();
        }
    }
    bool enforce_local_strain_optimization =
        (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental && single_face_run);
    if (PyObject *strain_obj = PyDict_GetItemString(params_copy, "enforce_local_strain_optimization")) {
        int parsed_bool = PyObject_IsTrue(strain_obj);
        if (parsed_bool >= 0) {
            enforce_local_strain_optimization = (parsed_bool != 0);
        } else {
            PyErr_Clear();
        }
    }
    double max_local_edge_rel_error =
        (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental && single_face_run) ? 0.12 : 0.0;
    if (PyObject *edge_obj = PyDict_GetItemString(params_copy, "max_local_edge_rel_error")) {
        double parsed_rel = PyFloat_AsDouble(edge_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_rel) && parsed_rel > 0.0) {
            max_local_edge_rel_error = parsed_rel;
        } else {
            PyErr_Clear();
        }
    }
    bool incremental_growth = acp_energy_mode;
    if (PyObject *grow_obj = PyDict_GetItemString(params_copy, "incremental_growth")) {
        int parsed_bool = PyObject_IsTrue(grow_obj);
        if (parsed_bool >= 0) {
            incremental_growth = (parsed_bool != 0);
        } else {
            PyErr_Clear();
        }
    }

    bool paper_strict_inextensible = false;
    if (PyObject *strict_obj = PyDict_GetItemString(params_copy, "paper_strict_inextensible")) {
        int parsed_bool = PyObject_IsTrue(strict_obj);
        if (parsed_bool >= 0) {
            paper_strict_inextensible = (parsed_bool != 0);
        } else {
            PyErr_Clear();
        }
    }
    double paper_strict_rel_tol = 1.0e-3;
    if (PyObject *strict_tol_obj = PyDict_GetItemString(params_copy, "paper_strict_rel_tol")) {
        double parsed_tol = PyFloat_AsDouble(strict_tol_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_tol) && parsed_tol >= 0.0) {
            paper_strict_rel_tol = parsed_tol;
        } else {
            PyErr_Clear();
        }
    }

    if (paper_strict_inextensible) {
        // Keep strict geometric constraints, but DO NOT disable fold/shear guards.
        max_inextensible_rel_error = 0.0;
        enforce_local_strain_optimization = false;
        max_local_edge_rel_error = 0.0;
        strict_inside_updates = true;
    }

    ExperimentalSolveStats experimental_stats;

    double sample_max_length = 0.0;
    if (PyObject *max_length_obj = PyDict_GetItemString(params_copy, "max_length")) {
        sample_max_length = PyFloat_AsDouble(max_length_obj);
        if (PyErr_Occurred()) {
            PyErr_Clear();
            sample_max_length = 0.0;
        }
    }
    double nominal_spacing = 0.0;
    if (PyObject *spacing_obj = PyDict_GetItemString(params_copy, "fabric_spacing")) {
        nominal_spacing = PyFloat_AsDouble(spacing_obj);
        if (PyErr_Occurred()) {
            PyErr_Clear();
            nominal_spacing = 0.0;
        }
    }
    if (sample_max_length <= 0.0) {
        sample_max_length = nominal_spacing;
    }
    if (nominal_spacing <= 0.0) {
        nominal_spacing = sample_max_length;
    }

    std::vector<FaceSample> samples;
    std::vector<int> face_indices;
    std::vector<Vec3> points;
    std::vector<Vec3> layout_points;
    std::vector<std::array<int, 3>> triangles;
    std::vector<std::vector<int>> quads;

    for (size_t i = 0; i < native_faces.size(); ++i) {
        FaceSample sample = sample_face(
            native_faces[i],
            sample_max_length,
            solver_mode,
            max_adjacent_normal_angle,
            strict_inside_updates,
            max_local_fold_ratio,
            max_shear_angle,
            max_inextensible_rel_error,
            enforce_local_strain_optimization,
            max_local_edge_rel_error,
            incremental_growth,
            paper_strict_inextensible,
            paper_strict_rel_tol,
            (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental) ? &experimental_stats : nullptr
        );
        if (sample.points.empty() || sample.triangles.empty()) {
            continue;
        }

        if (!samples.empty() && !sample.layout_points.empty()) {
            transfer_layout_between_faces(samples.back(), sample);
        }

        int offset = static_cast<int>(points.size());
        points.insert(points.end(), sample.points.begin(), sample.points.end());
        layout_points.insert(layout_points.end(), sample.layout_points.begin(), sample.layout_points.end());
        for (const auto &tri : sample.triangles) {
            triangles.push_back({tri[0] + offset, tri[1] + offset, tri[2] + offset});
        }
        for (const auto &quad : sample.quads) {
            quads.push_back({quad[0] + offset, quad[1] + offset, quad[2] + offset, quad[3] + offset});
        }
        face_indices.push_back(static_cast<int>(i));
        samples.push_back(std::move(sample));
    }

    for (PyObject *face : faces) {
        Py_DECREF(face);
    }
    faces.clear();

    if (points.empty() || triangles.empty() || samples.empty()) {
        return build_empty_geometry_result("fishnet solver needs at least one face", params_copy);
    }

    Vec3 origin = centroid(points);
    Vec3 normal{}, x_axis{}, y_axis{};
    build_basis(points, triangles, normal, x_axis, y_axis);

    std::vector<Vec3> local_points;
    std::vector<Vec3> fabric_points;
    local_points.reserve(points.size());
    fabric_points.reserve(points.size());
    for (size_t pi = 0; pi < points.size(); ++pi) {
        const auto &point = points[pi];
        Vec3 local = project_point(point, origin, x_axis, y_axis, normal);
        local_points.push_back(local);
        Vec3 seed = {local.x, local.y, 0.0};
        if (nominal_spacing > kVectorZeroEpsilon && pi < layout_points.size()) {
            seed = {layout_points[pi].x * nominal_spacing, layout_points[pi].y * nominal_spacing, 0.0};
        }
        fabric_points.push_back(seed);
    }

    std::vector<std::vector<int>> loops_idx = boundary_loops(triangles);
    std::vector<std::pair<int, int>> constrained_edges = !quads.empty()
        ? perimeter_edges_from_quads(quads)
        : edges_from_triangles(triangles);
    double nominal_edge_length = nominal_spacing;
    int relax_iterations = solver_iterations_from_params(params_copy);
    if (relax_iterations <= 0) {
        relax_iterations = 120;
    }

    AcpPropagationSummary acp_summary;
    std::vector<double> edge_targets;
    std::vector<double> edge_weights;
    if (acp_energy_mode) {
        acp_summary = initialize_acp_layout(
            points,
            local_points,
            constrained_edges,
            x_axis,
            y_axis,
            nominal_edge_length,
            params_copy,
            fabric_points
        );
        const std::string material_model = param_string(params_copy, "material_model", "woven");
        const double ud_coefficient = param_double(params_copy, "ud_coefficient", 0.0);
        build_acp_edge_objective(
            local_points,
            constrained_edges,
            nominal_edge_length,
            acp_summary.primary_axis,
            material_model,
            ud_coefficient,
            edge_targets,
            edge_weights
        );
    }

    std::vector<double> residual_history;
    relax_fabric_points_with_edge_constraints(
        fabric_points,
        constrained_edges,
        loops_idx,
        nominal_edge_length,
        relax_iterations,
        &residual_history,
        acp_energy_mode ? &edge_targets : nullptr,
        acp_energy_mode ? &edge_weights : nullptr
    );

    std::vector<std::vector<Vec3>> loops_pts;
    loops_pts.reserve(loops_idx.size());
    for (const auto &loop : loops_idx) {
        loops_pts.push_back(loop_to_points(loop, fabric_points));
    }

    std::vector<std::array<double, 3>> strains = face_strains(triangles, local_points, normal);

    PyObject *fabric_points_list = build_vec3_list(fabric_points);
    PyObject *fabric_quads_list = build_quad_list(quads);
    PyObject *boundary_loops_list = build_loop_list(loops_pts);
    PyObject *strains_list = build_strain_list(strains);
    PyObject *mesh_points_list = build_vec3_list(points);
    std::vector<std::vector<int>> mesh_face_vec;
    mesh_face_vec.reserve(triangles.size());
    for (const auto &face : triangles) {
        mesh_face_vec.push_back({face[0], face[1], face[2]});
    }
    PyObject *mesh_faces_list = build_quad_list(mesh_face_vec);

    PyObject *face_frames_list = PyList_New(0);
    PyObject *orientation_breaks_list = PyList_New(0);
    PyObject *atlas_charts_list = PyList_New(0);
    if (!face_frames_list || !orientation_breaks_list || !atlas_charts_list) {
        Py_XDECREF(face_frames_list);
        Py_XDECREF(orientation_breaks_list);
        Py_XDECREF(atlas_charts_list);
        Py_DECREF(fabric_points_list);
        Py_DECREF(fabric_quads_list);
        Py_DECREF(boundary_loops_list);
        Py_DECREF(strains_list);
        Py_DECREF(mesh_points_list);
        Py_DECREF(mesh_faces_list);
        Py_DECREF(params_copy);
        return nullptr;
    }

    double rel_tol = kDefaultEdgeLengthTolerance;
    bool rel_tol_from_parameter = false;
    if (PyObject *tol_obj = PyDict_GetItemString(params_copy, "edge_length_tolerance")) {
        rel_tol_from_parameter = true;
        double parsed_tol = PyFloat_AsDouble(tol_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_tol) && parsed_tol > 0.0) {
            rel_tol = parsed_tol;
        } else {
            PyErr_Clear();
        }
    }
    auto [edge_violations, max_rel_error] = acp_energy_mode
        ? edge_length_violation_summary_for_targets(fabric_points, constrained_edges, edge_targets, infer_nominal_edge_length(nominal_edge_length, fabric_points, constrained_edges), rel_tol)
        : edge_length_violation_summary_for_edges(fabric_points, constrained_edges, nominal_edge_length, rel_tol);
    if (acp_energy_mode && edge_violations > 0) {
        PyObject *break_item = PyDict_New();
        if (break_item) {
            PyObject *from_face = PyLong_FromLong(-1);
            PyObject *to_face = PyLong_FromLong(-1);
            if (from_face && to_face) {
                PyDict_SetItemString(break_item, "from_face", from_face);
                PyDict_SetItemString(break_item, "to_face", to_face);
            }
            Py_XDECREF(from_face);
            Py_XDECREF(to_face);
            char reason_buf[256];
            std::snprintf(
                reason_buf,
                sizeof(reason_buf),
                "edge length constraint violated: %d edges (max relative error %.6g, tolerance %.6g)",
                edge_violations,
                max_rel_error,
                rel_tol
            );
            PyObject *reason = PyUnicode_FromString(reason_buf);
            if (reason) {
                PyDict_SetItemString(break_item, "reason", reason);
                Py_DECREF(reason);
            }
            PyList_Append(orientation_breaks_list, break_item);
            Py_DECREF(break_item);
        }
    }

    if (solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental && experimental_stats.calls > 0) {
        PyObject *diag_item = PyDict_New();
        if (diag_item) {
            PyObject *from_face = PyLong_FromLong(-1);
            PyObject *to_face = PyLong_FromLong(-1);
            if (from_face && to_face) {
                PyDict_SetItemString(diag_item, "from_face", from_face);
                PyDict_SetItemString(diag_item, "to_face", to_face);
            }
            Py_XDECREF(from_face);
            Py_XDECREF(to_face);
            double mean_improvement = experimental_stats.better_candidate_hits > 0
                ? (experimental_stats.improvement_sum / static_cast<double>(experimental_stats.better_candidate_hits))
                : 0.0;
            double local_seed_ratio = experimental_stats.seed_attempts > 0
                ? (static_cast<double>(experimental_stats.seed_local) / static_cast<double>(experimental_stats.seed_attempts))
                : 0.0;
            double mean_best_shift = experimental_stats.better_candidate_hits > 0
                ? (experimental_stats.best_shift_norm_sum / static_cast<double>(experimental_stats.better_candidate_hits))
                : 0.0;
            char reason_buf[512];
            std::snprintf(
                reason_buf,
                sizeof(reason_buf),
                "experimental spheresurface diagnostics: calls=%d base_failures=%d seed_attempts=%d seed_solved=%d seed_local=%d local_seed_ratio=%.6g better_candidate_hits=%d mean_improvement=%.6g mean_best_shift=%.6g max_best_shift=%.6g fallbacks=%d",
                experimental_stats.calls,
                experimental_stats.base_failures,
                experimental_stats.seed_attempts,
                experimental_stats.seed_solved,
                experimental_stats.seed_local,
                local_seed_ratio,
                experimental_stats.better_candidate_hits,
                mean_improvement,
                mean_best_shift,
                experimental_stats.best_shift_norm_max,
                experimental_stats.fallback_count
            );
            PyObject *reason = PyUnicode_FromString(reason_buf);
            if (reason) {
                PyDict_SetItemString(diag_item, "reason", reason);
                Py_DECREF(reason);
            }
            PyList_Append(orientation_breaks_list, diag_item);
            Py_DECREF(diag_item);
        }
    }

    if (!samples.empty()) {
        double seam_tol_3d = 1.0e-6;
        SeamContinuityStats seam_stats = seam_layout_continuity_summary(points, fabric_points, seam_tol_3d);
        if (seam_stats.group_count > 0) {
            double seam_limit = nominal_edge_length > kVectorZeroEpsilon ? nominal_edge_length * 3.0 : 5.0;
            if (seam_stats.max_min_distance > seam_limit) {
                PyObject *break_item = PyDict_New();
                if (break_item) {
                    PyObject *from_face = PyLong_FromLong(-1);
                    PyObject *to_face = PyLong_FromLong(-1);
                    if (from_face && to_face) {
                        PyDict_SetItemString(break_item, "from_face", from_face);
                        PyDict_SetItemString(break_item, "to_face", to_face);
                    }
                    Py_XDECREF(from_face);
                    Py_XDECREF(to_face);
                    char reason_buf[256];
                    std::snprintf(
                        reason_buf,
                        sizeof(reason_buf),
                        "seam continuity degraded: %d groups (mean min distance %.6g, max min distance %.6g, limit %.6g)",
                        seam_stats.group_count,
                        seam_stats.mean_min_distance,
                        seam_stats.max_min_distance,
                        seam_limit
                    );
                    PyObject *reason = PyUnicode_FromString(reason_buf);
                    if (reason) {
                        PyDict_SetItemString(break_item, "reason", reason);
                        Py_DECREF(reason);
                    }
                    PyList_Append(orientation_breaks_list, break_item);
                    Py_DECREF(break_item);
                }
            }
        }
    }

    if (!samples.empty()) {
        PyObject *frame = build_face_frame_dict(samples.front(), face_indices.front(), true);
        if (!frame) {
            Py_DECREF(face_frames_list);
            Py_DECREF(orientation_breaks_list);
            Py_DECREF(atlas_charts_list);
            Py_DECREF(fabric_points_list);
            Py_DECREF(fabric_quads_list);
            Py_DECREF(boundary_loops_list);
            Py_DECREF(strains_list);
            Py_DECREF(mesh_points_list);
            Py_DECREF(mesh_faces_list);
            Py_DECREF(params_copy);
            return nullptr;
        }
        if (PyList_Append(face_frames_list, frame) != 0) {
            Py_DECREF(frame);
            Py_DECREF(face_frames_list);
            Py_DECREF(orientation_breaks_list);
            Py_DECREF(atlas_charts_list);
            Py_DECREF(fabric_points_list);
            Py_DECREF(fabric_quads_list);
            Py_DECREF(boundary_loops_list);
            Py_DECREF(strains_list);
            Py_DECREF(mesh_points_list);
            Py_DECREF(mesh_faces_list);
            Py_DECREF(params_copy);
            return nullptr;
        }
        Py_DECREF(frame);

        std::vector<std::vector<int>> chart_quads_vec = quads;
        if (chart_quads_vec.empty()) {
            chart_quads_vec = mesh_face_vec;
        }

        int overlap_rejections = 0;
        std::vector<AtlasChartBuild> charts = split_into_non_overlapping_charts(fabric_points, chart_quads_vec, overlap_rejections);
        double x_offset = 0.0;
        for (size_t chart_i = 0; chart_i < charts.size(); ++chart_i) {
            PyObject *chart = PyDict_New();
            if (!chart) {
                Py_DECREF(face_frames_list);
                Py_DECREF(orientation_breaks_list);
                Py_DECREF(atlas_charts_list);
                Py_DECREF(fabric_points_list);
                Py_DECREF(fabric_quads_list);
                Py_DECREF(boundary_loops_list);
                Py_DECREF(strains_list);
                Py_DECREF(mesh_points_list);
                Py_DECREF(mesh_faces_list);
                Py_DECREF(params_copy);
                return nullptr;
            }

            std::vector<Vec3> shifted_points = charts[chart_i].points;
            for (auto &p : shifted_points) {
                p.x += x_offset;
            }

            PyObject *chart_index_obj = PyLong_FromLong(static_cast<long>(chart_i));
            PyObject *chart_points = build_vec3_list(shifted_points);
            PyObject *chart_quads = build_quad_list(charts[chart_i].quads);
            PyObject *bounds_list = PyList_New(4);
            if (!chart_index_obj || !chart_points || !chart_quads || !bounds_list) {
                Py_XDECREF(chart_index_obj);
                Py_XDECREF(chart_points);
                Py_XDECREF(chart_quads);
                Py_XDECREF(bounds_list);
                Py_DECREF(chart);
                Py_DECREF(face_frames_list);
                Py_DECREF(orientation_breaks_list);
                Py_DECREF(atlas_charts_list);
                Py_DECREF(fabric_points_list);
                Py_DECREF(fabric_quads_list);
                Py_DECREF(boundary_loops_list);
                Py_DECREF(strains_list);
                Py_DECREF(mesh_points_list);
                Py_DECREF(mesh_faces_list);
                Py_DECREF(params_copy);
                return nullptr;
            }

            double min_x = shifted_points.empty() ? 0.0 : shifted_points.front().x;
            double max_x = shifted_points.empty() ? 0.0 : shifted_points.front().x;
            double min_y = shifted_points.empty() ? 0.0 : shifted_points.front().y;
            double max_y = shifted_points.empty() ? 0.0 : shifted_points.front().y;
            for (const auto &p : shifted_points) {
                min_x = std::min(min_x, p.x);
                max_x = std::max(max_x, p.x);
                min_y = std::min(min_y, p.y);
                max_y = std::max(max_y, p.y);
            }
            PyList_SET_ITEM(bounds_list, 0, PyFloat_FromDouble(min_x));
            PyList_SET_ITEM(bounds_list, 1, PyFloat_FromDouble(max_x));
            PyList_SET_ITEM(bounds_list, 2, PyFloat_FromDouble(min_y));
            PyList_SET_ITEM(bounds_list, 3, PyFloat_FromDouble(max_y));
            PyDict_SetItemString(chart, "chart_index", chart_index_obj);
            PyDict_SetItemString(chart, "points", chart_points);
            PyDict_SetItemString(chart, "quads", chart_quads);
            PyDict_SetItemString(chart, "bounds", bounds_list);
            PyList_Append(atlas_charts_list, chart);
            Py_DECREF(chart_index_obj);
            Py_DECREF(chart_points);
            Py_DECREF(chart_quads);
            Py_DECREF(bounds_list);
            Py_DECREF(chart);

            x_offset += (max_x - min_x) + kAtlasChartGap;
        }

        if (overlap_rejections > 0) {
            PyObject *break_item = PyDict_New();
            if (break_item) {
                PyObject *from_face = PyLong_FromLong(-1);
                PyObject *to_face = PyLong_FromLong(-1);
                if (from_face && to_face) {
                    PyDict_SetItemString(break_item, "from_face", from_face);
                    PyDict_SetItemString(break_item, "to_face", to_face);
                }
                Py_XDECREF(from_face);
                Py_XDECREF(to_face);
                PyObject *reason = PyUnicode_FromFormat("atlas overlap split: %d overlapping placements moved to new charts", overlap_rejections);
                if (reason) {
                    PyDict_SetItemString(break_item, "reason", reason);
                    Py_DECREF(reason);
                }
                PyList_Append(orientation_breaks_list, break_item);
                Py_DECREF(break_item);
            }
        }
    }

    PyObject *result = PyDict_New();
    if (!result) {
        Py_DECREF(face_frames_list);
        Py_DECREF(orientation_breaks_list);
        Py_DECREF(atlas_charts_list);
        Py_DECREF(params_copy);
        return nullptr;
    }

    std::vector<Vec3> warp_weft_points;
    warp_weft_points.reserve(points.size());
    for (size_t pi = 0; pi < points.size(); ++pi) {
        Vec3 seed = local_points[pi];
        seed.z = 0.0;
        if (nominal_spacing > kVectorZeroEpsilon && pi < layout_points.size()) {
            seed = {layout_points[pi].x * nominal_spacing, layout_points[pi].y * nominal_spacing, 0.0};
        } else if (pi < layout_points.size()) {
            seed = {layout_points[pi].x, layout_points[pi].y, 0.0};
        }
        warp_weft_points.push_back(seed);
    }
    PyObject *warp_weft_points_list = build_vec3_list(warp_weft_points);
    std::vector<std::vector<Vec3>> warp_weft_loops_pts;
    warp_weft_loops_pts.reserve(loops_idx.size());
    for (const auto &loop : loops_idx) {
        warp_weft_loops_pts.push_back(loop_to_points(loop, warp_weft_points));
    }
    PyObject *warp_weft_boundary_loops_list = build_loop_list(warp_weft_loops_pts);
    if (!warp_weft_points_list || !warp_weft_boundary_loops_list) {
        Py_XDECREF(warp_weft_points_list);
        Py_XDECREF(warp_weft_boundary_loops_list);
        Py_DECREF(result);
        Py_DECREF(fabric_points_list);
        Py_DECREF(fabric_quads_list);
        Py_DECREF(boundary_loops_list);
        Py_DECREF(strains_list);
        Py_DECREF(mesh_points_list);
        Py_DECREF(mesh_faces_list);
        Py_DECREF(face_frames_list);
        Py_DECREF(orientation_breaks_list);
        Py_DECREF(atlas_charts_list);
        Py_DECREF(params_copy);
        return nullptr;
    }

    set_result_common_fields(
        result,
        fabric_points_list,
        warp_weft_points_list,
        fabric_quads_list,
        boundary_loops_list,
        warp_weft_boundary_loops_list,
        strains_list,
        mesh_points_list,
        mesh_faces_list,
        face_frames_list,
        orientation_breaks_list,
        atlas_charts_list,
        origin,
        normal,
        x_axis,
        y_axis,
        params_copy
    );

    const bool converged = !(acp_energy_mode && edge_violations > 0);
    const char *termination_reason = converged ? "converged" : "max_iterations";
    const int max_iterations = relax_iterations;

    PyObject *diagnostics = PyDict_New();
    if (diagnostics) {
        add_solver_diagnostics(
            diagnostics,
            params_copy,
            static_cast<long>(samples.size()),
            static_cast<long>(points.size()),
            static_cast<long>(triangles.size()),
            static_cast<long>(quads.size()),
            PyList_Size(orientation_breaks_list),
            edge_violations,
            max_rel_error,
            rel_tol,
            rel_tol_from_parameter,
            max_iterations,
            residual_history,
            acp_energy_mode,
            acp_summary
        );
        attach_solver_metadata(result, params_copy, termination_reason, converged, diagnostics);
        Py_DECREF(diagnostics);
    } else {
        attach_solver_metadata(result, params_copy, termination_reason, converged);
    }

    Py_DECREF(fabric_points_list);
    Py_DECREF(warp_weft_points_list);
    Py_DECREF(fabric_quads_list);
    Py_DECREF(boundary_loops_list);
    Py_DECREF(warp_weft_boundary_loops_list);
    Py_DECREF(strains_list);
    Py_DECREF(mesh_points_list);
    Py_DECREF(mesh_faces_list);
    Py_DECREF(face_frames_list);
    Py_DECREF(orientation_breaks_list);
    Py_DECREF(atlas_charts_list);
    Py_DECREF(params_copy);
    return result;
}

static PyObject *solve_impl(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char *kwlist[] = {"mesh_points", "mesh_faces", "parameters", nullptr};
    PyObject *points_obj = nullptr;
    PyObject *faces_obj = Py_None;
    PyObject *params_obj = Py_None;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OO", const_cast<char **>(kwlist), &points_obj, &faces_obj, &params_obj)) {
        return nullptr;
    }

    if (geometry_like(points_obj)) {
        return solve_geometry(points_obj, params_obj);
    }

    std::vector<Vec3> points;
    std::vector<std::array<int, 3>> faces;

    PyObject *points_seq = PySequence_Fast(points_obj, "mesh_points must be a sequence");
    if (!points_seq) {
        return nullptr;
    }
    points.reserve(static_cast<size_t>(PySequence_Fast_GET_SIZE(points_seq)));
    for (Py_ssize_t i = 0; i < PySequence_Fast_GET_SIZE(points_seq); ++i) {
        Vec3 p;
        if (!parse_point(PySequence_Fast_GET_ITEM(points_seq, i), p)) {
            Py_DECREF(points_seq);
            return nullptr;
        }
        points.push_back(p);
    }
    Py_DECREF(points_seq);

    if (faces_obj != Py_None) {
        PyObject *faces_seq = PySequence_Fast(faces_obj, "mesh_faces must be a sequence");
        if (!faces_seq) {
            return nullptr;
        }
        faces.reserve(static_cast<size_t>(PySequence_Fast_GET_SIZE(faces_seq)));
        for (Py_ssize_t i = 0; i < PySequence_Fast_GET_SIZE(faces_seq); ++i) {
            std::array<int, 3> face{};
            if (!parse_face(PySequence_Fast_GET_ITEM(faces_seq, i), face)) {
                Py_DECREF(faces_seq);
                return nullptr;
            }
            if (face[0] < 0 || face[1] < 0 || face[2] < 0 ||
                face[0] >= static_cast<int>(points.size()) ||
                face[1] >= static_cast<int>(points.size()) ||
                face[2] >= static_cast<int>(points.size())) {
                Py_DECREF(faces_seq);
                PyErr_SetString(PyExc_ValueError, "face index out of range");
                return nullptr;
            }
            faces.push_back(face);
        }
        Py_DECREF(faces_seq);
    }

    PyObject *params_copy = (!params_obj || params_obj == Py_None)
        ? PyDict_New()
        : PyDict_Copy(params_obj);
    if (!params_copy) {
        return nullptr;
    }
    if (!PyDict_Check(params_copy)) {
        Py_DECREF(params_copy);
        PyErr_SetString(PyExc_TypeError, "parameters must be a dict or None");
        return nullptr;
    }

    const std::string algorithm = solver_algorithm_from_params(params_copy);
    const bool acp_energy_mode = (algorithm == "acp_energy_v1");

    if (points.empty()) {
        PyObject *res = PyDict_New();
        PyDict_SetItemString(res, "valid", Py_False);
        PyDict_SetItemString(res, "error", PyUnicode_FromString("fishnet solver needs at least one point"));
        PyDict_SetItemString(res, "fabric_points", PyList_New(0));
        PyDict_SetItemString(res, "fabric_quads", PyList_New(0));
        PyDict_SetItemString(res, "boundary_loops", PyList_New(0));
        PyDict_SetItemString(res, "strains", PyList_New(0));
        PyDict_SetItemString(res, "mesh_points", PyList_New(0));
        PyDict_SetItemString(res, "mesh_faces", PyList_New(0));
        PyDict_SetItemString(res, "face_frames", PyList_New(0));
        PyDict_SetItemString(res, "orientation_breaks", PyList_New(0));
        PyDict_SetItemString(res, "atlas_charts", PyList_New(0));
        PyDict_SetItemString(res, "parameters", params_copy);
        attach_solver_metadata(res, params_copy, "infeasible", false);
        Py_DECREF(params_copy);
        return res;
    }
    if (faces.empty()) {
        PyObject *res = PyDict_New();
        PyDict_SetItemString(res, "valid", Py_False);
        PyDict_SetItemString(res, "error", PyUnicode_FromString("fishnet solver needs at least one face"));
        PyDict_SetItemString(res, "fabric_points", PyList_New(0));
        PyDict_SetItemString(res, "fabric_quads", PyList_New(0));
        PyDict_SetItemString(res, "boundary_loops", PyList_New(0));
        PyDict_SetItemString(res, "strains", PyList_New(0));
        PyDict_SetItemString(res, "mesh_points", PyList_New(0));
        PyDict_SetItemString(res, "mesh_faces", PyList_New(0));
        PyDict_SetItemString(res, "face_frames", PyList_New(0));
        PyDict_SetItemString(res, "orientation_breaks", PyList_New(0));
        PyDict_SetItemString(res, "atlas_charts", PyList_New(0));
        PyDict_SetItemString(res, "parameters", params_copy);
        attach_solver_metadata(res, params_copy, "infeasible", false);
        Py_DECREF(params_copy);
        return res;
    }

    Vec3 origin = centroid(points);
    Vec3 normal{}, x_axis{}, y_axis{};
    build_basis(points, faces, normal, x_axis, y_axis);

    std::vector<Vec3> local_points;
    std::vector<Vec3> fabric_points;
    local_points.reserve(points.size());
    fabric_points.reserve(points.size());
    for (const auto &p : points) {
        Vec3 local = project_point(p, origin, x_axis, y_axis, normal);
        local_points.push_back(local);
        fabric_points.push_back({local.x, local.y, 0.0});
    }

    std::vector<std::vector<int>> fabric_quads = extract_quads(faces, points);
    std::vector<std::vector<int>> loops_idx = boundary_loops(faces);
    std::vector<std::pair<int, int>> constrained_edges = !fabric_quads.empty()
        ? perimeter_edges_from_quads(fabric_quads)
        : edges_from_triangles(faces);
    double nominal_edge_length = 0.0;
    if (PyObject *spacing_obj = PyDict_GetItemString(params_copy, "fabric_spacing")) {
        nominal_edge_length = PyFloat_AsDouble(spacing_obj);
        if (PyErr_Occurred()) {
            PyErr_Clear();
            nominal_edge_length = 0.0;
        }
    }
    int relax_iterations = solver_iterations_from_params(params_copy);
    if (relax_iterations <= 0) {
        relax_iterations = 120;
    }

    AcpPropagationSummary acp_summary;
    std::vector<double> edge_targets;
    std::vector<double> edge_weights;
    if (acp_energy_mode) {
        acp_summary = initialize_acp_layout(
            points,
            local_points,
            constrained_edges,
            x_axis,
            y_axis,
            nominal_edge_length,
            params_copy,
            fabric_points
        );
        const std::string material_model = param_string(params_copy, "material_model", "woven");
        const double ud_coefficient = param_double(params_copy, "ud_coefficient", 0.0);
        build_acp_edge_objective(
            local_points,
            constrained_edges,
            nominal_edge_length,
            acp_summary.primary_axis,
            material_model,
            ud_coefficient,
            edge_targets,
            edge_weights
        );
    }

    std::vector<double> residual_history;
    relax_fabric_points_with_edge_constraints(
        fabric_points,
        constrained_edges,
        loops_idx,
        nominal_edge_length,
        relax_iterations,
        &residual_history,
        acp_energy_mode ? &edge_targets : nullptr,
        acp_energy_mode ? &edge_weights : nullptr
    );

    std::vector<std::vector<Vec3>> loops_pts;
    loops_pts.reserve(loops_idx.size());
    for (const auto &loop : loops_idx) {
        loops_pts.push_back(loop_to_points(loop, fabric_points));
    }
    std::vector<std::array<double, 3>> strains = face_strains(faces, local_points, normal);

    PyObject *fabric_points_list = build_vec3_list(fabric_points);
    PyObject *fabric_quads_list = build_quad_list(fabric_quads);
    PyObject *boundary_loops_list = build_loop_list(loops_pts);
    PyObject *strains_list = build_strain_list(strains);
    PyObject *mesh_points_list = build_vec3_list(points);
    std::vector<std::vector<int>> mesh_face_vec;
    mesh_face_vec.reserve(faces.size());
    for (const auto &face : faces) {
        mesh_face_vec.push_back({face[0], face[1], face[2]});
    }
    PyObject *mesh_faces_list = build_quad_list(mesh_face_vec);
    PyObject *face_frames_list = PyList_New(1);
    PyObject *orientation_breaks_list = PyList_New(0);

    double rel_tol = kDefaultEdgeLengthTolerance;
    bool rel_tol_from_parameter = false;
    if (PyObject *tol_obj = PyDict_GetItemString(params_copy, "edge_length_tolerance")) {
        rel_tol_from_parameter = true;
        double parsed_tol = PyFloat_AsDouble(tol_obj);
        if (!PyErr_Occurred() && std::isfinite(parsed_tol) && parsed_tol > 0.0) {
            rel_tol = parsed_tol;
        } else {
            PyErr_Clear();
        }
    }
    auto [edge_violations, max_rel_error] = acp_energy_mode
        ? edge_length_violation_summary_for_targets(fabric_points, constrained_edges, edge_targets, infer_nominal_edge_length(nominal_edge_length, fabric_points, constrained_edges), rel_tol)
        : edge_length_violation_summary_for_edges(fabric_points, constrained_edges, nominal_edge_length, rel_tol);
    if (acp_energy_mode && orientation_breaks_list && edge_violations > 0) {
        PyObject *break_item = PyDict_New();
        if (break_item) {
            PyObject *from_face = PyLong_FromLong(-1);
            PyObject *to_face = PyLong_FromLong(-1);
            if (from_face && to_face) {
                PyDict_SetItemString(break_item, "from_face", from_face);
                PyDict_SetItemString(break_item, "to_face", to_face);
            }
            Py_XDECREF(from_face);
            Py_XDECREF(to_face);
            char reason_buf[256];
            std::snprintf(
                reason_buf,
                sizeof(reason_buf),
                "edge length constraint violated: %d edges (max relative error %.6g, tolerance %.6g)",
                edge_violations,
                max_rel_error,
                rel_tol
            );
            PyObject *reason = PyUnicode_FromString(reason_buf);
            if (reason) {
                PyDict_SetItemString(break_item, "reason", reason);
                Py_DECREF(reason);
            }
            PyList_Append(orientation_breaks_list, break_item);
            Py_DECREF(break_item);
        }
    }

    if (face_frames_list) {
        PyObject *frame = PyDict_New();
        if (frame) {
            PyObject *face_index = PyLong_FromLong(0);
            PyObject *origin_obj = build_vec3_tuple(origin);
            PyObject *normal_obj = build_vec3_tuple(normal);
            PyObject *x_axis_obj = build_vec3_tuple(x_axis);
            PyObject *y_axis_obj = build_vec3_tuple(y_axis);
            if (face_index && origin_obj && normal_obj && x_axis_obj && y_axis_obj) {
                PyDict_SetItemString(frame, "face_index", face_index);
                PyDict_SetItemString(frame, "origin", origin_obj);
                PyDict_SetItemString(frame, "normal", normal_obj);
                PyDict_SetItemString(frame, "x_axis", x_axis_obj);
                PyDict_SetItemString(frame, "y_axis", y_axis_obj);
                PyDict_SetItemString(frame, "continuous", Py_True);
                PyList_SET_ITEM(face_frames_list, 0, frame);
            } else {
                Py_DECREF(frame);
                Py_DECREF(face_frames_list);
                face_frames_list = nullptr;
            }
            Py_XDECREF(face_index);
            Py_XDECREF(origin_obj);
            Py_XDECREF(normal_obj);
            Py_XDECREF(x_axis_obj);
            Py_XDECREF(y_axis_obj);
        } else {
            Py_DECREF(face_frames_list);
            face_frames_list = nullptr;
        }
    }
    if (!fabric_points_list || !fabric_quads_list || !boundary_loops_list || !strains_list || !mesh_points_list || !mesh_faces_list || !face_frames_list || !orientation_breaks_list) {
        Py_XDECREF(fabric_points_list);
        Py_XDECREF(fabric_quads_list);
        Py_XDECREF(boundary_loops_list);
        Py_XDECREF(strains_list);
        Py_XDECREF(mesh_points_list);
        Py_XDECREF(mesh_faces_list);
        Py_XDECREF(face_frames_list);
        Py_XDECREF(orientation_breaks_list);
        Py_DECREF(params_copy);
        return nullptr;
    }

    PyObject *result = PyDict_New();
    if (!result) {
        Py_DECREF(fabric_points_list);
        Py_DECREF(fabric_quads_list);
        Py_DECREF(boundary_loops_list);
        Py_DECREF(strains_list);
        Py_DECREF(mesh_points_list);
        Py_DECREF(mesh_faces_list);
        Py_DECREF(face_frames_list);
        Py_DECREF(orientation_breaks_list);
        Py_DECREF(params_copy);
        return nullptr;
    }

    PyObject *atlas_charts_list = PyList_New(0);
    if (!atlas_charts_list) {
        Py_DECREF(result);
        Py_DECREF(fabric_points_list);
        Py_DECREF(fabric_quads_list);
        Py_DECREF(boundary_loops_list);
        Py_DECREF(strains_list);
        Py_DECREF(mesh_points_list);
        Py_DECREF(mesh_faces_list);
        Py_DECREF(face_frames_list);
        Py_DECREF(orientation_breaks_list);
        Py_DECREF(params_copy);
        return nullptr;
    }

    set_result_common_fields(
        result,
        fabric_points_list,
        fabric_points_list,
        fabric_quads_list,
        boundary_loops_list,
        boundary_loops_list,
        strains_list,
        mesh_points_list,
        mesh_faces_list,
        face_frames_list,
        orientation_breaks_list,
        atlas_charts_list,
        origin,
        normal,
        x_axis,
        y_axis,
        params_copy
    );

    const bool converged = !(acp_energy_mode && edge_violations > 0);
    const char *termination_reason = converged ? "converged" : "max_iterations";
    const int max_iterations = relax_iterations;

    PyObject *diagnostics = PyDict_New();
    if (diagnostics) {
        add_solver_diagnostics(
            diagnostics,
            params_copy,
            -1,
            static_cast<long>(points.size()),
            static_cast<long>(faces.size()),
            static_cast<long>(fabric_quads.size()),
            PyList_Size(orientation_breaks_list),
            edge_violations,
            max_rel_error,
            rel_tol,
            rel_tol_from_parameter,
            max_iterations,
            residual_history,
            acp_energy_mode,
            acp_summary
        );
        attach_solver_metadata(result, params_copy, termination_reason, converged, diagnostics);
        Py_DECREF(diagnostics);
    } else {
        attach_solver_metadata(result, params_copy, termination_reason, converged);
    }

    Py_DECREF(fabric_points_list);
    Py_DECREF(fabric_quads_list);
    Py_DECREF(boundary_loops_list);
    Py_DECREF(strains_list);
    Py_DECREF(mesh_points_list);
    Py_DECREF(mesh_faces_list);
    Py_DECREF(face_frames_list);
    Py_DECREF(orientation_breaks_list);
    Py_DECREF(atlas_charts_list);
    Py_DECREF(params_copy);
    return result;
}

}  // namespace

PyObject *fishnet_solve(PyObject *self, PyObject *args, PyObject *kwargs) {
    return solve_impl(self, args, kwargs);
}
