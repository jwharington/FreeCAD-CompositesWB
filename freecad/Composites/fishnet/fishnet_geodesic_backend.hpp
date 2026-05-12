#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <array>
#include <vector>

#include "fishnet_options_api.hpp"
#include "fishnet_primitives.hpp"

namespace fishnet_internal
{

    bool geodesic_heat_requested(const SolverAlgorithmProfile &profile);

    // Temporary scaffold while geometry-central integration is being wired.
    // Returns a standard invalid solver payload with guidance. The mesh
    // input arrays (points + triangles) are inspected to publish additive
    // input-shape diagnostics; the scaffold itself remains invalid.
    PyObject *build_geodesic_heat_scaffold_result(
        PyObject *params_copy,
        const SolverAlgorithmProfile &algorithm_profile,
        const NormalizedParams &normalized_params,
        const char *input_kind,
        const std::vector<Vec3> &points,
        const std::vector<std::array<int, 3>> &triangles);

} // namespace fishnet_internal
