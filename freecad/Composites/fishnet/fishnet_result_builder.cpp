#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <limits>
#include <unordered_set>
#include <vector>

#include "fishnet_result_builder.hpp"

#include "fishnet_diagnostics_api.hpp"
#include "fishnet_layout_geometry_api.hpp"
#include "fishnet_options.hpp"
#include "fishnet_python_geometry.hpp"
#include "fishnet_python_util.hpp"
#include "fishnet_result_api.hpp"

namespace fishnet_internal
{
    static std::pair<int, double> summarize_edge_violations(
        bool acp_energy_mode,
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &constrained_edges,
        const std::vector<double> &edge_targets,
        double nominal_edge_length,
        double rel_tol)
    {
        if (acp_energy_mode)
        {
            return edge_length_violation_summary_for_targets(
                fabric_points,
                constrained_edges,
                edge_targets,
                infer_nominal_edge_length(nominal_edge_length, fabric_points, constrained_edges),
                rel_tol);
        }
        return edge_length_violation_summary_for_edges(
            fabric_points,
            constrained_edges,
            nominal_edge_length,
            rel_tol);
    }

    static void append_edge_violation_break(
        PyObject *orientation_breaks_list,
        bool acp_energy_mode,
        int edge_violations,
        double max_rel_error,
        double rel_tol)
    {
        if (!acp_energy_mode || !orientation_breaks_list || edge_violations <= 0)
        {
            return;
        }

        PyObject *break_item = PyDict_New();
        if (!break_item)
        {
            return;
        }
        PyObject *from_face = PyLong_FromLong(-1);
        PyObject *to_face = PyLong_FromLong(-1);
        if (from_face && to_face)
        {
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
            rel_tol);
        PyObject *reason = PyUnicode_FromString(reason_buf);
        if (reason)
        {
            PyDict_SetItemString(break_item, "reason", reason);
            Py_DECREF(reason);
        }
        PyList_Append(orientation_breaks_list, break_item);
        Py_DECREF(break_item);
    }

    static void append_experimental_diagnostics_break(
        PyObject *orientation_breaks_list,
        const ExperimentalSolveStats &experimental_stats)
    {
        if (!orientation_breaks_list || experimental_stats.calls <= 0)
        {
            return;
        }

        PyObject *diag_item = PyDict_New();
        if (!diag_item)
        {
            return;
        }
        PyObject *from_face = PyLong_FromLong(-1);
        PyObject *to_face = PyLong_FromLong(-1);
        if (from_face && to_face)
        {
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
            "spheresurface diagnostics: calls=%d base_failures=%d seed_attempts=%d seed_solved=%d seed_local=%d local_seed_ratio=%.6g better_candidate_hits=%d mean_improvement=%.6g mean_best_shift=%.6g max_best_shift=%.6g fallbacks=%d",
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
            experimental_stats.fallback_count);
        PyObject *reason = PyUnicode_FromString(reason_buf);
        if (reason)
        {
            PyDict_SetItemString(diag_item, "reason", reason);
            Py_DECREF(reason);
        }
        PyList_Append(orientation_breaks_list, diag_item);
        Py_DECREF(diag_item);
    }

    static void append_seam_continuity_break(
        PyObject *orientation_breaks_list,
        const std::vector<Vec3> &points,
        const std::vector<Vec3> &fabric_points,
        double nominal_edge_length)
    {
        if (!orientation_breaks_list || points.empty())
        {
            return;
        }

        constexpr double kSeamTol3d = 1.0e-6;
        SeamContinuityStats seam_stats = seam_layout_continuity_summary(points, fabric_points, kSeamTol3d);
        if (seam_stats.group_count <= 0)
        {
            return;
        }

        double seam_limit = nominal_edge_length > kVectorZeroEpsilon ? nominal_edge_length * 3.0 : 5.0;
        if (seam_stats.max_min_distance <= seam_limit)
        {
            return;
        }

        PyObject *break_item = PyDict_New();
        if (!break_item)
        {
            return;
        }
        PyObject *from_face = PyLong_FromLong(-1);
        PyObject *to_face = PyLong_FromLong(-1);
        if (from_face && to_face)
        {
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
            seam_limit);
        PyObject *reason = PyUnicode_FromString(reason_buf);
        if (reason)
        {
            PyDict_SetItemString(break_item, "reason", reason);
            Py_DECREF(reason);
        }
        PyList_Append(orientation_breaks_list, break_item);
        Py_DECREF(break_item);
    }

    static bool append_first_face_frame(
        PyObject *face_frames_list,
        const std::vector<FaceSample> &samples,
        const std::vector<int> &face_indices)
    {
        if (!face_frames_list || samples.empty() || face_indices.empty())
        {
            return true;
        }

        PyObject *frame = build_face_frame_dict(samples.front(), face_indices.front(), true, -1);
        if (!frame)
        {
            return false;
        }
        int append_ok = PyList_Append(face_frames_list, frame);
        Py_DECREF(frame);
        return append_ok == 0;
    }

    static bool append_atlas_charts_and_overlap_break(
        PyObject *atlas_charts_list,
        PyObject *orientation_breaks_list,
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::vector<int>> &quads,
        const std::vector<std::vector<int>> &mesh_face_vec)
    {
        if (!atlas_charts_list || !orientation_breaks_list)
        {
            return false;
        }

        std::vector<std::vector<int>> chart_quads_vec = quads;
        if (chart_quads_vec.empty())
        {
            chart_quads_vec = mesh_face_vec;
        }

        int overlap_rejections = 0;
        std::vector<AtlasChartBuild> charts = split_into_non_overlapping_charts(fabric_points, chart_quads_vec, overlap_rejections);
        double x_offset = 0.0;
        for (size_t chart_i = 0; chart_i < charts.size(); ++chart_i)
        {
            PyObject *chart = PyDict_New();
            if (!chart)
            {
                return false;
            }

            std::vector<Vec3> shifted_points = charts[chart_i].points;
            for (auto &p : shifted_points)
            {
                p.x += x_offset;
            }

            PyObject *chart_index_obj = PyLong_FromLong(static_cast<long>(chart_i));
            PyObject *chart_points = build_vec3_list(shifted_points);
            PyObject *chart_quads = build_quad_list(charts[chart_i].quads);
            PyObject *bounds_list = PyList_New(4);
            if (!chart_index_obj || !chart_points || !chart_quads || !bounds_list)
            {
                Py_XDECREF(chart_index_obj);
                Py_XDECREF(chart_points);
                Py_XDECREF(chart_quads);
                Py_XDECREF(bounds_list);
                Py_DECREF(chart);
                return false;
            }

            double min_x = shifted_points.empty() ? 0.0 : shifted_points.front().x;
            double max_x = shifted_points.empty() ? 0.0 : shifted_points.front().x;
            double min_y = shifted_points.empty() ? 0.0 : shifted_points.front().y;
            double max_y = shifted_points.empty() ? 0.0 : shifted_points.front().y;
            for (const auto &p : shifted_points)
            {
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

        if (overlap_rejections > 0)
        {
            PyObject *break_item = PyDict_New();
            if (break_item)
            {
                PyObject *from_face = PyLong_FromLong(-1);
                PyObject *to_face = PyLong_FromLong(-1);
                if (from_face && to_face)
                {
                    PyDict_SetItemString(break_item, "from_face", from_face);
                    PyDict_SetItemString(break_item, "to_face", to_face);
                }
                Py_XDECREF(from_face);
                Py_XDECREF(to_face);
                PyObject *reason = PyUnicode_FromFormat(
                    "atlas overlap split: %d overlapping placements moved to new charts",
                    overlap_rejections);
                if (reason)
                {
                    PyDict_SetItemString(break_item, "reason", reason);
                    Py_DECREF(reason);
                }
                PyList_Append(orientation_breaks_list, break_item);
                Py_DECREF(break_item);
            }
        }

        return true;
    }

    struct WarpWeftBuildInput
    {
        const std::vector<Vec3> &points;
        const std::vector<Vec3> &local_points;
        const std::vector<Vec3> &layout_points;
        const std::vector<std::vector<int>> &loops_idx;
        double nominal_edge_length;
    };

    struct WarpWeftBuildOutput
    {
        PyObject *&warp_weft_points_list;
        PyObject *&warp_weft_boundary_loops_list;
    };

    static bool build_warp_weft_outputs(
        const WarpWeftBuildInput &input,
        const WarpWeftBuildOutput &output)
    {
        std::vector<Vec3> warp_weft_points;
        warp_weft_points.reserve(input.points.size());
        for (size_t pi = 0; pi < input.points.size(); ++pi)
        {
            Vec3 seed = input.local_points[pi];
            seed.z = 0.0;
            if (input.nominal_edge_length > kVectorZeroEpsilon && pi < input.layout_points.size())
            {
                seed = {input.layout_points[pi].x * input.nominal_edge_length, input.layout_points[pi].y * input.nominal_edge_length, 0.0};
            }
            else if (pi < input.layout_points.size())
            {
                seed = {input.layout_points[pi].x, input.layout_points[pi].y, 0.0};
            }
            warp_weft_points.push_back(seed);
        }

        output.warp_weft_points_list = build_vec3_list(warp_weft_points);
        std::vector<std::vector<Vec3>> warp_weft_loops_pts;
        warp_weft_loops_pts.reserve(input.loops_idx.size());
        for (const auto &loop : input.loops_idx)
        {
            warp_weft_loops_pts.push_back(loop_to_points(loop, warp_weft_points));
        }
        output.warp_weft_boundary_loops_list = build_loop_list(warp_weft_loops_pts);
        return output.warp_weft_points_list && output.warp_weft_boundary_loops_list;
    }

    static std::vector<std::vector<int>> triangles_to_mesh_face_vec(
        const std::vector<std::array<int, 3>> &triangles)
    {
        std::vector<std::vector<int>> mesh_face_vec;
        mesh_face_vec.reserve(triangles.size());
        for (const auto &face : triangles)
        {
            mesh_face_vec.push_back({face[0], face[1], face[2]});
        }
        return mesh_face_vec;
    }

    static bool append_origin_face_frame(
        PyObject *face_frames_list,
        const Vec3 &origin,
        const Vec3 &normal,
        const Vec3 &x_axis,
        const Vec3 &y_axis)
    {
        if (!face_frames_list)
        {
            return false;
        }

        PyObject *frame = PyDict_New();
        if (!frame)
        {
            Py_DECREF(face_frames_list);
            return false;
        }
        PyObject *face_index = PyLong_FromLong(0);
        PyObject *origin_obj = build_vec3_tuple(origin);
        PyObject *normal_obj = build_vec3_tuple(normal);
        PyObject *x_axis_obj = build_vec3_tuple(x_axis);
        PyObject *y_axis_obj = build_vec3_tuple(y_axis);
        if (face_index && origin_obj && normal_obj && x_axis_obj && y_axis_obj)
        {
            PyDict_SetItemString(frame, "face_index", face_index);
            PyDict_SetItemString(frame, "origin", origin_obj);
            PyDict_SetItemString(frame, "normal", normal_obj);
            PyDict_SetItemString(frame, "x_axis", x_axis_obj);
            PyDict_SetItemString(frame, "y_axis", y_axis_obj);
            PyDict_SetItemString(frame, "continuous", Py_True);
            PyList_SET_ITEM(face_frames_list, 0, frame);
        }
        else
        {
            Py_DECREF(frame);
            Py_DECREF(face_frames_list);
            face_frames_list = nullptr;
        }
        Py_XDECREF(face_index);
        Py_XDECREF(origin_obj);
        Py_XDECREF(normal_obj);
        Py_XDECREF(x_axis_obj);
        Py_XDECREF(y_axis_obj);
        return face_frames_list != nullptr;
    }

    static void decref_result_build_objects(
        PyObject *fabric_points_list,
        PyObject *fabric_quads_list,
        PyObject *boundary_loops_list,
        PyObject *strains_list,
        PyObject *mesh_points_list,
        PyObject *mesh_faces_list,
        PyObject *face_frames_list,
        PyObject *orientation_breaks_list,
        PyObject *atlas_charts_list,
        PyObject *warp_weft_points_list,
        PyObject *warp_weft_boundary_loops_list)
    {
        Py_XDECREF(fabric_points_list);
        Py_XDECREF(fabric_quads_list);
        Py_XDECREF(boundary_loops_list);
        Py_XDECREF(strains_list);
        Py_XDECREF(mesh_points_list);
        Py_XDECREF(mesh_faces_list);
        Py_XDECREF(face_frames_list);
        Py_XDECREF(orientation_breaks_list);
        Py_XDECREF(atlas_charts_list);
        Py_XDECREF(warp_weft_points_list);
        Py_XDECREF(warp_weft_boundary_loops_list);
    }

    class ResultBuildScope
    {
    public:
        explicit ResultBuildScope(PyObject *params_copy)
            : params_copy_(params_copy)
        {
        }

        ResultBuildScope(const ResultBuildScope &) = delete;
        ResultBuildScope &operator=(const ResultBuildScope &) = delete;

        ~ResultBuildScope()
        {
            decref_result_build_objects(
                fabric_points_list_,
                fabric_quads_list_,
                boundary_loops_list_,
                strains_list_,
                mesh_points_list_,
                mesh_faces_list_,
                face_frames_list_,
                orientation_breaks_list_,
                atlas_charts_list_,
                warp_weft_points_list_,
                warp_weft_boundary_loops_list_);
            Py_XDECREF(params_copy_);
        }

        PyObject *params_copy() const
        {
            return params_copy_;
        }

        PyObject *&fabric_points_list()
        {
            return fabric_points_list_;
        }

        PyObject *&fabric_quads_list()
        {
            return fabric_quads_list_;
        }

        PyObject *&boundary_loops_list()
        {
            return boundary_loops_list_;
        }

        PyObject *&strains_list()
        {
            return strains_list_;
        }

        PyObject *&mesh_points_list()
        {
            return mesh_points_list_;
        }

        PyObject *&mesh_faces_list()
        {
            return mesh_faces_list_;
        }

        PyObject *&face_frames_list()
        {
            return face_frames_list_;
        }

        PyObject *&orientation_breaks_list()
        {
            return orientation_breaks_list_;
        }

        PyObject *&atlas_charts_list()
        {
            return atlas_charts_list_;
        }

        PyObject *&warp_weft_points_list()
        {
            return warp_weft_points_list_;
        }

        PyObject *&warp_weft_boundary_loops_list()
        {
            return warp_weft_boundary_loops_list_;
        }

    private:
        PyObject *params_copy_ = nullptr;
        PyObject *fabric_points_list_ = nullptr;
        PyObject *fabric_quads_list_ = nullptr;
        PyObject *boundary_loops_list_ = nullptr;
        PyObject *strains_list_ = nullptr;
        PyObject *mesh_points_list_ = nullptr;
        PyObject *mesh_faces_list_ = nullptr;
        PyObject *face_frames_list_ = nullptr;
        PyObject *orientation_breaks_list_ = nullptr;
        PyObject *atlas_charts_list_ = nullptr;
        PyObject *warp_weft_points_list_ = nullptr;
        PyObject *warp_weft_boundary_loops_list_ = nullptr;
    };

    struct GeometryPythonListsInput
    {
        const std::vector<Vec3> &fabric_points;
        const std::vector<std::vector<int>> &quads;
        const std::vector<std::vector<Vec3>> &loops_pts;
        const std::vector<std::array<double, 3>> &strains;
        const std::vector<Vec3> &points;
        const std::vector<std::array<int, 3>> &triangles;
    };

    struct GeometryPythonListsOutput
    {
        PyObject *&fabric_points_list;
        PyObject *&fabric_quads_list;
        PyObject *&boundary_loops_list;
        PyObject *&strains_list;
        PyObject *&mesh_points_list;
        PyObject *&mesh_faces_list;
        PyObject *&face_frames_list;
        PyObject *&orientation_breaks_list;
        PyObject *&atlas_charts_list;
        std::vector<std::vector<int>> &mesh_face_vec;
    };

    static bool build_geometry_python_lists(
        const GeometryPythonListsInput &input,
        const GeometryPythonListsOutput &output)
    {
        output.fabric_points_list = build_vec3_list(input.fabric_points);
        output.fabric_quads_list = build_quad_list(input.quads);
        output.boundary_loops_list = build_loop_list(input.loops_pts);
        output.strains_list = build_strain_list(input.strains);
        output.mesh_points_list = build_vec3_list(input.points);
        output.mesh_face_vec = triangles_to_mesh_face_vec(input.triangles);
        output.mesh_faces_list = build_quad_list(output.mesh_face_vec);

        if (!output.fabric_points_list || !output.fabric_quads_list || !output.boundary_loops_list ||
            !output.strains_list || !output.mesh_points_list || !output.mesh_faces_list)
        {
            return false;
        }

        output.face_frames_list = PyList_New(0);
        output.orientation_breaks_list = PyList_New(0);
        output.atlas_charts_list = PyList_New(0);
        if (!output.face_frames_list || !output.orientation_breaks_list || !output.atlas_charts_list)
        {
            return false;
        }

        return true;
    }

    struct MeshPythonListsInput
    {
        const std::vector<Vec3> &points;
        const std::vector<std::array<int, 3>> &faces;
        const std::vector<Vec3> &fabric_points;
        const std::vector<std::vector<int>> &fabric_quads;
        const std::vector<std::vector<Vec3>> &loops_pts;
        const std::vector<std::array<double, 3>> &strains;
        const Vec3 &origin;
        const Vec3 &normal;
        const Vec3 &x_axis;
        const Vec3 &y_axis;
    };

    struct MeshPythonListsOutput
    {
        PyObject *&fabric_points_list;
        PyObject *&fabric_quads_list;
        PyObject *&boundary_loops_list;
        PyObject *&strains_list;
        PyObject *&mesh_points_list;
        PyObject *&mesh_faces_list;
        PyObject *&face_frames_list;
        PyObject *&orientation_breaks_list;
        PyObject *&atlas_charts_list;
    };

    static bool build_mesh_python_lists(
        const MeshPythonListsInput &input,
        const MeshPythonListsOutput &output)
    {
        output.fabric_points_list = build_vec3_list(input.fabric_points);
        output.fabric_quads_list = build_quad_list(input.fabric_quads);
        output.boundary_loops_list = build_loop_list(input.loops_pts);
        output.strains_list = build_strain_list(input.strains);
        output.mesh_points_list = build_vec3_list(input.points);

        std::vector<std::vector<int>> mesh_face_vec = triangles_to_mesh_face_vec(input.faces);
        output.mesh_faces_list = build_quad_list(mesh_face_vec);
        output.face_frames_list = PyList_New(1);
        output.orientation_breaks_list = PyList_New(0);
        output.atlas_charts_list = PyList_New(0);

        if (output.face_frames_list &&
            !append_origin_face_frame(output.face_frames_list, input.origin, input.normal, input.x_axis, input.y_axis))
        {
            output.face_frames_list = nullptr;
        }

        if (!output.fabric_points_list || !output.fabric_quads_list || !output.boundary_loops_list || !output.strains_list ||
            !output.mesh_points_list || !output.mesh_faces_list || !output.face_frames_list ||
            !output.orientation_breaks_list || !output.atlas_charts_list)
        {
            return false;
        }

        return true;
    }

    struct EdgeDiagnosticsContext
    {
        double rel_tol = 0.0;
        bool rel_tol_from_parameter = false;
        int edge_violations = 0;
        double max_rel_error = 0.0;
    };

    struct EdgeDiagnosticsBreakInput
    {
        PyObject *params_copy;
        PyObject *orientation_breaks_list;
        bool acp_energy_mode;
        const std::vector<Vec3> &fabric_points;
        const std::vector<std::pair<int, int>> &constrained_edges;
        const std::vector<double> &edge_targets;
        double nominal_edge_length;
    };

    static EdgeDiagnosticsContext append_edge_diagnostics_break(
        const EdgeDiagnosticsBreakInput &input)
    {
        EdgeDiagnosticsContext edge_context;
        auto [rel_tol, rel_tol_from_parameter] = resolve_edge_rel_tolerance(input.params_copy);
        auto [edge_violations, max_rel_error] = summarize_edge_violations(
            input.acp_energy_mode,
            input.fabric_points,
            input.constrained_edges,
            input.edge_targets,
            input.nominal_edge_length,
            rel_tol);
        append_edge_violation_break(
            input.orientation_breaks_list,
            input.acp_energy_mode,
            edge_violations,
            max_rel_error,
            rel_tol);

        edge_context.rel_tol = rel_tol;
        edge_context.rel_tol_from_parameter = rel_tol_from_parameter;
        edge_context.edge_violations = edge_violations;
        edge_context.max_rel_error = max_rel_error;
        return edge_context;
    }

    struct GeometryDiagnosticsInput
    {
        PyObject *params_copy;
        bool acp_energy_mode;
        const ExperimentalSolveStats &experimental_stats;
        const std::vector<FaceSample> &samples;
        const std::vector<int> &face_indices;
        const std::vector<Vec3> &points;
        const std::vector<Vec3> &fabric_points;
        double nominal_edge_length;
        const std::vector<std::pair<int, int>> &constrained_edges;
        const std::vector<double> &edge_targets;
        const std::vector<std::vector<int>> &quads;
        const std::vector<std::vector<int>> &mesh_face_vec;
        PyObject *face_frames_list;
        PyObject *orientation_breaks_list;
        PyObject *atlas_charts_list;
    };

    static bool populate_geometry_diagnostics_lists(
        const GeometryDiagnosticsInput &input,
        EdgeDiagnosticsContext &edge_context)
    {
        const EdgeDiagnosticsBreakInput edge_input{
            input.params_copy,
            input.orientation_breaks_list,
            input.acp_energy_mode,
            input.fabric_points,
            input.constrained_edges,
            input.edge_targets,
            input.nominal_edge_length,
        };
        edge_context = append_edge_diagnostics_break(edge_input);

        append_experimental_diagnostics_break(
            input.orientation_breaks_list,
            input.experimental_stats);
        append_seam_continuity_break(
            input.orientation_breaks_list,
            input.points,
            input.fabric_points,
            input.nominal_edge_length);

        if (!append_first_face_frame(input.face_frames_list, input.samples, input.face_indices) ||
            !append_atlas_charts_and_overlap_break(
                input.atlas_charts_list,
                input.orientation_breaks_list,
                input.fabric_points,
                input.quads,
                input.mesh_face_vec))
        {
            return false;
        }

        return true;
    }

    struct GeometryResultDictInput
    {
        const std::vector<Vec3> &points;
        const std::vector<Vec3> &local_points;
        const std::vector<Vec3> &layout_points;
        const std::vector<std::vector<int>> &loops_idx;
        double nominal_edge_length;
        PyObject *fabric_points_list;
        PyObject *fabric_quads_list;
        PyObject *boundary_loops_list;
        PyObject *strains_list;
        PyObject *mesh_points_list;
        PyObject *mesh_faces_list;
        PyObject *face_frames_list;
        PyObject *orientation_breaks_list;
        PyObject *atlas_charts_list;
        const Vec3 &origin;
        const Vec3 &normal;
        const Vec3 &x_axis;
        const Vec3 &y_axis;
        PyObject *params_copy;
        PyObject *&warp_weft_points_list;
        PyObject *&warp_weft_boundary_loops_list;
    };

    static PyObject *build_geometry_result_dict(const GeometryResultDictInput &input)
    {
        PyObject *result = PyDict_New();
        if (!result)
        {
            return nullptr;
        }

        const WarpWeftBuildInput warp_weft_input{
            input.points,
            input.local_points,
            input.layout_points,
            input.loops_idx,
            input.nominal_edge_length,
        };
        const WarpWeftBuildOutput warp_weft_output{
            input.warp_weft_points_list,
            input.warp_weft_boundary_loops_list,
        };
        if (!build_warp_weft_outputs(warp_weft_input, warp_weft_output))
        {
            Py_DECREF(result);
            return nullptr;
        }

        set_result_common_fields(
            result,
            input.fabric_points_list,
            input.warp_weft_points_list,
            input.fabric_quads_list,
            input.boundary_loops_list,
            input.warp_weft_boundary_loops_list,
            input.strains_list,
            input.mesh_points_list,
            input.mesh_faces_list,
            input.face_frames_list,
            input.orientation_breaks_list,
            input.atlas_charts_list,
            input.origin,
            input.normal,
            input.x_axis,
            input.y_axis,
            input.params_copy);
        return result;
    }

    struct GeometryResultDiagnosticsInput
    {
        const std::vector<FaceSample> &samples;
        const std::vector<Vec3> &points;
        const std::vector<std::array<int, 3>> &triangles;
        const std::vector<std::vector<int>> &quads;
        PyObject *orientation_breaks_list;
        const EdgeDiagnosticsContext &edge_context;
        int relax_iterations;
        const std::vector<double> &residual_history;
        const std::vector<double> &combined_objective_history;
        bool acp_energy_mode;
        const AcpPropagationSummary &acp_summary;
        const AcpObjectiveSummary &objective_summary;
    };

    static void attach_geometry_result_diagnostics(
        PyObject *result,
        PyObject *params_copy,
        const GeometryResultDiagnosticsInput &input)
    {
        long surface_spacing_active_nodes = 0;
        long surface_spacing_total_nodes = 0;
        long surface_spacing_frontier_pops = 0;
        long surface_spacing_frontier_accepts = 0;
        long surface_spacing_candidate_quads = 0;
        long surface_spacing_selected_quads = 0;
        long per_row_active_cols_min = 0;
        long per_row_active_cols_max = 0;
        double per_row_active_cols_mean = 0.0;
        accumulate_surface_spacing_stats(
            input.samples,
            surface_spacing_active_nodes,
            surface_spacing_total_nodes,
            surface_spacing_frontier_pops,
            surface_spacing_frontier_accepts,
            surface_spacing_candidate_quads,
            surface_spacing_selected_quads,
            per_row_active_cols_min,
            per_row_active_cols_max,
            per_row_active_cols_mean);
        const long coverage_point_count = coverage_point_count_for_quads(input.quads);

        const SolverDiagnosticsInput diagnostics_input{
            static_cast<long>(input.samples.size()),
            static_cast<long>(input.points.size()),
            static_cast<long>(input.triangles.size()),
            static_cast<long>(input.quads.size()),
            PyList_Size(input.orientation_breaks_list),
            input.edge_context.edge_violations,
            input.edge_context.max_rel_error,
            input.edge_context.rel_tol,
            input.edge_context.rel_tol_from_parameter,
            input.relax_iterations,
            input.residual_history,
            input.combined_objective_history,
            input.acp_energy_mode,
            input.acp_summary,
            input.objective_summary,
            coverage_point_count,
            surface_spacing_active_nodes,
            surface_spacing_total_nodes,
            surface_spacing_frontier_pops,
            surface_spacing_frontier_accepts,
            surface_spacing_candidate_quads,
            surface_spacing_selected_quads,
            per_row_active_cols_min,
            per_row_active_cols_max,
            per_row_active_cols_mean,
        };
        attach_result_diagnostics(result, params_copy, diagnostics_input);
    }

    PyObject *build_geometry_result_object(const GeometryResultBuildInput &input)
    {
        ResultBuildScope scope(input.params_copy);
        std::vector<std::vector<int>> mesh_face_vec;
        const GeometryPythonListsInput list_input{
            input.fabric_points,
            input.quads,
            input.loops_pts,
            input.strains,
            input.points,
            input.triangles,
        };
        const GeometryPythonListsOutput list_output{
            scope.fabric_points_list(),
            scope.fabric_quads_list(),
            scope.boundary_loops_list(),
            scope.strains_list(),
            scope.mesh_points_list(),
            scope.mesh_faces_list(),
            scope.face_frames_list(),
            scope.orientation_breaks_list(),
            scope.atlas_charts_list(),
            mesh_face_vec,
        };
        if (!build_geometry_python_lists(list_input, list_output))
        {
            return nullptr;
        }

        EdgeDiagnosticsContext edge_context;
        const GeometryDiagnosticsInput diagnostics_lists_input{
            scope.params_copy(),
            input.acp_energy_mode,
            input.experimental_stats,
            input.samples,
            input.face_indices,
            input.points,
            input.fabric_points,
            input.nominal_edge_length,
            input.constrained_edges,
            input.edge_targets,
            input.quads,
            mesh_face_vec,
            scope.face_frames_list(),
            scope.orientation_breaks_list(),
            scope.atlas_charts_list(),
        };
        if (!populate_geometry_diagnostics_lists(diagnostics_lists_input, edge_context))
        {
            return nullptr;
        }

        const GeometryResultDictInput dict_input{
            input.points,
            input.local_points,
            input.layout_points,
            input.loops_idx,
            input.nominal_edge_length,
            scope.fabric_points_list(),
            scope.fabric_quads_list(),
            scope.boundary_loops_list(),
            scope.strains_list(),
            scope.mesh_points_list(),
            scope.mesh_faces_list(),
            scope.face_frames_list(),
            scope.orientation_breaks_list(),
            scope.atlas_charts_list(),
            input.origin,
            input.normal,
            input.x_axis,
            input.y_axis,
            scope.params_copy(),
            scope.warp_weft_points_list(),
            scope.warp_weft_boundary_loops_list(),
        };
        PyObject *result = build_geometry_result_dict(dict_input);
        if (!result)
        {
            return nullptr;
        }

        const GeometryResultDiagnosticsInput diagnostics_input{
            input.samples,
            input.points,
            input.triangles,
            input.quads,
            scope.orientation_breaks_list(),
            edge_context,
            input.relax_iterations,
            input.residual_history,
            input.combined_objective_history,
            input.acp_energy_mode,
            input.acp_summary,
            input.objective_summary,
        };
        attach_geometry_result_diagnostics(result, scope.params_copy(), diagnostics_input);

        return result;
    }

    PyObject *build_mesh_result_object(const MeshResultBuildInput &input)
    {
        ResultBuildScope scope(input.params_copy);
        const MeshPythonListsInput list_input{
            input.points,
            input.faces,
            input.fabric_points,
            input.fabric_quads,
            input.loops_pts,
            input.strains,
            input.origin,
            input.normal,
            input.x_axis,
            input.y_axis,
        };
        const MeshPythonListsOutput list_output{
            scope.fabric_points_list(),
            scope.fabric_quads_list(),
            scope.boundary_loops_list(),
            scope.strains_list(),
            scope.mesh_points_list(),
            scope.mesh_faces_list(),
            scope.face_frames_list(),
            scope.orientation_breaks_list(),
            scope.atlas_charts_list(),
        };
        if (!build_mesh_python_lists(list_input, list_output))
        {
            return nullptr;
        }

        const EdgeDiagnosticsBreakInput edge_input{
            scope.params_copy(),
            scope.orientation_breaks_list(),
            input.acp_energy_mode,
            input.fabric_points,
            input.constrained_edges,
            input.edge_targets,
            input.nominal_edge_length,
        };
        EdgeDiagnosticsContext edge_context = append_edge_diagnostics_break(edge_input);

        PyObject *result = PyDict_New();
        if (!result)
        {
            return nullptr;
        }

        set_result_common_fields(
            result,
            scope.fabric_points_list(),
            scope.fabric_points_list(),
            scope.fabric_quads_list(),
            scope.boundary_loops_list(),
            scope.boundary_loops_list(),
            scope.strains_list(),
            scope.mesh_points_list(),
            scope.mesh_faces_list(),
            scope.face_frames_list(),
            scope.orientation_breaks_list(),
            scope.atlas_charts_list(),
            input.origin,
            input.normal,
            input.x_axis,
            input.y_axis,
            scope.params_copy());

        const long coverage_point_count = coverage_point_count_for_quads(input.fabric_quads);
        const SolverDiagnosticsInput diagnostics_input{
            -1,
            static_cast<long>(input.points.size()),
            static_cast<long>(input.faces.size()),
            static_cast<long>(input.fabric_quads.size()),
            PyList_Size(scope.orientation_breaks_list()),
            edge_context.edge_violations,
            edge_context.max_rel_error,
            edge_context.rel_tol,
            edge_context.rel_tol_from_parameter,
            input.relax_iterations,
            input.residual_history,
            input.combined_objective_history,
            input.acp_energy_mode,
            input.acp_summary,
            input.objective_summary,
            coverage_point_count,
            -1,
            -1,
            -1,
            -1,
            -1,
            -1,
            0,
            0,
            0.0,
        };
        attach_result_diagnostics(result, scope.params_copy(), diagnostics_input);

        return result;
    }

} // namespace fishnet_internal
