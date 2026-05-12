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
        Vec3 seed_point_used{0.0, 0.0, 0.0};
        Vec3 draping_direction_used{1.0, 0.0, 0.0};
        std::string sweep_analysis_seed_source{"unresolved"};
        double sweep_analysis_seed_point_request_distance{0.0};
        std::string sweep_analysis_draping_direction_source{"default_unit_x"};
        double sweep_analysis_draping_direction_request_alignment_cos{0.0};
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
        std::vector<double> generator_objective_history;
        std::vector<double> generator_shear_history;
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

        // Paper-alignment Phase 1 scaffold metadata.
        std::string paper_alignment_requested{"off"};
        std::string paper_alignment_effective{"off"};
        std::string paper_alignment_fallback{"none"};
        std::string paper_alignment_profile_requested{"default"};
        std::string paper_alignment_profile_effective{"default"};
        bool paper_alignment_enabled{false};
    };

    struct NormalizedParams
    {
        SolverAlgorithmProfile algorithm_profile{};

        int steps{0};
        double fabric_spacing{0.0};
        double max_length{0.0};

        bool has_max_adjacent_normal_angle{false};
        double max_adjacent_normal_angle{0.0};

        bool has_max_local_fold_ratio{false};
        double max_local_fold_ratio{0.0};

        bool has_max_shear_angle_deg{false};
        double max_shear_angle_deg{0.0};

        bool has_surface_spacing_relax_iterations{false};
        int surface_spacing_relax_iterations{0};

        bool boundary_extend{true};
        bool boundary_trim{true};

        bool edge_length_tolerance_from_parameter{false};
        double edge_length_tolerance{0.0};

        bool surface_spacing_strict{false};
        bool surface_spacing_edge_tolerance_from_parameter{false};
        double surface_spacing_edge_tolerance{0.02};
        bool surface_spacing_fail_on_violation{false};

        std::string material_model{"woven"};
        double ud_coefficient{0.0};
        bool thickness_correction{false};

        double objective_p_norm{6.0};
        double pre_shear_deg{0.0};

        bool has_objective_shear_weight{false};
        double objective_shear_weight{1.0};

        bool has_objective_fiber_weight{false};
        double objective_fiber_weight{0.25};

        bool has_objective_cell_gain{false};
        double objective_cell_gain{0.0};

        bool has_seed{false};
        int seed{0};

        bool has_seed_point{false};
        Vec3 seed_point{0.0, 0.0, 0.0};

        bool has_draping_direction{false};
        Vec3 draping_direction{1.0, 0.0, 0.0};
    };

    struct SurfaceSpacingStrictPolicy
    {
        bool enabled{false};
        bool fail_on_violation{false};
        bool tolerance_from_parameter{false};
        double tolerance{0.02};
    };

    bool try_parse_param_vec3(PyObject *params, const char *key, Vec3 &out);
    double param_double(PyObject *params, const char *key, double fallback);
    bool param_bool(PyObject *params, const char *key, bool fallback);
    std::string param_string(PyObject *params, const char *key, const char *fallback);

    NormalizedParams normalize_params(PyObject *params_copy);

    std::string solver_algorithm_from_params(PyObject *params_copy);
    SolverAlgorithmProfile solver_algorithm_profile_from_params(PyObject *params_copy);
    int solver_iterations_from_params(PyObject *params_copy);
    void attach_solver_metadata(PyObject *result, PyObject *params_copy, const char *termination_reason, bool converged, PyObject *diagnostics);

    std::pair<double, bool> resolve_edge_rel_tolerance(PyObject *params_copy);
    int resolve_relax_iterations(PyObject *params_copy);
    double read_nominal_edge_length(PyObject *params_copy);

    SurfaceSpacingStrictPolicy resolve_surface_spacing_strict_policy(const NormalizedParams &params);
    SurfaceSpacingStrictPolicy resolve_surface_spacing_strict_policy(PyObject *params_copy);

} // namespace fishnet_internal
