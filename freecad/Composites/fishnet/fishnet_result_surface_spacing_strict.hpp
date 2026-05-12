#pragma once

#include <string>
#include <vector>

#include "fishnet_options_api.hpp"

namespace fishnet_internal
{

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

    SurfaceSpacingStrictVerification enforce_surface_spacing_strict_mode(
        const SurfaceSpacingStrictPolicy &strict_policy,
        bool surface_spacing_mode,
        const std::vector<Vec3> &points,
        std::vector<std::vector<int>> &quads,
        double target_spacing);

} // namespace fishnet_internal
