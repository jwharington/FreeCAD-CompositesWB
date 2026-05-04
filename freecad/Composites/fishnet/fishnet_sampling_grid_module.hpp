#pragma once

#include <vector>

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal
{

    /// Owns all mutable grid-state invariants for one face-sampling run.
    /// Passed by reference to node-update and surface-relaxation modules so
    /// callers never need to coordinate the individual grid vectors.
    struct SamplingGridState
    {
        int divisions{0};
        double target_spacing_len{0.0};
        int seed_i_uv{-1};
        int seed_j_uv{-1};
        std::vector<Vec3> seed_points;
        std::vector<std::vector<int>> grid_indices;
        std::vector<std::vector<double>> grid_u;
        std::vector<std::vector<double>> grid_v;
        std::vector<std::vector<Vec3>> grid_normals;
        std::vector<std::vector<unsigned char>> active_nodes;
    };

} // namespace fishnet_internal
