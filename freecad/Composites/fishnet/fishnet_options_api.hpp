#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <string>
#include <utility>
#include <vector>

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal
{

    struct AcpPropagationSummary
    {
        int seed_index{0};
        int primary_assigned{0};
        int orthogonal_assigned{0};
        int fill_assigned{0};
        int step1_assigned{0};
        int step2_assigned{0};
        int step3_assigned{0};
        int step2_nr_attempts{0};
        int step2_nr_converged{0};
        int step2_nr_fallback_count{0};
        int step2_nr_infeasible{0};
        int step2_nr_decrease_count{0};
        int step2_nr_iterations{0};
        double step2_nr_initial_objective_sum{0.0};
        double step2_nr_final_objective_sum{0.0};
        int step2_nr_signed_shear_count{0};
        double step2_nr_signed_shear_sum_deg{0.0};
        double step2_nr_signed_shear_target_error_sum_deg{0.0};
        double propagation_pre_shear_deg{0.0};
        double propagation_pre_shear_slope{0.0};
        int propagation_step3_pre_shear_adjust_count{0};
        double propagation_step3_pre_shear_adjust_sum{0.0};
        Vec3 primary_axis{1.0, 0.0, 0.0};
        Vec3 orthogonal_axis{0.0, 1.0, 0.0};
        std::vector<std::string> stage_trace;
    };

    struct AcpObjectiveSummary
    {
        long edge_count{0};
        long primary_edge_count{0};
        long transverse_edge_count{0};
        long bias_edge_count{0};
        long positive_bias_edge_count{0};
        long negative_bias_edge_count{0};
        long cell_count{0};
        double objective_p_norm{6.0};
        double objective_pre_shear_deg{0.0};
        double objective_shear_weight{1.0};
        double objective_fiber_weight{0.25};
        double objective_cell_gain{0.0};
        double target_scale_mean{1.0};
        double target_scale_min{1.0};
        double target_scale_max{1.0};
        double weight_mean{1.0};
        double weight_min{1.0};
        double weight_max{1.0};
        double primary_target_scale_mean{1.0};
        double transverse_target_scale_mean{1.0};
        double bias_target_scale_mean{1.0};
        double primary_weight_mean{1.0};
        double transverse_weight_mean{1.0};
        double bias_weight_mean{1.0};
        double positive_bias_target_scale_mean{1.0};
        double negative_bias_target_scale_mean{1.0};
        double signed_bias_target_asymmetry{0.0};
        double signed_shear_proxy_mean{0.0};
        double abs_shear_proxy_mean{0.0};
        double cell_shear_abs_mean_deg{0.0};
        double cell_shear_signed_mean_deg{0.0};
        double cell_shear_target_error_mean_deg{0.0};
        double cell_fiber_angle_mean_deg{0.0};
        double cell_combined_objective_mean{0.0};
        double target_anisotropy_ratio{1.0};
        double weight_anisotropy_ratio{1.0};
    };

    struct SolverAlgorithmProfile
    {
        std::string requested_algorithm{"acp_energy"};
        bool acp_energy_mode{false};
        bool surface_spacing_mode{false};
        std::string acp_strategy{"none"};
    };

    bool try_parse_param_vec3(PyObject *params, const char *key, Vec3 &out);
    double param_double(PyObject *params, const char *key, double fallback);
    bool param_bool(PyObject *params, const char *key, bool fallback);
    std::string param_string(PyObject *params, const char *key, const char *fallback);

    std::string solver_algorithm_from_params(PyObject *params_copy);
    SolverAlgorithmProfile solver_algorithm_profile_from_params(PyObject *params_copy);
    int solver_iterations_from_params(PyObject *params_copy);
    void attach_solver_metadata(PyObject *result, PyObject *params_copy, const char *termination_reason, bool converged, PyObject *diagnostics);

    std::pair<double, bool> resolve_edge_rel_tolerance(PyObject *params_copy);
    int resolve_relax_iterations(PyObject *params_copy);
    double read_nominal_edge_length(PyObject *params_copy);

} // namespace fishnet_internal
