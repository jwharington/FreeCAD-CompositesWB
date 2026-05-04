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

#include "fishnet_algorithm_sections.hpp"
#include "fishnet_algorithm_types.hpp"
#include "fishnet_options.hpp"
#include "fishnet_python_geometry.hpp"
#include "fishnet_python_input.hpp"
#include "fishnet_python_parse.hpp"
#include "fishnet_python_util.hpp"

namespace fishnet_internal
{


    static void sample_geometry_faces(
        const std::vector<TopoDS_Face> &native_faces,
        const GeometrySolverConfig &config,
        std::vector<FaceSample> &samples,
        std::vector<int> &face_indices,
        std::vector<Vec3> &points,
        std::vector<Vec3> &layout_points,
        std::vector<std::array<int, 3>> &triangles,
        std::vector<std::vector<int>> &quads,
        ExperimentalSolveStats &experimental_stats)
    {
        samples.clear();
        face_indices.clear();
        points.clear();
        layout_points.clear();
        triangles.clear();
        quads.clear();

        for (size_t i = 0; i < native_faces.size(); ++i)
        {
            FaceSample sample = sample_face(
                native_faces[i],
                config.sample_max_length,
                config.solver_mode,
                config.max_adjacent_normal_angle,
                config.max_local_fold_ratio,
                config.max_shear_angle,
                config.incremental_growth,
                config.surface_spacing_refine,
                config.surface_spacing_relax_iterations,
                (config.solver_mode == CurrentNodeSolverMode::SphereSurfaceExperimental) ? &experimental_stats : nullptr);
            if (sample.points.empty() || sample.triangles.empty())
            {
                continue;
            }

            if (!samples.empty() && !sample.layout_points.empty())
            {
                transfer_layout_between_faces(samples.back(), sample);
            }

            int offset = static_cast<int>(points.size());
            points.insert(points.end(), sample.points.begin(), sample.points.end());
            layout_points.insert(layout_points.end(), sample.layout_points.begin(), sample.layout_points.end());
            for (const auto &tri : sample.triangles)
            {
                triangles.push_back({tri[0] + offset, tri[1] + offset, tri[2] + offset});
            }
            for (const auto &quad : sample.quads)
            {
                quads.push_back({quad[0] + offset, quad[1] + offset, quad[2] + offset, quad[3] + offset});
            }
            face_indices.push_back(static_cast<int>(i));
            samples.push_back(std::move(sample));
        }
    }

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

    static long coverage_point_count_for_quads(const std::vector<std::vector<int>> &quad_list)
    {
        std::unordered_set<int> covered;
        for (const auto &q : quad_list)
        {
            for (int idx : q)
            {
                if (idx >= 0)
                {
                    covered.insert(idx);
                }
            }
        }
        return static_cast<long>(covered.size());
    }

    static void append_experimental_diagnostics_break(
        PyObject *orientation_breaks_list,
        CurrentNodeSolverMode solver_mode,
        const ExperimentalSolveStats &experimental_stats)
    {
        if (!orientation_breaks_list ||
            solver_mode != CurrentNodeSolverMode::SphereSurfaceExperimental ||
            experimental_stats.calls <= 0)
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

    static std::pair<PyObject *, PyObject *> build_warp_weft_outputs(
        const std::vector<Vec3> &points,
        const std::vector<Vec3> &local_points,
        const std::vector<Vec3> &layout_points,
        const std::vector<std::vector<int>> &loops_idx,
        double nominal_edge_length)
    {
        std::vector<Vec3> warp_weft_points;
        warp_weft_points.reserve(points.size());
        for (size_t pi = 0; pi < points.size(); ++pi)
        {
            Vec3 seed = local_points[pi];
            seed.z = 0.0;
            if (nominal_edge_length > kVectorZeroEpsilon && pi < layout_points.size())
            {
                seed = {layout_points[pi].x * nominal_edge_length, layout_points[pi].y * nominal_edge_length, 0.0};
            }
            else if (pi < layout_points.size())
            {
                seed = {layout_points[pi].x, layout_points[pi].y, 0.0};
            }
            warp_weft_points.push_back(seed);
        }

        PyObject *warp_weft_points_list = build_vec3_list(warp_weft_points);
        std::vector<std::vector<Vec3>> warp_weft_loops_pts;
        warp_weft_loops_pts.reserve(loops_idx.size());
        for (const auto &loop : loops_idx)
        {
            warp_weft_loops_pts.push_back(loop_to_points(loop, warp_weft_points));
        }
        PyObject *warp_weft_boundary_loops_list = build_loop_list(warp_weft_loops_pts);
        return {warp_weft_points_list, warp_weft_boundary_loops_list};
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

    static void accumulate_surface_spacing_stats(
        const std::vector<FaceSample> &samples,
        long &surface_spacing_active_nodes,
        long &surface_spacing_total_nodes,
        long &surface_spacing_frontier_pops,
        long &surface_spacing_frontier_accepts,
        long &surface_spacing_candidate_quads,
        long &surface_spacing_selected_quads)
    {
        surface_spacing_active_nodes = 0;
        surface_spacing_total_nodes = 0;
        surface_spacing_frontier_pops = 0;
        surface_spacing_frontier_accepts = 0;
        surface_spacing_candidate_quads = 0;
        surface_spacing_selected_quads = 0;
        for (const auto &sample : samples)
        {
            surface_spacing_active_nodes += sample.surface_spacing_active_nodes;
            surface_spacing_total_nodes += sample.surface_spacing_total_nodes;
            surface_spacing_frontier_pops += sample.surface_spacing_frontier_pops;
            surface_spacing_frontier_accepts += sample.surface_spacing_frontier_accepts;
            surface_spacing_candidate_quads += sample.surface_spacing_candidate_quads;
            surface_spacing_selected_quads += sample.surface_spacing_selected_quads;
        }
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

    struct SolverDiagnosticsInput
    {
        long sample_count;
        long point_count;
        long triangle_count;
        long quad_count;
        long orientation_break_count;
        int edge_violations;
        double max_rel_error;
        double rel_tol;
        bool rel_tol_from_parameter;
        int max_iterations;
        const std::vector<double> &residual_history;
        bool acp_energy_mode;
        const AcpPropagationSummary &acp_summary;
        long coverage_point_count;
        long surface_spacing_active_nodes;
        long surface_spacing_total_nodes;
        long surface_spacing_frontier_pops;
        long surface_spacing_frontier_accepts;
        long surface_spacing_candidate_quads;
        long surface_spacing_selected_quads;
    };

    static void attach_result_diagnostics(
        PyObject *result,
        PyObject *params_copy,
        const SolverDiagnosticsInput &input)
    {
        const bool converged = !(input.acp_energy_mode && input.edge_violations > 0);
        const char *termination_reason = converged ? "converged" : "max_iterations";

        PyObject *diagnostics = PyDict_New();
        if (diagnostics)
        {
            add_solver_diagnostics(
                diagnostics,
                params_copy,
                input.sample_count,
                input.point_count,
                input.triangle_count,
                input.quad_count,
                input.orientation_break_count,
                input.edge_violations,
                input.max_rel_error,
                input.rel_tol,
                input.rel_tol_from_parameter,
                input.max_iterations,
                input.residual_history,
                input.acp_energy_mode,
                input.acp_summary,
                input.coverage_point_count,
                input.surface_spacing_active_nodes,
                input.surface_spacing_total_nodes,
                input.surface_spacing_frontier_pops,
                input.surface_spacing_frontier_accepts,
                input.surface_spacing_candidate_quads,
                input.surface_spacing_selected_quads);
            attach_solver_metadata(result, params_copy, termination_reason, converged, diagnostics);
            Py_DECREF(diagnostics);
            return;
        }

        attach_solver_metadata(result, params_copy, termination_reason, converged, nullptr);
    }

    static bool build_geometry_python_lists(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::vector<int>> &quads,
        const std::vector<std::vector<Vec3>> &loops_pts,
        const std::vector<std::array<double, 3>> &strains,
        const std::vector<Vec3> &points,
        const std::vector<std::array<int, 3>> &triangles,
        PyObject *&fabric_points_list,
        PyObject *&fabric_quads_list,
        PyObject *&boundary_loops_list,
        PyObject *&strains_list,
        PyObject *&mesh_points_list,
        PyObject *&mesh_faces_list,
        PyObject *&face_frames_list,
        PyObject *&orientation_breaks_list,
        PyObject *&atlas_charts_list,
        std::vector<std::vector<int>> &mesh_face_vec)
    {
        fabric_points_list = build_vec3_list(fabric_points);
        fabric_quads_list = build_quad_list(quads);
        boundary_loops_list = build_loop_list(loops_pts);
        strains_list = build_strain_list(strains);
        mesh_points_list = build_vec3_list(points);
        mesh_face_vec = triangles_to_mesh_face_vec(triangles);
        mesh_faces_list = build_quad_list(mesh_face_vec);

        if (!fabric_points_list || !fabric_quads_list || !boundary_loops_list ||
            !strains_list || !mesh_points_list || !mesh_faces_list)
        {
            return false;
        }

        face_frames_list = PyList_New(0);
        orientation_breaks_list = PyList_New(0);
        atlas_charts_list = PyList_New(0);
        if (!face_frames_list || !orientation_breaks_list || !atlas_charts_list)
        {
            return false;
        }

        return true;
    }

    static bool build_mesh_python_lists(
        const std::vector<Vec3> &points,
        const std::vector<std::array<int, 3>> &faces,
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::vector<int>> &fabric_quads,
        const std::vector<std::vector<Vec3>> &loops_pts,
        const std::vector<std::array<double, 3>> &strains,
        const Vec3 &origin,
        const Vec3 &normal,
        const Vec3 &x_axis,
        const Vec3 &y_axis,
        PyObject *&fabric_points_list,
        PyObject *&fabric_quads_list,
        PyObject *&boundary_loops_list,
        PyObject *&strains_list,
        PyObject *&mesh_points_list,
        PyObject *&mesh_faces_list,
        PyObject *&face_frames_list,
        PyObject *&orientation_breaks_list,
        PyObject *&atlas_charts_list)
    {
        fabric_points_list = build_vec3_list(fabric_points);
        fabric_quads_list = build_quad_list(fabric_quads);
        boundary_loops_list = build_loop_list(loops_pts);
        strains_list = build_strain_list(strains);
        mesh_points_list = build_vec3_list(points);

        std::vector<std::vector<int>> mesh_face_vec = triangles_to_mesh_face_vec(faces);
        mesh_faces_list = build_quad_list(mesh_face_vec);
        face_frames_list = PyList_New(1);
        orientation_breaks_list = PyList_New(0);
        atlas_charts_list = PyList_New(0);

        if (face_frames_list && !append_origin_face_frame(face_frames_list, origin, normal, x_axis, y_axis))
        {
            face_frames_list = nullptr;
        }

        if (!fabric_points_list || !fabric_quads_list || !boundary_loops_list || !strains_list ||
            !mesh_points_list || !mesh_faces_list || !face_frames_list ||
            !orientation_breaks_list || !atlas_charts_list)
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

    static EdgeDiagnosticsContext append_edge_diagnostics_break(
        PyObject *params_copy,
        PyObject *orientation_breaks_list,
        bool acp_energy_mode,
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &constrained_edges,
        const std::vector<double> &edge_targets,
        double nominal_edge_length)
    {
        EdgeDiagnosticsContext edge_context;
        auto [rel_tol, rel_tol_from_parameter] = resolve_edge_rel_tolerance(params_copy);
        auto [edge_violations, max_rel_error] = summarize_edge_violations(
            acp_energy_mode,
            fabric_points,
            constrained_edges,
            edge_targets,
            nominal_edge_length,
            rel_tol);
        append_edge_violation_break(
            orientation_breaks_list,
            acp_energy_mode,
            edge_violations,
            max_rel_error,
            rel_tol);

        edge_context.rel_tol = rel_tol;
        edge_context.rel_tol_from_parameter = rel_tol_from_parameter;
        edge_context.edge_violations = edge_violations;
        edge_context.max_rel_error = max_rel_error;
        return edge_context;
    }

    static bool populate_geometry_diagnostics_lists(
        PyObject *params_copy,
        bool acp_energy_mode,
        CurrentNodeSolverMode solver_mode,
        const ExperimentalSolveStats &experimental_stats,
        const std::vector<FaceSample> &samples,
        const std::vector<int> &face_indices,
        const std::vector<Vec3> &points,
        const std::vector<Vec3> &fabric_points,
        double nominal_edge_length,
        const std::vector<std::pair<int, int>> &constrained_edges,
        const std::vector<double> &edge_targets,
        const std::vector<std::vector<int>> &quads,
        const std::vector<std::vector<int>> &mesh_face_vec,
        PyObject *face_frames_list,
        PyObject *orientation_breaks_list,
        PyObject *atlas_charts_list,
        EdgeDiagnosticsContext &edge_context)
    {
        edge_context = append_edge_diagnostics_break(
            params_copy,
            orientation_breaks_list,
            acp_energy_mode,
            fabric_points,
            constrained_edges,
            edge_targets,
            nominal_edge_length);

        append_experimental_diagnostics_break(
            orientation_breaks_list,
            solver_mode,
            experimental_stats);
        append_seam_continuity_break(
            orientation_breaks_list,
            points,
            fabric_points,
            nominal_edge_length);

        if (!append_first_face_frame(face_frames_list, samples, face_indices) ||
            !append_atlas_charts_and_overlap_break(
                atlas_charts_list,
                orientation_breaks_list,
                fabric_points,
                quads,
                mesh_face_vec))
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

        auto [new_warp_weft_points_list, new_warp_weft_boundary_loops_list] = build_warp_weft_outputs(
            input.points,
            input.local_points,
            input.layout_points,
            input.loops_idx,
            input.nominal_edge_length);
        input.warp_weft_points_list = new_warp_weft_points_list;
        input.warp_weft_boundary_loops_list = new_warp_weft_boundary_loops_list;
        if (!input.warp_weft_points_list || !input.warp_weft_boundary_loops_list)
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
        bool acp_energy_mode;
        const AcpPropagationSummary &acp_summary;
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
        accumulate_surface_spacing_stats(
            input.samples,
            surface_spacing_active_nodes,
            surface_spacing_total_nodes,
            surface_spacing_frontier_pops,
            surface_spacing_frontier_accepts,
            surface_spacing_candidate_quads,
            surface_spacing_selected_quads);
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
            input.acp_energy_mode,
            input.acp_summary,
            coverage_point_count,
            surface_spacing_active_nodes,
            surface_spacing_total_nodes,
            surface_spacing_frontier_pops,
            surface_spacing_frontier_accepts,
            surface_spacing_candidate_quads,
            surface_spacing_selected_quads,
        };
        attach_result_diagnostics(result, params_copy, diagnostics_input);
    }

    struct GeometryResultBuildInput
    {
        PyObject *params_copy;
        bool acp_energy_mode;
        CurrentNodeSolverMode solver_mode;
        const ExperimentalSolveStats &experimental_stats;
        const std::vector<FaceSample> &samples;
        const std::vector<int> &face_indices;
        const std::vector<Vec3> &points;
        const std::vector<Vec3> &layout_points;
        const std::vector<std::array<int, 3>> &triangles;
        const std::vector<std::vector<int>> &quads;
        const std::vector<Vec3> &local_points;
        const std::vector<Vec3> &fabric_points;
        const std::vector<std::vector<int>> &loops_idx;
        const std::vector<std::vector<Vec3>> &loops_pts;
        const std::vector<std::array<double, 3>> &strains;
        const Vec3 &origin;
        const Vec3 &normal;
        const Vec3 &x_axis;
        const Vec3 &y_axis;
        double nominal_edge_length;
        int relax_iterations;
        const std::vector<double> &residual_history;
        const AcpPropagationSummary &acp_summary;
        const std::vector<std::pair<int, int>> &constrained_edges;
        const std::vector<double> &edge_targets;
    };

    static PyObject *build_geometry_result_object(const GeometryResultBuildInput &input)
    {
        ResultBuildScope scope(input.params_copy);
        std::vector<std::vector<int>> mesh_face_vec;
        if (!build_geometry_python_lists(
                input.fabric_points,
                input.quads,
                input.loops_pts,
                input.strains,
                input.points,
                input.triangles,
                scope.fabric_points_list(),
                scope.fabric_quads_list(),
                scope.boundary_loops_list(),
                scope.strains_list(),
                scope.mesh_points_list(),
                scope.mesh_faces_list(),
                scope.face_frames_list(),
                scope.orientation_breaks_list(),
                scope.atlas_charts_list(),
                mesh_face_vec))
        {
            return nullptr;
        }

        EdgeDiagnosticsContext edge_context;
        if (!populate_geometry_diagnostics_lists(
                scope.params_copy(),
                input.acp_energy_mode,
                input.solver_mode,
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
                edge_context))
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
            input.acp_energy_mode,
            input.acp_summary,
        };
        attach_geometry_result_diagnostics(result, scope.params_copy(), diagnostics_input);

        return result;
    }

    class FabricLayoutSolverState
    {
    public:
        FabricLayoutSolverState(
            const std::vector<Vec3> &points,
            const Vec3 &origin,
            const Vec3 &normal,
            const Vec3 &x_axis,
            const Vec3 &y_axis,
            const std::vector<std::pair<int, int>> &constrained_edges,
            const std::vector<std::vector<int>> &loops_idx,
            double nominal_edge_length,
            int relax_iterations)
            : points_(points),
              origin_(origin),
              normal_(normal),
              x_axis_(x_axis),
              y_axis_(y_axis),
              constrained_edges_(constrained_edges),
              loops_idx_(loops_idx),
              nominal_edge_length_(nominal_edge_length),
              relax_iterations_(relax_iterations)
        {
        }

        void initialize_seed_points(const std::vector<Vec3> *layout_points)
        {
            local_points_.clear();
            fabric_points_.clear();
            local_points_.reserve(points_.size());
            fabric_points_.reserve(points_.size());

            for (size_t pi = 0; pi < points_.size(); ++pi)
            {
                const auto &point = points_[pi];
                Vec3 local = project_point(point, origin_, x_axis_, y_axis_, normal_);
                local_points_.push_back(local);

                Vec3 seed = {local.x, local.y, 0.0};
                if (layout_points && nominal_edge_length_ > kVectorZeroEpsilon && pi < layout_points->size())
                {
                    seed = {(*layout_points)[pi].x * nominal_edge_length_, (*layout_points)[pi].y * nominal_edge_length_, 0.0};
                }
                fabric_points_.push_back(seed);
            }
        }

        void configure_acp_if_enabled(
            bool acp_energy_mode,
            PyObject *params_copy,
            AcpPropagationSummary &acp_summary,
            std::vector<double> &edge_targets,
            std::vector<double> &edge_weights)
        {
            if (!acp_energy_mode)
            {
                return;
            }

            acp_summary = initialize_acp_layout(
                points_,
                local_points_,
                constrained_edges_,
                x_axis_,
                y_axis_,
                nominal_edge_length_,
                params_copy,
                fabric_points_);

            const std::string material_model = param_string(params_copy, "material_model", "woven");
            const double ud_coefficient = param_double(params_copy, "ud_coefficient", 0.0);
            const bool thickness_correction = param_bool(params_copy, "thickness_correction", false);
            build_acp_edge_objective(
                local_points_,
                constrained_edges_,
                nominal_edge_length_,
                acp_summary.primary_axis,
                material_model,
                ud_coefficient,
                thickness_correction,
                edge_targets,
                edge_weights);
        }

        void relax(
            bool acp_energy_mode,
            const std::vector<double> &edge_targets,
            const std::vector<double> &edge_weights)
        {
            residual_history_.clear();
            relax_fabric_points_with_edge_constraints(
                fabric_points_,
                constrained_edges_,
                loops_idx_,
                nominal_edge_length_,
                relax_iterations_,
                &residual_history_,
                acp_energy_mode ? &edge_targets : nullptr,
                acp_energy_mode ? &edge_weights : nullptr);
        }

        std::vector<std::vector<Vec3>> build_loop_points() const
        {
            std::vector<std::vector<Vec3>> loops_pts;
            loops_pts.reserve(loops_idx_.size());
            for (const auto &loop : loops_idx_)
            {
                loops_pts.push_back(loop_to_points(loop, fabric_points_));
            }
            return loops_pts;
        }

        const std::vector<Vec3> &local_points() const
        {
            return local_points_;
        }

        const std::vector<Vec3> &fabric_points() const
        {
            return fabric_points_;
        }

        const std::vector<double> &residual_history() const
        {
            return residual_history_;
        }

    private:
        const std::vector<Vec3> &points_;
        const Vec3 &origin_;
        const Vec3 &normal_;
        const Vec3 &x_axis_;
        const Vec3 &y_axis_;
        const std::vector<std::pair<int, int>> &constrained_edges_;
        const std::vector<std::vector<int>> &loops_idx_;
        double nominal_edge_length_ = 0.0;
        int relax_iterations_ = 0;

        std::vector<Vec3> local_points_;
        std::vector<Vec3> fabric_points_;
        std::vector<double> residual_history_;
    };

    static PyObject *copy_params_dict(PyObject *params_obj);

    enum class GeometrySolveInputStatus
    {
        Ok,
        EmptyGeometry,
        InvalidNativeGeometry,
        Error
    };

    class GeometrySolveInputContext
    {
    public:
        GeometrySolveInputContext() = default;
        GeometrySolveInputContext(const GeometrySolveInputContext &) = delete;
        GeometrySolveInputContext &operator=(const GeometrySolveInputContext &) = delete;

        ~GeometrySolveInputContext()
        {
            release_py_faces(py_faces_);
            Py_XDECREF(params_copy_);
        }

        GeometrySolveInputStatus prepare(PyObject *geometry_obj, PyObject *params_obj)
        {
            if (!prepare_params(params_obj))
            {
                return GeometrySolveInputStatus::Error;
            }

            GeometrySolveInputStatus face_status = collect_python_faces(geometry_obj);
            if (face_status != GeometrySolveInputStatus::Ok)
            {
                return face_status;
            }

            if (!extract_native_faces())
            {
                return GeometrySolveInputStatus::InvalidNativeGeometry;
            }

            build_config_and_sample();
            return GeometrySolveInputStatus::Ok;
        }

        bool has_sampled_geometry() const
        {
            return !points_.empty() && !triangles_.empty() && !samples_.empty();
        }

        PyObject *params_copy() const
        {
            return params_copy_;
        }

        PyObject *release_params_copy()
        {
            PyObject *released = params_copy_;
            params_copy_ = nullptr;
            return released;
        }

        const GeometrySolverConfig &config() const
        {
            return config_;
        }

        const ExperimentalSolveStats &experimental_stats() const
        {
            return experimental_stats_;
        }

        const std::vector<FaceSample> &samples() const
        {
            return samples_;
        }

        const std::vector<int> &face_indices() const
        {
            return face_indices_;
        }

        const std::vector<Vec3> &points() const
        {
            return points_;
        }

        const std::vector<Vec3> &layout_points() const
        {
            return layout_points_;
        }

        const std::vector<std::array<int, 3>> &triangles() const
        {
            return triangles_;
        }

        const std::vector<std::vector<int>> &quads() const
        {
            return quads_;
        }

    private:
        bool prepare_params(PyObject *params_obj)
        {
            params_copy_ = copy_params_dict(params_obj);
            return params_copy_ != nullptr;
        }

        GeometrySolveInputStatus collect_python_faces(PyObject *geometry_obj)
        {
            if (!collect_geometry_faces(geometry_obj, py_faces_))
            {
                return GeometrySolveInputStatus::EmptyGeometry;
            }
            return GeometrySolveInputStatus::Ok;
        }

        bool extract_native_faces()
        {
            return extract_native_faces_from_py(py_faces_, native_faces_);
        }

        void build_config_and_sample()
        {
            config_ = build_geometry_solver_config(params_copy_, native_faces_.size());
            sample_geometry_faces(
                native_faces_,
                config_,
                samples_,
                face_indices_,
                points_,
                layout_points_,
                triangles_,
                quads_,
                experimental_stats_);
        }

        PyObject *params_copy_ = nullptr;
        std::vector<PyObject *> py_faces_;
        std::vector<TopoDS_Face> native_faces_;
        GeometrySolverConfig config_;
        ExperimentalSolveStats experimental_stats_;
        std::vector<FaceSample> samples_;
        std::vector<int> face_indices_;
        std::vector<Vec3> points_;
        std::vector<Vec3> layout_points_;
        std::vector<std::array<int, 3>> triangles_;
        std::vector<std::vector<int>> quads_;
    };

    class GeometrySolveTopology
    {
    public:
        GeometrySolveTopology(
            const std::vector<std::array<int, 3>> &triangles,
            const std::vector<std::vector<int>> &quads,
            double nominal_spacing,
            PyObject *params_copy)
            : loops_idx_(boundary_loops(triangles)),
              constrained_edges_(!quads.empty()
                                     ? perimeter_edges_from_quads(quads)
                                     : edges_from_triangles(triangles)),
              nominal_edge_length_(nominal_spacing),
              relax_iterations_(resolve_relax_iterations(params_copy))
        {
        }

        const std::vector<std::vector<int>> &loops_idx() const
        {
            return loops_idx_;
        }

        const std::vector<std::pair<int, int>> &constrained_edges() const
        {
            return constrained_edges_;
        }

        double nominal_edge_length() const
        {
            return nominal_edge_length_;
        }

        int relax_iterations() const
        {
            return relax_iterations_;
        }

    private:
        std::vector<std::vector<int>> loops_idx_;
        std::vector<std::pair<int, int>> constrained_edges_;
        double nominal_edge_length_ = 0.0;
        int relax_iterations_ = 0;
    };

    static PyObject *solve_geometry(PyObject *geometry_obj, PyObject *params_obj)
    {
        ensure_part_module_loaded();

        GeometrySolveInputContext input;
        switch (input.prepare(geometry_obj, params_obj))
        {
        case GeometrySolveInputStatus::Error:
            return nullptr;
        case GeometrySolveInputStatus::EmptyGeometry:
            return build_empty_geometry_result("fishnet solver needs at least one face", input.release_params_copy());
        case GeometrySolveInputStatus::InvalidNativeGeometry:
            return build_empty_geometry_result("fishnet solver needs native Part.Face geometry", input.release_params_copy());
        case GeometrySolveInputStatus::Ok:
            break;
        }

        const DrapingAlgorithmPolicy algorithm_policy(input.params_copy());
        if (!algorithm_policy.supported())
        {
            return algorithm_policy.build_unsupported_result(input.release_params_copy());
        }

        if (!input.has_sampled_geometry())
        {
            return build_empty_geometry_result("fishnet solver needs at least one face", input.release_params_copy());
        }

        const GeometrySolverConfig &config = input.config();
        const bool acp_energy_mode = config.acp_energy_mode;
        const CurrentNodeSolverMode solver_mode = config.solver_mode;
        const double nominal_spacing = config.nominal_spacing;

        const std::vector<Vec3> &points = input.points();
        const std::vector<std::array<int, 3>> &triangles = input.triangles();

        Vec3 origin = centroid(points);
        Vec3 normal{}, x_axis{}, y_axis{};
        build_basis(points, triangles, normal, x_axis, y_axis);

        GeometrySolveTopology topology(
            triangles,
            input.quads(),
            nominal_spacing,
            input.params_copy());

        FabricLayoutSolverState layout_solver(
            points,
            origin,
            normal,
            x_axis,
            y_axis,
            topology.constrained_edges(),
            topology.loops_idx(),
            topology.nominal_edge_length(),
            topology.relax_iterations());
        layout_solver.initialize_seed_points(&input.layout_points());

        AcpPropagationSummary acp_summary;
        std::vector<double> edge_targets;
        std::vector<double> edge_weights;
        layout_solver.configure_acp_if_enabled(
            acp_energy_mode,
            input.params_copy(),
            acp_summary,
            edge_targets,
            edge_weights);

        layout_solver.relax(acp_energy_mode, edge_targets, edge_weights);

        std::vector<std::vector<Vec3>> loops_pts = layout_solver.build_loop_points();
        std::vector<std::array<double, 3>> strains = face_strains(triangles, layout_solver.local_points(), normal);

        const GeometryResultBuildInput result_input{
            input.release_params_copy(),
            acp_energy_mode,
            solver_mode,
            input.experimental_stats(),
            input.samples(),
            input.face_indices(),
            points,
            input.layout_points(),
            triangles,
            input.quads(),
            layout_solver.local_points(),
            layout_solver.fabric_points(),
            topology.loops_idx(),
            loops_pts,
            strains,
            origin,
            normal,
            x_axis,
            y_axis,
            topology.nominal_edge_length(),
            topology.relax_iterations(),
            layout_solver.residual_history(),
            acp_summary,
            topology.constrained_edges(),
            edge_targets,
        };
        return build_geometry_result_object(result_input);
    }

    static PyObject *copy_params_dict(PyObject *params_obj)
    {
        PyObject *params_copy = (!params_obj || params_obj == Py_None)
                                    ? PyDict_New()
                                    : PyDict_Copy(params_obj);
        if (!params_copy)
        {
            return nullptr;
        }
        if (!PyDict_Check(params_copy))
        {
            Py_DECREF(params_copy);
            PyErr_SetString(PyExc_TypeError, "parameters must be a dict or None");
            return nullptr;
        }
        return params_copy;
    }

    class MeshSolveInputContext
    {
    public:
        MeshSolveInputContext() = default;
        MeshSolveInputContext(const MeshSolveInputContext &) = delete;
        MeshSolveInputContext &operator=(const MeshSolveInputContext &) = delete;

        ~MeshSolveInputContext()
        {
            Py_XDECREF(params_copy_);
        }

        bool prepare(PyObject *points_obj, PyObject *faces_obj, PyObject *params_obj)
        {
            if (!collect_mesh_points(points_obj, points_))
            {
                return false;
            }
            if (!collect_mesh_faces(faces_obj, points_.size(), faces_))
            {
                return false;
            }
            if (!prepare_params(params_obj))
            {
                return false;
            }

            resolve_algorithm_mode();
            return true;
        }

        const std::vector<Vec3> &points() const
        {
            return points_;
        }

        const std::vector<std::array<int, 3>> &faces() const
        {
            return faces_;
        }

        bool acp_energy_mode() const
        {
            return acp_energy_mode_;
        }

        PyObject *params_copy() const
        {
            return params_copy_;
        }

        PyObject *release_params_copy()
        {
            PyObject *released = params_copy_;
            params_copy_ = nullptr;
            return released;
        }

    private:
        bool prepare_params(PyObject *params_obj)
        {
            params_copy_ = copy_params_dict(params_obj);
            return params_copy_ != nullptr;
        }

        void resolve_algorithm_mode()
        {
            const SolverAlgorithmProfile profile = solver_algorithm_profile_from_params(params_copy_);
            acp_energy_mode_ = profile.acp_energy_mode;
        }

        std::vector<Vec3> points_;
        std::vector<std::array<int, 3>> faces_;
        PyObject *params_copy_ = nullptr;
        bool acp_energy_mode_ = false;
    };

    class MeshSolveTopology
    {
    public:
        MeshSolveTopology(
            const std::vector<Vec3> &points,
            const std::vector<std::array<int, 3>> &faces,
            PyObject *params_copy)
            : fabric_quads_(extract_quads(faces, points)),
              loops_idx_(boundary_loops(faces)),
              constrained_edges_(!fabric_quads_.empty()
                                     ? perimeter_edges_from_quads(fabric_quads_)
                                     : edges_from_triangles(faces)),
              nominal_edge_length_(read_nominal_edge_length(params_copy)),
              relax_iterations_(resolve_relax_iterations(params_copy))
        {
        }

        const std::vector<std::vector<int>> &fabric_quads() const
        {
            return fabric_quads_;
        }

        const std::vector<std::vector<int>> &loops_idx() const
        {
            return loops_idx_;
        }

        const std::vector<std::pair<int, int>> &constrained_edges() const
        {
            return constrained_edges_;
        }

        double nominal_edge_length() const
        {
            return nominal_edge_length_;
        }

        int relax_iterations() const
        {
            return relax_iterations_;
        }

    private:
        std::vector<std::vector<int>> fabric_quads_;
        std::vector<std::vector<int>> loops_idx_;
        std::vector<std::pair<int, int>> constrained_edges_;
        double nominal_edge_length_ = 0.0;
        int relax_iterations_ = 0;
    };

    struct MeshResultBuildInput
    {
        PyObject *params_copy;
        bool acp_energy_mode;
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
        const std::vector<std::pair<int, int>> &constrained_edges;
        const std::vector<double> &edge_targets;
        double nominal_edge_length;
        int relax_iterations;
        const std::vector<double> &residual_history;
        const AcpPropagationSummary &acp_summary;
    };

    static PyObject *build_mesh_result_object(const MeshResultBuildInput &input)
    {
        ResultBuildScope scope(input.params_copy);
        if (!build_mesh_python_lists(
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
                scope.fabric_points_list(),
                scope.fabric_quads_list(),
                scope.boundary_loops_list(),
                scope.strains_list(),
                scope.mesh_points_list(),
                scope.mesh_faces_list(),
                scope.face_frames_list(),
                scope.orientation_breaks_list(),
                scope.atlas_charts_list()))
        {
            return nullptr;
        }

        EdgeDiagnosticsContext edge_context = append_edge_diagnostics_break(
            scope.params_copy(),
            scope.orientation_breaks_list(),
            input.acp_energy_mode,
            input.fabric_points,
            input.constrained_edges,
            input.edge_targets,
            input.nominal_edge_length);

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
            input.acp_energy_mode,
            input.acp_summary,
            coverage_point_count,
            -1,
            -1,
            -1,
            -1,
            -1,
            -1,
        };
        attach_result_diagnostics(result, scope.params_copy(), diagnostics_input);

        return result;
    }

    static PyObject *solve_impl(PyObject *, PyObject *args, PyObject *kwargs)
    {
        static const char *kwlist[] = {"mesh_points", "mesh_faces", "parameters", nullptr};
        PyObject *points_obj = nullptr;
        PyObject *faces_obj = Py_None;
        PyObject *params_obj = Py_None;

        if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OO", const_cast<char **>(kwlist), &points_obj, &faces_obj, &params_obj))
        {
            return nullptr;
        }

        if (geometry_like(points_obj))
        {
            return solve_geometry(points_obj, params_obj);
        }

        MeshSolveInputContext input;
        if (!input.prepare(points_obj, faces_obj, params_obj))
        {
            return nullptr;
        }

        const DrapingAlgorithmPolicy algorithm_policy(input.params_copy());
        if (!algorithm_policy.supported())
        {
            return algorithm_policy.build_unsupported_result(input.release_params_copy());
        }

        if (input.points().empty())
        {
            return build_empty_geometry_result("fishnet solver needs at least one point", input.release_params_copy());
        }
        if (input.faces().empty())
        {
            return build_empty_geometry_result("fishnet solver needs at least one face", input.release_params_copy());
        }

        Vec3 origin = centroid(input.points());
        Vec3 normal{}, x_axis{}, y_axis{};
        build_basis(input.points(), input.faces(), normal, x_axis, y_axis);

        MeshSolveTopology topology(input.points(), input.faces(), input.params_copy());

        FabricLayoutSolverState layout_solver(
            input.points(),
            origin,
            normal,
            x_axis,
            y_axis,
            topology.constrained_edges(),
            topology.loops_idx(),
            topology.nominal_edge_length(),
            topology.relax_iterations());
        layout_solver.initialize_seed_points(nullptr);

        AcpPropagationSummary acp_summary;
        std::vector<double> edge_targets;
        std::vector<double> edge_weights;
        layout_solver.configure_acp_if_enabled(
            input.acp_energy_mode(),
            input.params_copy(),
            acp_summary,
            edge_targets,
            edge_weights);

        layout_solver.relax(input.acp_energy_mode(), edge_targets, edge_weights);

        std::vector<std::vector<Vec3>> loops_pts = layout_solver.build_loop_points();
        std::vector<std::array<double, 3>> strains = face_strains(input.faces(), layout_solver.local_points(), normal);

        const MeshResultBuildInput result_input{
            input.release_params_copy(),
            input.acp_energy_mode(),
            input.points(),
            input.faces(),
            layout_solver.fabric_points(),
            topology.fabric_quads(),
            loops_pts,
            strains,
            origin,
            normal,
            x_axis,
            y_axis,
            topology.constrained_edges(),
            edge_targets,
            topology.nominal_edge_length(),
            topology.relax_iterations(),
            layout_solver.residual_history(),
            acp_summary,
        };
        return build_mesh_result_object(result_input);
    }

} // namespace fishnet_internal

PyObject *fishnet_solve(PyObject *self, PyObject *args, PyObject *kwargs)
{
    return fishnet_internal::solve_impl(self, args, kwargs);
}
