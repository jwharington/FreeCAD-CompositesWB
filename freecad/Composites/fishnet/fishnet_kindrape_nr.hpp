#pragma once

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal
{

    struct Step2NrSolveResult
    {
        bool success{false};
        bool converged{false};
        bool used_fallback{false};
        bool infeasible{false};
        int iterations{0};
        double objective_initial{0.0};
        double objective_final{0.0};
        double signed_shear_initial_deg{0.0};
        double signed_shear_final_deg{0.0};
        double signed_shear_target_deg{0.0};
        Vec3 solved_point{0.0, 0.0, 0.0};
    };

    Step2NrSolveResult solve_step2_generator_cell_nr(
        const Vec3 &current_point,
        const Vec3 &reference_vector,
        const Vec3 &initial_direction,
        double nominal_edge_length,
        double target_pre_shear_deg);

} // namespace fishnet_internal
