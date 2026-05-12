#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <cmath>
#include <utility>

#include "fishnet_options_api.hpp"

namespace fishnet_internal
{

    namespace
    {
        constexpr int kDefaultRelaxIterations = 120;
        constexpr double kDefaultSurfaceSpacingStrictTolerance = 0.02;
    }

    std::pair<double, bool> resolve_edge_rel_tolerance(const NormalizedParams &params)
    {
        const SurfaceSpacingStrictPolicy strict_policy = resolve_surface_spacing_strict_policy(params);
        if (strict_policy.enabled)
        {
            return {strict_policy.tolerance, strict_policy.tolerance_from_parameter};
        }
        return {params.edge_length_tolerance, params.edge_length_tolerance_from_parameter};
    }

    std::pair<double, bool> resolve_edge_rel_tolerance(PyObject *params_copy)
    {
        return resolve_edge_rel_tolerance(normalize_params(params_copy));
    }

    int resolve_relax_iterations(const NormalizedParams &params)
    {
        int relax_iterations = params.steps;
        if (relax_iterations <= 0)
        {
            relax_iterations = kDefaultRelaxIterations;
        }
        return relax_iterations;
    }

    int resolve_relax_iterations(PyObject *params_copy)
    {
        return resolve_relax_iterations(normalize_params(params_copy));
    }

    double read_nominal_edge_length(const NormalizedParams &params)
    {
        return params.fabric_spacing;
    }

    double read_nominal_edge_length(PyObject *params_copy)
    {
        return read_nominal_edge_length(normalize_params(params_copy));
    }

    SurfaceSpacingStrictPolicy resolve_surface_spacing_strict_policy(const NormalizedParams &params)
    {
        SurfaceSpacingStrictPolicy policy;
        policy.enabled = params.algorithm_profile.surface_spacing_mode && params.surface_spacing_strict;

        if (!policy.enabled)
        {
            policy.tolerance = params.edge_length_tolerance;
            policy.tolerance_from_parameter = params.edge_length_tolerance_from_parameter;
            policy.fail_on_violation = false;
            return policy;
        }

        policy.fail_on_violation = params.surface_spacing_fail_on_violation;
        policy.tolerance = kDefaultSurfaceSpacingStrictTolerance;
        policy.tolerance_from_parameter = false;

        if (params.surface_spacing_edge_tolerance_from_parameter &&
            std::isfinite(params.surface_spacing_edge_tolerance) &&
            params.surface_spacing_edge_tolerance > 0.0)
        {
            policy.tolerance = params.surface_spacing_edge_tolerance;
            policy.tolerance_from_parameter = true;
        }
        else if (params.edge_length_tolerance_from_parameter &&
                 std::isfinite(params.edge_length_tolerance) &&
                 params.edge_length_tolerance > 0.0)
        {
            policy.tolerance = params.edge_length_tolerance;
            policy.tolerance_from_parameter = true;
        }

        return policy;
    }

    SurfaceSpacingStrictPolicy resolve_surface_spacing_strict_policy(PyObject *params_copy)
    {
        return resolve_surface_spacing_strict_policy(normalize_params(params_copy));
    }

} // namespace fishnet_internal
