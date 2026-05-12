#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <limits>
#include <set>
#include <string>
#include <unordered_set>
#include <vector>

#include "fishnet_result_builder.hpp"

#include "fishnet_metric_cell_diagnostics.hpp"

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

    static long coverage_point_count_for_cells(
        const std::vector<std::vector<int>> &quads,
        const std::vector<std::array<int, 3>> &triangles)
    {
        std::unordered_set<int> covered;
        for (const auto &q : quads)
        {
            for (int idx : q)
            {
                if (idx >= 0)
                {
                    covered.insert(idx);
                }
            }
        }
        for (const auto &tri : triangles)
        {
            for (int idx : tri)
            {
                if (idx >= 0)
                {
                    covered.insert(idx);
                }
            }
        }
        return static_cast<long>(covered.size());
    }

    struct BoundaryReferenceAggregatePlaceholders
    {
        long total{0};
        long valid{0};
        long invalid{0};
        long sample_count{0};
        long loop_count{0};
        long loop_point_count{0};

        long geodesic_fibre_count{0};
        long geodesic_arm_target_count{0};
        long geodesic_arm_attempt_count{0};
        long geodesic_arm_success_count{0};
        long geodesic_arm_failure_count{0};
        long geodesic_arm_boundary_hit_count{0};
        double geodesic_arm_success_ratio{0.0};

        long geodesic_seed_commit_success_count{0};
        long geodesic_seed_commit_failure_count{0};

        long geodesic_step_attempt_count{0};
        long geodesic_step_success_count{0};
        long geodesic_step_failure_count{0};
        double geodesic_step_success_ratio{0.0};
        long geodesic_step_backtrack_count{0};
        long geodesic_step_candidate_attempt_count{0};
        long geodesic_step_candidate_outside_face_count{0};
        long geodesic_step_candidate_evaluation_failure_count{0};
        long geodesic_step_terminal_state_in_count{0};
        long geodesic_step_terminal_state_on_count{0};
        long geodesic_step_terminal_state_unknown_count{0};

        long geodesic_failure_geodesic_step_count{0};
        long geodesic_failure_degenerate_frame_count{0};
        long geodesic_failure_singular_metric_count{0};
        long geodesic_failure_stalled_count{0};
        long geodesic_failure_outside_face_count{0};
        long geodesic_failure_evaluation_count{0};
        long geodesic_failure_unknown_count{0};
        long geodesic_failure_node_commit_count{0};
        long geodesic_covered_node_count{0};
        long geodesic_total_node_count{0};
        double geodesic_coverage_ratio{0.0};
    };

    static std::string lowercase_copy_for_metric_mode(std::string value)
    {
        std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c)
                       { return static_cast<char>(std::tolower(c)); });
        return value;
    }

    static std::string parse_metric_strategy_name(const std::string &raw_value)
    {
        const std::string value = lowercase_copy_for_metric_mode(raw_value);
        if (value == "surface_spacing" || value == "surface-spacing" || value == "v2")
        {
            return "surface_spacing";
        }
        if (value == "woven" || value == "default" || value == "v1")
        {
            return "woven";
        }
        return "";
    }

    static std::string metric_mode_requested_label(PyObject *params_copy)
    {
        const std::string requested_algorithm = solver_algorithm_from_params(params_copy);
        const std::string requested_algorithm_norm = lowercase_copy_for_metric_mode(requested_algorithm);
        if (requested_algorithm_norm != "acp_energy")
        {
            return requested_algorithm;
        }

        if (param_bool(params_copy, "objective_surface_spacing", false))
        {
            return "acp_energy:surface_spacing";
        }

        const std::string requested_strategy = parse_metric_strategy_name(param_string(params_copy, "acp_strategy", ""));
        if (!requested_strategy.empty())
        {
            return std::string("acp_energy:") + requested_strategy;
        }

        return "acp_energy:woven";
    }

    static std::string metric_mode_effective_label(PyObject *params_copy)
    {
        const SolverAlgorithmProfile profile = solver_algorithm_profile_from_params(params_copy);
        if (!profile.acp_energy_mode)
        {
            return profile.requested_algorithm;
        }

        const std::string strategy = profile.acp_strategy.empty() ? std::string("woven") : profile.acp_strategy;
        return std::string("acp_energy:") + strategy;
    }

    static long loop_point_count_from_indices(const std::vector<std::vector<int>> &loops_idx)
    {
        long point_count = 0;
        for (const auto &loop : loops_idx)
        {
            point_count += static_cast<long>(loop.size());
        }
        return point_count;
    }

    static long loop_point_count_from_points(const std::vector<std::vector<Vec3>> &loops_pts)
    {
        long point_count = 0;
        for (const auto &loop : loops_pts)
        {
            point_count += static_cast<long>(loop.size());
        }
        return point_count;
    }

    static BoundaryReferenceAggregatePlaceholders build_boundary_reference_placeholders(
        long sample_count,
        long loop_count,
        long loop_point_count,
        long valid_loop_count)
    {
        BoundaryReferenceAggregatePlaceholders placeholders;
        placeholders.sample_count = std::max(0L, sample_count);
        placeholders.loop_count = std::max(0L, loop_count);
        placeholders.loop_point_count = std::max(0L, loop_point_count);

        // Placeholder contract: expect two boundary-reference families per sampled face.
        placeholders.total = placeholders.sample_count > 0
                                 ? placeholders.sample_count * 2
                                 : placeholders.loop_count;
        placeholders.valid = std::clamp(valid_loop_count, 0L, placeholders.total);
        placeholders.invalid = std::max(0L, placeholders.total - placeholders.valid);
        return placeholders;
    }

    static BoundaryReferenceAggregatePlaceholders build_boundary_reference_placeholders_from_indices(
        const std::vector<FaceSample> &samples,
        const std::vector<std::vector<int>> &loops_idx)
    {
        long valid_loop_count = 0;
        for (const auto &loop : loops_idx)
        {
            if (loop.size() >= 2)
            {
                valid_loop_count += 1;
            }
        }

        BoundaryReferenceAggregatePlaceholders placeholders = build_boundary_reference_placeholders(
            static_cast<long>(samples.size()),
            static_cast<long>(loops_idx.size()),
            loop_point_count_from_indices(loops_idx),
            valid_loop_count);

        long total_nodes = 0;
        long covered_nodes = 0;
        for (const auto &sample : samples)
        {
            placeholders.geodesic_fibre_count += std::max(0L, sample.boundary_reference_fibre_count);
            placeholders.geodesic_arm_target_count += std::max(0L, sample.boundary_reference_arm_target_count);
            placeholders.geodesic_arm_attempt_count += std::max(0L, sample.boundary_reference_arm_attempt_count);
            placeholders.geodesic_arm_success_count += std::max(0L, sample.boundary_reference_arm_success_count);
            placeholders.geodesic_arm_failure_count += std::max(0L, sample.boundary_reference_arm_failure_count);
            placeholders.geodesic_arm_boundary_hit_count += std::max(0L, sample.boundary_reference_arm_boundary_hit_count);

            placeholders.geodesic_seed_commit_success_count += std::max(0L, sample.boundary_reference_seed_commit_success_count);
            placeholders.geodesic_seed_commit_failure_count += std::max(0L, sample.boundary_reference_seed_commit_failure_count);

            placeholders.geodesic_step_attempt_count += std::max(0L, sample.boundary_reference_step_attempt_count);
            placeholders.geodesic_step_success_count += std::max(0L, sample.boundary_reference_step_success_count);
            placeholders.geodesic_step_failure_count += std::max(0L, sample.boundary_reference_step_failure_count);
            placeholders.geodesic_step_backtrack_count += std::max(0L, sample.boundary_reference_step_backtrack_count);
            placeholders.geodesic_step_candidate_attempt_count += std::max(0L, sample.boundary_reference_step_candidate_attempt_count);
            placeholders.geodesic_step_candidate_outside_face_count += std::max(0L, sample.boundary_reference_step_candidate_outside_face_count);
            placeholders.geodesic_step_candidate_evaluation_failure_count += std::max(0L, sample.boundary_reference_step_candidate_evaluation_failure_count);
            placeholders.geodesic_step_terminal_state_in_count += std::max(0L, sample.boundary_reference_step_terminal_state_in_count);
            placeholders.geodesic_step_terminal_state_on_count += std::max(0L, sample.boundary_reference_step_terminal_state_on_count);
            placeholders.geodesic_step_terminal_state_unknown_count += std::max(0L, sample.boundary_reference_step_terminal_state_unknown_count);

            placeholders.geodesic_failure_geodesic_step_count += std::max(0L, sample.boundary_reference_failure_geodesic_step_count);
            placeholders.geodesic_failure_degenerate_frame_count += std::max(0L, sample.boundary_reference_failure_degenerate_frame_count);
            placeholders.geodesic_failure_singular_metric_count += std::max(0L, sample.boundary_reference_failure_singular_metric_count);
            placeholders.geodesic_failure_stalled_count += std::max(0L, sample.boundary_reference_failure_stalled_count);
            placeholders.geodesic_failure_outside_face_count += std::max(0L, sample.boundary_reference_failure_outside_face_count);
            placeholders.geodesic_failure_evaluation_count += std::max(0L, sample.boundary_reference_failure_evaluation_count);
            placeholders.geodesic_failure_unknown_count += std::max(0L, sample.boundary_reference_failure_unknown_count);
            placeholders.geodesic_failure_node_commit_count += std::max(0L, sample.boundary_reference_failure_node_commit_count);

            const long sample_total = std::max(0L, sample.boundary_reference_total_node_count);
            const long sample_covered = std::clamp(sample.boundary_reference_covered_node_count, 0L, sample_total);
            total_nodes += sample_total;
            covered_nodes += sample_covered;
        }

        placeholders.geodesic_arm_success_ratio = placeholders.geodesic_arm_attempt_count > 0
                                                      ? finite_or_zero(static_cast<double>(placeholders.geodesic_arm_success_count) /
                                                                       static_cast<double>(placeholders.geodesic_arm_attempt_count))
                                                      : 0.0;
        placeholders.geodesic_step_success_ratio = placeholders.geodesic_step_attempt_count > 0
                                                       ? finite_or_zero(static_cast<double>(placeholders.geodesic_step_success_count) /
                                                                        static_cast<double>(placeholders.geodesic_step_attempt_count))
                                                       : 0.0;
        placeholders.geodesic_total_node_count = total_nodes;
        placeholders.geodesic_covered_node_count = std::clamp(covered_nodes, 0L, total_nodes);
        placeholders.geodesic_coverage_ratio = total_nodes > 0
                                                   ? finite_or_zero(static_cast<double>(placeholders.geodesic_covered_node_count) / static_cast<double>(total_nodes))
                                                   : 0.0;

        if (total_nodes > 0)
        {
            placeholders.total = total_nodes;
            placeholders.valid = std::clamp(covered_nodes, 0L, total_nodes);
            placeholders.invalid = std::max(0L, placeholders.total - placeholders.valid);
        }

        return placeholders;
    }

    static BoundaryReferenceAggregatePlaceholders build_boundary_reference_placeholders_from_points(
        const std::vector<std::vector<Vec3>> &loops_pts)
    {
        long valid_loop_count = 0;
        for (const auto &loop : loops_pts)
        {
            if (loop.size() >= 2)
            {
                valid_loop_count += 1;
            }
        }

        return build_boundary_reference_placeholders(
            0,
            static_cast<long>(loops_pts.size()),
            loop_point_count_from_points(loops_pts),
            valid_loop_count);
    }

    static void attach_metric_contract_diagnostics(
        PyObject *result,
        PyObject *params_copy,
        const MetricCellResidualDiagnostics &metric_residuals,
        const BoundaryReferenceAggregatePlaceholders &boundary_ref_placeholders)
    {
        PyObject *diagnostics = result ? PyDict_GetItemString(result, "diagnostics") : nullptr;
        if (!diagnostics || !PyDict_Check(diagnostics))
        {
            return;
        }

        set_diag_double(diagnostics, "metric_eq410_residual_mean", metric_residuals.eq410_residual_mean);
        set_diag_double(diagnostics, "metric_eq410_residual_max", metric_residuals.eq410_residual_max);
        set_diag_double(diagnostics, "metric_eq410_residual_p95", metric_residuals.eq410_residual_p95);
        set_diag_double(diagnostics, "metric_eq411_residual_mean", metric_residuals.eq411_residual_mean);
        set_diag_double(diagnostics, "metric_eq411_residual_max", metric_residuals.eq411_residual_max);
        set_diag_double(diagnostics, "metric_eq411_residual_p95", metric_residuals.eq411_residual_p95);
        set_diag_double(diagnostics, "metric_eq412_residual_mean", metric_residuals.eq412_residual_mean);
        set_diag_double(diagnostics, "metric_eq412_residual_max", metric_residuals.eq412_residual_max);
        set_diag_double(diagnostics, "metric_eq412_residual_p95", metric_residuals.eq412_residual_p95);
        set_diag_double(diagnostics, "metric_residual_combined_l2", metric_residuals.residual_combined_l2);
        set_diag_double(diagnostics, "metric_residual_combined_linf", metric_residuals.residual_combined_linf);
        set_diag_double(diagnostics, "metric_residual_combined_p95", metric_residuals.residual_combined_p95);

        set_diag_long(diagnostics, "metric_cell_count_total", metric_residuals.cell_count_total);
        set_diag_long(diagnostics, "metric_cell_count_valid", metric_residuals.cell_count_valid);
        set_diag_long(diagnostics, "metric_cell_count_invalid", metric_residuals.cell_count_invalid);
        set_diag_double(diagnostics, "metric_cell_valid_ratio", metric_residuals.cell_valid_ratio);
        set_diag_double(diagnostics, "metric_cell_invalid_ratio", metric_residuals.cell_invalid_ratio);

        const std::string requested_mode = metric_mode_requested_label(params_copy);
        const std::string effective_mode = metric_mode_effective_label(params_copy);
        const std::string fallback_mode = requested_mode == effective_mode ? std::string("none") : effective_mode;

        set_diag_string(diagnostics, "metric_mode_requested", requested_mode.c_str());
        set_diag_string(diagnostics, "metric_mode_effective", effective_mode.c_str());
        set_diag_string(diagnostics, "metric_mode_fallback", fallback_mode.c_str());

        set_diag_long(diagnostics, "boundary_ref_total", boundary_ref_placeholders.total);
        set_diag_long(diagnostics, "boundary_ref_valid", boundary_ref_placeholders.valid);
        set_diag_long(diagnostics, "boundary_ref_invalid", boundary_ref_placeholders.invalid);
        set_diag_long(diagnostics, "boundary_ref_sample_count", boundary_ref_placeholders.sample_count);
        set_diag_long(diagnostics, "boundary_ref_loop_count", boundary_ref_placeholders.loop_count);
        set_diag_long(diagnostics, "boundary_ref_loop_point_count", boundary_ref_placeholders.loop_point_count);

        const SolverAlgorithmProfile profile = solver_algorithm_profile_from_params(params_copy);
        PyDict_SetItemString(diagnostics, "boundary_ref_geodesic_enabled", profile.paper_alignment_enabled ? Py_True : Py_False);
        set_diag_long(diagnostics, "boundary_ref_geodesic_fibre_count", boundary_ref_placeholders.geodesic_fibre_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_arm_target_count", boundary_ref_placeholders.geodesic_arm_target_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_arm_attempt_count", boundary_ref_placeholders.geodesic_arm_attempt_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_arm_success_count", boundary_ref_placeholders.geodesic_arm_success_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_arm_failure_count", boundary_ref_placeholders.geodesic_arm_failure_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_arm_boundary_hit_count", boundary_ref_placeholders.geodesic_arm_boundary_hit_count);
        set_diag_double(diagnostics, "boundary_ref_geodesic_arm_success_ratio", finite_or_zero(boundary_ref_placeholders.geodesic_arm_success_ratio));

        set_diag_long(diagnostics, "boundary_ref_geodesic_seed_commit_success_count", boundary_ref_placeholders.geodesic_seed_commit_success_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_seed_commit_failure_count", boundary_ref_placeholders.geodesic_seed_commit_failure_count);

        set_diag_long(diagnostics, "boundary_ref_geodesic_step_attempt_count", boundary_ref_placeholders.geodesic_step_attempt_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_step_success_count", boundary_ref_placeholders.geodesic_step_success_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_step_failure_count", boundary_ref_placeholders.geodesic_step_failure_count);
        set_diag_double(diagnostics, "boundary_ref_geodesic_step_success_ratio", finite_or_zero(boundary_ref_placeholders.geodesic_step_success_ratio));
        set_diag_long(diagnostics, "boundary_ref_geodesic_step_backtrack_count", boundary_ref_placeholders.geodesic_step_backtrack_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_step_candidate_attempt_count", boundary_ref_placeholders.geodesic_step_candidate_attempt_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_step_candidate_outside_face_count", boundary_ref_placeholders.geodesic_step_candidate_outside_face_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_step_candidate_evaluation_failure_count", boundary_ref_placeholders.geodesic_step_candidate_evaluation_failure_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_step_terminal_state_in_count", boundary_ref_placeholders.geodesic_step_terminal_state_in_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_step_terminal_state_on_count", boundary_ref_placeholders.geodesic_step_terminal_state_on_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_step_terminal_state_unknown_count", boundary_ref_placeholders.geodesic_step_terminal_state_unknown_count);

        set_diag_long(diagnostics, "boundary_ref_geodesic_failure_geodesic_step_count", boundary_ref_placeholders.geodesic_failure_geodesic_step_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_failure_degenerate_frame_count", boundary_ref_placeholders.geodesic_failure_degenerate_frame_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_failure_singular_metric_count", boundary_ref_placeholders.geodesic_failure_singular_metric_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_failure_stalled_count", boundary_ref_placeholders.geodesic_failure_stalled_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_failure_outside_face_count", boundary_ref_placeholders.geodesic_failure_outside_face_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_failure_evaluation_count", boundary_ref_placeholders.geodesic_failure_evaluation_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_failure_unknown_count", boundary_ref_placeholders.geodesic_failure_unknown_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_failure_node_commit_count", boundary_ref_placeholders.geodesic_failure_node_commit_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_covered_node_count", boundary_ref_placeholders.geodesic_covered_node_count);
        set_diag_long(diagnostics, "boundary_ref_geodesic_total_node_count", boundary_ref_placeholders.geodesic_total_node_count);
        set_diag_double(diagnostics, "boundary_ref_geodesic_coverage_ratio", finite_or_zero(boundary_ref_placeholders.geodesic_coverage_ratio));
    }

    struct SurfaceSpacingStrictVerification
    {
        bool enabled{false};
        bool fail_on_violation{false};
        double tolerance{0.0};
        long edge_count{0};
        long violation_count{0};
        double max_rel_error{0.0};
        bool pass{true};
        long repair_passes{0};
        std::string fail_reason{"none"};
        bool force_nonconverged{false};
    };

    static std::pair<long, double> surface_spacing_edge_violation_summary(
        const std::vector<Vec3> &points,
        const std::vector<std::vector<int>> &quads,
        double target_spacing,
        double tolerance,
        std::set<std::pair<int, int>> *violating_edges)
    {
        if (violating_edges)
        {
            violating_edges->clear();
        }
        if (points.empty() || quads.empty() ||
            !std::isfinite(target_spacing) || target_spacing <= kVectorZeroEpsilon ||
            !std::isfinite(tolerance) || tolerance < 0.0)
        {
            return {0L, 0.0};
        }

        std::set<std::pair<int, int>> unique_edges;
        long violations = 0;
        double max_rel_error = 0.0;

        for (const auto &quad : quads)
        {
            if (quad.size() < 4)
            {
                continue;
            }
            const int a = quad[0];
            const int b = quad[1];
            const int c = quad[2];
            const int d = quad[3];
            const std::array<std::pair<int, int>, 4> edge_pairs{{
                {a, b},
                {b, c},
                {c, d},
                {d, a},
            }};

            for (const auto &edge_pair : edge_pairs)
            {
                int e0 = edge_pair.first;
                int e1 = edge_pair.second;
                if (e0 == e1 ||
                    e0 < 0 || e1 < 0 ||
                    e0 >= static_cast<int>(points.size()) ||
                    e1 >= static_cast<int>(points.size()))
                {
                    continue;
                }
                if (e0 > e1)
                {
                    std::swap(e0, e1);
                }
                const auto edge = std::make_pair(e0, e1);
                if (!unique_edges.insert(edge).second)
                {
                    continue;
                }

                const Vec3 delta = points[static_cast<size_t>(e1)] - points[static_cast<size_t>(e0)];
                const double length = norm(delta);
                if (!std::isfinite(length))
                {
                    continue;
                }
                const double rel_error = std::abs(length - target_spacing) / target_spacing;
                if (!std::isfinite(rel_error))
                {
                    continue;
                }
                if (rel_error > tolerance)
                {
                    violations += 1;
                    max_rel_error = std::max(max_rel_error, rel_error);
                    if (violating_edges)
                    {
                        violating_edges->insert(edge);
                    }
                }
            }
        }

        return {violations, max_rel_error};
    }

    static long surface_spacing_structural_edge_count(
        const std::vector<Vec3> &points,
        const std::vector<std::vector<int>> &quads)
    {
        if (points.empty() || quads.empty())
        {
            return 0;
        }

        std::set<std::pair<int, int>> unique_edges;
        for (const auto &quad : quads)
        {
            if (quad.size() < 4)
            {
                continue;
            }
            const int a = quad[0];
            const int b = quad[1];
            const int c = quad[2];
            const int d = quad[3];
            const std::array<std::pair<int, int>, 4> edge_pairs{{
                {a, b},
                {b, c},
                {c, d},
                {d, a},
            }};
            for (const auto &edge_pair : edge_pairs)
            {
                int e0 = edge_pair.first;
                int e1 = edge_pair.second;
                if (e0 == e1 ||
                    e0 < 0 || e1 < 0 ||
                    e0 >= static_cast<int>(points.size()) ||
                    e1 >= static_cast<int>(points.size()))
                {
                    continue;
                }
                if (e0 > e1)
                {
                    std::swap(e0, e1);
                }
                unique_edges.insert({e0, e1});
            }
        }

        return static_cast<long>(unique_edges.size());
    }

    static SurfaceSpacingStrictVerification enforce_surface_spacing_strict_mode(
        const SurfaceSpacingStrictPolicy &strict_policy,
        bool surface_spacing_mode,
        const std::vector<Vec3> &points,
        std::vector<std::vector<int>> &quads,
        double target_spacing)
    {
        SurfaceSpacingStrictVerification verification;
        verification.enabled = surface_spacing_mode && strict_policy.enabled;
        verification.fail_on_violation = strict_policy.fail_on_violation;
        verification.tolerance = strict_policy.tolerance;

        if (!verification.enabled)
        {
            return verification;
        }

        if (!std::isfinite(target_spacing) || target_spacing <= kVectorZeroEpsilon)
        {
            verification.pass = false;
            verification.fail_reason = "infeasible_geometry";
            verification.force_nonconverged = verification.fail_on_violation;
            return verification;
        }

        constexpr int kMaxRepairPasses = 3;
        for (int pass = 0; pass < kMaxRepairPasses; ++pass)
        {
            std::set<std::pair<int, int>> violating_edges;
            const auto [violation_count, max_rel_error] = surface_spacing_edge_violation_summary(
                points,
                quads,
                target_spacing,
                verification.tolerance,
                &violating_edges);

            verification.violation_count = violation_count;
            verification.max_rel_error = max_rel_error;
            if (violation_count <= 0)
            {
                break;
            }
            if (quads.empty())
            {
                break;
            }

            std::vector<std::vector<int>> repaired_quads;
            repaired_quads.reserve(quads.size());
            for (const auto &quad : quads)
            {
                if (quad.size() < 4)
                {
                    continue;
                }

                const int a = quad[0];
                const int b = quad[1];
                const int c = quad[2];
                const int d = quad[3];
                const std::array<std::pair<int, int>, 4> edge_pairs{{
                    {std::min(a, b), std::max(a, b)},
                    {std::min(b, c), std::max(b, c)},
                    {std::min(c, d), std::max(c, d)},
                    {std::min(d, a), std::max(d, a)},
                }};

                bool intersects_violation = false;
                for (const auto &edge : edge_pairs)
                {
                    if (violating_edges.find(edge) != violating_edges.end())
                    {
                        intersects_violation = true;
                        break;
                    }
                }
                if (!intersects_violation)
                {
                    repaired_quads.push_back(quad);
                }
            }

            if (repaired_quads.size() == quads.size())
            {
                break;
            }

            quads.swap(repaired_quads);
            verification.repair_passes += 1;
            if (quads.empty())
            {
                break;
            }
        }

        const auto [final_violations, final_max_rel_error] = surface_spacing_edge_violation_summary(
            points,
            quads,
            target_spacing,
            verification.tolerance,
            nullptr);
        verification.violation_count = final_violations;
        verification.max_rel_error = final_max_rel_error;

        verification.edge_count = surface_spacing_structural_edge_count(points, quads);

        verification.pass = verification.edge_count > 0 && verification.violation_count == 0;
        if (!verification.pass)
        {
            verification.fail_reason = verification.edge_count <= 0 ? "insufficient_coverage" : "violations_after_repair";
        }
        verification.force_nonconverged = verification.fail_on_violation && !verification.pass;

        return verification;
    }

    static bool quad_within_shear_limit_radians(
        const std::vector<Vec3> &points,
        const std::vector<int> &quad,
        double max_shear_angle)
    {
        if (quad.size() < 4)
        {
            return false;
        }
        if (!std::isfinite(max_shear_angle) || max_shear_angle < 0.0)
        {
            return true;
        }

        const int a = quad[0];
        const int b = quad[1];
        const int c = quad[2];
        const int d = quad[3];
        if (std::min({a, b, c, d}) < 0 ||
            std::max({a, b, c, d}) >= static_cast<int>(points.size()))
        {
            return false;
        }

        constexpr double kHalfPi = 1.5707963267948966;
        const std::array<int, 4> ids{{a, b, c, d}};
        for (int k = 0; k < 4; ++k)
        {
            const Vec3 &prev = points[static_cast<size_t>(ids[static_cast<size_t>((k + 3) % 4)])];
            const Vec3 &curr = points[static_cast<size_t>(ids[static_cast<size_t>(k)])];
            const Vec3 &next = points[static_cast<size_t>(ids[static_cast<size_t>((k + 1) % 4)])];
            const Vec3 e1 = prev - curr;
            const Vec3 e2 = next - curr;
            const double n1 = norm(e1);
            const double n2 = norm(e2);
            if (n1 <= kVectorZeroEpsilon || n2 <= kVectorZeroEpsilon)
            {
                return false;
            }
            const double cos_ang = std::clamp(dot(e1, e2) / (n1 * n2), -1.0, 1.0);
            const double ang = std::acos(cos_ang);
            const double shear = std::fabs(kHalfPi - ang);
            if (shear > max_shear_angle + 1.0e-9)
            {
                return false;
            }
        }
        return true;
    }

    static std::vector<std::vector<int>> filtered_geometry_quads_for_output(
        const std::vector<std::vector<int>> &quads,
        const std::vector<Vec3> &points,
        PyObject *params_copy)
    {
        if (quads.empty())
        {
            return quads;
        }

        const SolverAlgorithmProfile profile = solver_algorithm_profile_from_params(params_copy);
        if (profile.surface_spacing_mode)
        {
            return quads;
        }

        const double max_shear_deg = param_double(params_copy, "max_shear_angle_deg", 30.0);
        if (!std::isfinite(max_shear_deg) || max_shear_deg < 0.0)
        {
            return quads;
        }

        const double max_shear_angle = max_shear_deg * 0.017453292519943295;
        std::vector<std::vector<int>> filtered;
        filtered.reserve(quads.size());
        for (const auto &quad : quads)
        {
            if (quad_within_shear_limit_radians(points, quad, max_shear_angle))
            {
                filtered.push_back(quad);
            }
        }

        return filtered;
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
        const std::vector<Vec3> &solver_points;
        const std::vector<Vec3> &solver_fabric_points;
        const std::vector<Vec3> &output_fabric_points;
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
            input.solver_fabric_points,
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
            input.solver_points,
            input.solver_fabric_points,
            input.nominal_edge_length);

        if (!append_first_face_frame(input.face_frames_list, input.samples, input.face_indices) ||
            !append_atlas_charts_and_overlap_break(
                input.atlas_charts_list,
                input.orientation_breaks_list,
                input.output_fabric_points,
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
            return nullptr;
        }

        const ResultCompatibilityPayload payload{
            true,
            "",
            input.params_copy,
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
        };
        return build_result_from_compat_payload(payload, nullptr);
    }

    struct GeometryResultDiagnosticsInput
    {
        const std::vector<FaceSample> &samples;
        const std::vector<Vec3> &solver_points;
        const std::vector<std::array<int, 3>> &solver_triangles;
        const std::vector<std::vector<int>> &solver_quads;
        const std::vector<Vec3> &output_points;
        const std::vector<Vec3> &output_fabric_points;
        const std::vector<std::vector<int>> &output_quads;
        const std::vector<TopoDS_Face> &native_faces;
        const std::vector<std::array<double, 2>> &point_uv;
        const std::vector<int> &point_face_indices;
        const std::vector<std::vector<int>> &output_loops_idx;
        long trim_clipped_cell_count;
        long trim_generated_vertex_count;
        PyObject *orientation_breaks_list;
        const EdgeDiagnosticsContext &edge_context;
        int relax_iterations;
        const std::vector<double> &residual_history;
        const std::vector<double> &combined_objective_history;
        bool acp_energy_mode;
        const AcpPropagationSummary &acp_summary;
        const AcpObjectiveSummary &objective_summary;
        const SurfaceSpacingStrictVerification &strict_verification;
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
        long topology_transition_count = 0;
        long topology_split_count = 0;
        long topology_merge_count = 0;
        long topology_transition_fail_count = 0;
        std::vector<long> per_row_counts;
        std::vector<long> per_row_transitions_in_counts;
        std::vector<long> per_row_transitions_out_counts;
        std::vector<TransitionEventSample> transition_event_history;
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
            per_row_active_cols_mean,
            topology_transition_count,
            topology_split_count,
            topology_merge_count,
            topology_transition_fail_count,
            per_row_counts,
            per_row_transitions_in_counts,
            per_row_transitions_out_counts,
            transition_event_history);
        const long coverage_point_count = coverage_point_count_for_cells(input.solver_quads, input.solver_triangles);

        const SolverDiagnosticsInput diagnostics_input{
            static_cast<long>(input.samples.size()),
            static_cast<long>(input.solver_points.size()),
            static_cast<long>(input.solver_triangles.size()),
            static_cast<long>(input.solver_quads.size()),
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
            topology_transition_count,
            topology_split_count,
            topology_merge_count,
            topology_transition_fail_count,
            per_row_counts,
            per_row_transitions_in_counts,
            per_row_transitions_out_counts,
            transition_event_history,
            input.strict_verification.enabled,
            input.strict_verification.fail_on_violation,
            input.strict_verification.tolerance,
            input.strict_verification.edge_count,
            input.strict_verification.violation_count,
            input.strict_verification.max_rel_error,
            input.strict_verification.pass,
            input.strict_verification.repair_passes,
            input.strict_verification.fail_reason,
            input.strict_verification.force_nonconverged,
        };
        attach_result_diagnostics(result, params_copy, diagnostics_input);

        PyObject *diagnostics = result ? PyDict_GetItemString(result, "diagnostics") : nullptr;
        if (diagnostics && PyDict_Check(diagnostics))
        {
            set_diag_long(diagnostics, "trim_clipped_cell_count", input.trim_clipped_cell_count);
            set_diag_long(diagnostics, "trim_generated_vertex_count", input.trim_generated_vertex_count);
        }

        const MetricCellResidualDiagnostics metric_residuals = compute_metric_cell_residual_diagnostics(
            input.output_points,
            input.output_fabric_points,
            input.output_quads,
            &input.native_faces,
            &input.point_uv,
            &input.point_face_indices);
        const BoundaryReferenceAggregatePlaceholders boundary_ref_placeholders =
            build_boundary_reference_placeholders_from_indices(input.samples, input.output_loops_idx);
        attach_metric_contract_diagnostics(result, params_copy, metric_residuals, boundary_ref_placeholders);
    }

    PyObject *build_geometry_result_object(const GeometryResultBuildInput &input)
    {
        ResultBuildScope scope(input.params_copy);
        std::vector<std::vector<int>> filtered_quads = filtered_geometry_quads_for_output(
            input.quads,
            input.points,
            scope.params_copy());

        const SolverAlgorithmProfile profile = solver_algorithm_profile_from_params(scope.params_copy());
        const SurfaceSpacingStrictPolicy strict_policy = resolve_surface_spacing_strict_policy(scope.params_copy());
        SurfaceSpacingStrictVerification strict_verification = enforce_surface_spacing_strict_mode(
            strict_policy,
            profile.surface_spacing_mode,
            input.points,
            filtered_quads,
            input.nominal_edge_length);

        std::vector<std::vector<int>> mesh_face_vec;
        const GeometryPythonListsInput list_input{
            input.fabric_points,
            filtered_quads,
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
            input.solver_points,
            input.solver_fabric_points,
            input.fabric_points,
            input.nominal_edge_length,
            input.solver_constrained_edges,
            input.solver_edge_targets,
            filtered_quads,
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
            input.solver_points,
            input.solver_triangles,
            input.solver_quads,
            input.points,
            input.fabric_points,
            filtered_quads,
            input.native_faces,
            input.point_uv,
            input.point_face_indices,
            input.loops_idx,
            input.trim_clipped_cell_count,
            input.trim_generated_vertex_count,
            scope.orientation_breaks_list(),
            edge_context,
            input.relax_iterations,
            input.residual_history,
            input.combined_objective_history,
            input.acp_energy_mode,
            input.acp_summary,
            input.objective_summary,
            strict_verification,
        };
        attach_geometry_result_diagnostics(result, scope.params_copy(), diagnostics_input);

        return result;
    }

    PyObject *build_mesh_result_object(const MeshResultBuildInput &input)
    {
        ResultBuildScope scope(input.params_copy);

        std::vector<std::vector<int>> output_fabric_quads = input.fabric_quads;
        const SolverAlgorithmProfile profile = solver_algorithm_profile_from_params(scope.params_copy());
        const SurfaceSpacingStrictPolicy strict_policy = resolve_surface_spacing_strict_policy(scope.params_copy());
        SurfaceSpacingStrictVerification strict_verification = enforce_surface_spacing_strict_mode(
            strict_policy,
            profile.surface_spacing_mode,
            input.points,
            output_fabric_quads,
            input.nominal_edge_length);

        const MeshPythonListsInput list_input{
            input.points,
            input.faces,
            input.fabric_points,
            output_fabric_quads,
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

        const long coverage_point_count = coverage_point_count_for_quads(output_fabric_quads);
        static const std::vector<long> kEmptyPerRowCounts;
        static const std::vector<TransitionEventSample> kEmptyTransitionEventHistory;
        const SolverDiagnosticsInput diagnostics_input{
            -1,
            static_cast<long>(input.points.size()),
            static_cast<long>(input.faces.size()),
            static_cast<long>(output_fabric_quads.size()),
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
            0,
            0,
            0,
            0,
            kEmptyPerRowCounts,
            kEmptyPerRowCounts,
            kEmptyPerRowCounts,
            kEmptyTransitionEventHistory,
            strict_verification.enabled,
            strict_verification.fail_on_violation,
            strict_verification.tolerance,
            strict_verification.edge_count,
            strict_verification.violation_count,
            strict_verification.max_rel_error,
            strict_verification.pass,
            strict_verification.repair_passes,
            strict_verification.fail_reason,
            strict_verification.force_nonconverged,
        };
        const ResultCompatibilityPayload payload{
            true,
            "",
            scope.params_copy(),
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
        };

        PyObject *result = build_result_from_compat_payload(payload, &diagnostics_input);
        if (!result)
        {
            return nullptr;
        }

        const MetricCellResidualDiagnostics metric_residuals = compute_metric_cell_residual_diagnostics(
            input.points,
            input.fabric_points,
            output_fabric_quads);
        const BoundaryReferenceAggregatePlaceholders boundary_ref_placeholders =
            build_boundary_reference_placeholders_from_points(input.loops_pts);
        attach_metric_contract_diagnostics(result, scope.params_copy(), metric_residuals, boundary_ref_placeholders);

        return result;
    }

} // namespace fishnet_internal
