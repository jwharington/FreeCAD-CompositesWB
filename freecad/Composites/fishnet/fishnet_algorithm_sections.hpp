#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <array>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>
#include <TopoDS_Face.hxx>
#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal
{

    struct SeamContinuityStats
    {
        int group_count{0};
        double mean_min_distance{0.0};
        double max_min_distance{0.0};
    };

    struct AcpPropagationSummary
    {
        int seed_index{0};
        int primary_assigned{0};
        int orthogonal_assigned{0};
        int fill_assigned{0};
        Vec3 primary_axis{1.0, 0.0, 0.0};
        Vec3 orthogonal_axis{0.0, 1.0, 0.0};
    };

    struct AtlasChartBuild
    {
        std::vector<Vec3> points;
        std::vector<std::vector<int>> quads;
        std::vector<std::array<std::array<double, 2>, 4>> quad_polys;
        std::unordered_map<int, int> global_to_local;
    };

    struct FaceSample
    {
        std::vector<Vec3> points;
        std::vector<Vec3> layout_points;
        std::vector<std::array<int, 3>> triangles;
        std::vector<std::vector<int>> quads;
        Vec3 origin{0.0, 0.0, 0.0};
        Vec3 normal{0.0, 0.0, 1.0};
        Vec3 x_axis{1.0, 0.0, 0.0};
        Vec3 y_axis{0.0, 1.0, 0.0};
        long surface_spacing_active_nodes{0};
        long surface_spacing_total_nodes{0};
        long surface_spacing_frontier_pops{0};
        long surface_spacing_frontier_accepts{0};
        long surface_spacing_candidate_quads{0};
        long surface_spacing_selected_quads{0};
    };

    struct ExperimentalSolveStats
    {
        int calls{0};
        int base_failures{0};
        int seed_attempts{0};
        int seed_solved{0};
        int seed_local{0};
        int better_candidate_hits{0};
        int fallback_count{0};
        double improvement_sum{0.0};
        double best_shift_norm_sum{0.0};
        double best_shift_norm_max{0.0};
    };

    struct SolverAlgorithmProfile
    {
        std::string requested_algorithm{"acp_energy"};
        bool acp_energy_mode{false};
        bool surface_spacing_mode{false};
        std::string acp_strategy{"none"};
    };

    // Section APIs
    double orient2(const std::array<double, 2> &a, const std::array<double, 2> &b, const std::array<double, 2> &c);
    bool segment_intersect_proper(
        const std::array<double, 2> &a,
        const std::array<double, 2> &b,
        const std::array<double, 2> &c,
        const std::array<double, 2> &d,
        double eps);
    bool point_in_triangle_proper(
        const std::array<double, 2> &p,
        const std::array<double, 2> &a,
        const std::array<double, 2> &b,
        const std::array<double, 2> &c,
        double eps);
    bool triangles_overlap_proper(
        const std::array<std::array<double, 2>, 3> &t1,
        const std::array<std::array<double, 2>, 3> &t2,
        double eps);
    bool quads_overlap(
        const std::array<std::array<double, 2>, 4> &qa,
        const std::array<std::array<double, 2>, 4> &qb,
        double eps);
    bool segment_triangle_intersect_3d(
        const Vec3 &p0,
        const Vec3 &p1,
        const std::array<Vec3, 3> &tri,
        double eps);
    bool triangles_overlap_3d(
        const std::array<Vec3, 3> &t1,
        const std::array<Vec3, 3> &t2,
        double eps);
    bool quads_overlap_3d(
        const std::vector<Vec3> &points,
        const std::array<int, 4> &qa,
        const std::array<int, 4> &qb,
        double eps);
    std::vector<std::pair<int, int>> perimeter_edges_from_quads(const std::vector<std::vector<int>> &quads);
    std::vector<std::pair<int, int>> edges_from_triangles(const std::vector<std::array<int, 3>> &triangles);
    double mean_planar_edge_length(
        const std::vector<Vec3> &points,
        const std::vector<std::pair<int, int>> &edges);
    double infer_nominal_edge_length(
        double requested,
        const std::vector<Vec3> &fallback_points,
        const std::vector<std::pair<int, int>> &edges);
    double max_edge_relative_error_for_edges(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &edges,
        double requested_nominal_edge_length);
    double max_edge_relative_error_for_targets(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &edges,
        const std::vector<double> &edge_targets,
        double fallback_nominal_edge_length);
    std::pair<int, double> edge_length_violation_summary_for_targets(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &edges,
        const std::vector<double> &edge_targets,
        double fallback_nominal_edge_length,
        double rel_tol);
    void relax_fabric_points_with_edge_constraints(
        std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &edges,
        const std::vector<std::vector<int>> &boundary_loops,
        double requested_nominal_edge_length,
        int iterations,
        std::vector<double> *residual_history,
        const std::vector<double> *edge_targets,
        const std::vector<double> *edge_weights);
    std::pair<int, double> edge_length_violation_summary_for_edges(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::pair<int, int>> &edges,
        double requested_nominal_edge_length,
        double rel_tol);
    SeamContinuityStats seam_layout_continuity_summary(
        const std::vector<Vec3> &mesh_points,
        const std::vector<Vec3> &fabric_points,
        double position_tol);
    bool try_parse_param_vec3(PyObject *params, const char *key, Vec3 &out);
    double param_double(PyObject *params, const char *key, double fallback);
    bool param_bool(PyObject *params, const char *key, bool fallback);
    std::string param_string(PyObject *params, const char *key, const char *fallback);
    std::vector<std::vector<int>> build_vertex_adjacency(
        size_t point_count,
        const std::vector<std::pair<int, int>> &edges);
    int nearest_point_index(const std::vector<Vec3> &points, const Vec3 &target);
    Vec3 choose_primary_axis(
        const std::vector<Vec3> &local_points,
        const Vec3 &x_axis,
        const Vec3 &y_axis,
        PyObject *params);
    AcpPropagationSummary initialize_acp_layout(
        const std::vector<Vec3> &mesh_points,
        const std::vector<Vec3> &local_points,
        const std::vector<std::pair<int, int>> &edges,
        const Vec3 &x_axis,
        const Vec3 &y_axis,
        double nominal_edge_length,
        PyObject *params,
        std::vector<Vec3> &fabric_points);
    void build_acp_edge_objective(
        const std::vector<Vec3> &local_points,
        const std::vector<std::pair<int, int>> &edges,
        double nominal_edge_length,
        const Vec3 &primary_axis,
        const std::string &material_model,
        double ud_coefficient,
        bool thickness_correction,
        std::vector<double> &edge_targets,
        std::vector<double> &edge_weights);
    Vec3 centroid(const std::vector<Vec3> &points);
    void build_basis(
        const std::vector<Vec3> &points,
        const std::vector<std::array<int, 3>> &faces,
        Vec3 &normal,
        Vec3 &x_axis,
        Vec3 &y_axis);
    Vec3 project_point(
        const Vec3 &point,
        const Vec3 &origin,
        const Vec3 &x_axis,
        const Vec3 &y_axis,
        const Vec3 &normal);
    std::vector<std::vector<int>> boundary_loops(
        const std::vector<std::array<int, 3>> &faces);
    std::vector<std::array<double, 3>> face_strains(
        const std::vector<std::array<int, 3>> &faces,
        const std::vector<Vec3> &local_points,
        const Vec3 &normal);
    std::vector<int> order_quad_indices(
        const std::vector<int> &indices,
        const std::vector<Vec3> &points);
    std::vector<std::vector<int>> extract_quads(
        const std::vector<std::array<int, 3>> &faces,
        const std::vector<Vec3> &points);
    std::vector<Vec3> loop_to_points(
        const std::vector<int> &loop,
        const std::vector<Vec3> &fabric_points);
    std::array<std::array<double, 2>, 4> quad_poly2d(const std::vector<Vec3> &points, const std::vector<int> &quad);
    std::vector<AtlasChartBuild> split_into_non_overlapping_charts(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::vector<int>> &quads,
        int &overlap_rejections);
    double point_set_span(const std::vector<Vec3> &pts);
    void transfer_layout_between_faces(const FaceSample &prev, FaceSample &curr);
    bool ensure_part_module_loaded();
    FaceSample sample_face(
        const TopoDS_Face &face,
        double max_length,
        CurrentNodeSolverMode solver_mode,
        double max_adjacent_normal_angle,
        double max_local_fold_ratio,
        double max_shear_angle,
        bool incremental_growth,
        bool surface_spacing_refine,
        int surface_spacing_relax_iterations,
        ExperimentalSolveStats *experimental_stats);
    std::string solver_algorithm_from_params(PyObject *params_copy);
    SolverAlgorithmProfile solver_algorithm_profile_from_params(PyObject *params_copy);
    int solver_iterations_from_params(PyObject *params_copy);
    void attach_solver_metadata(PyObject *result, PyObject *params_copy, const char *termination_reason, bool converged, PyObject *diagnostics);
    void set_diag_long(PyObject *diagnostics, const char *key, long value);
    void set_diag_double(PyObject *diagnostics, const char *key, double value);
    void set_diag_string(PyObject *diagnostics, const char *key, const char *value);
    void add_solver_diagnostics(
        PyObject *diagnostics,
        PyObject *params_copy,
        long face_count,
        long point_count,
        long triangle_count,
        long quad_count,
        long orientation_break_count,
        int edge_violations,
        double max_rel_error,
        double rel_tol,
        bool rel_tol_from_parameter,
        int max_iterations,
        const std::vector<double> &residual_history,
        bool acp_energy_mode,
        const AcpPropagationSummary &acp_summary,
        long coverage_point_count,
        long surface_spacing_active_nodes,
        long surface_spacing_total_nodes,
        long surface_spacing_frontier_pops,
        long surface_spacing_frontier_accepts,
        long surface_spacing_candidate_quads,
        long surface_spacing_selected_quads);
    void set_result_common_fields(
        PyObject *result,
        PyObject *fabric_points,
        PyObject *warp_weft_points,
        PyObject *fabric_quads,
        PyObject *boundary_loops,
        PyObject *warp_weft_boundary_loops,
        PyObject *strains,
        PyObject *mesh_points,
        PyObject *mesh_faces,
        PyObject *face_frames,
        PyObject *orientation_breaks,
        PyObject *atlas_charts,
        const Vec3 &origin,
        const Vec3 &normal,
        const Vec3 &x_axis,
        const Vec3 &y_axis,
        PyObject *params_copy);
    PyObject *build_empty_geometry_result(const char *error, PyObject *params_copy);

} // namespace fishnet_internal
