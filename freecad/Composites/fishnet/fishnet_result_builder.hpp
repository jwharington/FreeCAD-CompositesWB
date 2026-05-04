#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <array>
#include <vector>

#include "fishnet_options_api.hpp"
#include "fishnet_sampling_api.hpp"

namespace fishnet_internal
{

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
        const std::vector<double> &combined_objective_history;
        const AcpPropagationSummary &acp_summary;
        const AcpObjectiveSummary &objective_summary;
        const std::vector<std::pair<int, int>> &constrained_edges;
        const std::vector<double> &edge_targets;
    };

    PyObject *build_geometry_result_object(const GeometryResultBuildInput &input);

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
        const std::vector<double> &combined_objective_history;
        const AcpPropagationSummary &acp_summary;
        const AcpObjectiveSummary &objective_summary;
    };

    PyObject *build_mesh_result_object(const MeshResultBuildInput &input);

} // namespace fishnet_internal
