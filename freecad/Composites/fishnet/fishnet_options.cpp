#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "fishnet_options.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <string>

#include "fishnet_options_api.hpp"
#include "fishnet_result_api.hpp"

namespace fishnet_internal
{

    namespace
    {
        constexpr double kHalfPi = 1.5707963267948966;
        constexpr double kThirtyDegreesInRadians = 0.5235987755982988;
        constexpr double kDegreesToRadians = 0.017453292519943295;
        constexpr int kDefaultSurfaceSpacingRelaxIterationsAcp = 12;
        constexpr int kDefaultRelaxIterations = 120;
        constexpr double kDefaultSurfaceSpacingStrictTolerance = 0.02;

        bool dict_has_key(PyObject *params, const char *key)
        {
            if (!params || !PyDict_Check(params) || !key)
            {
                return false;
            }
            return PyDict_GetItemString(params, key) != nullptr;
        }

        std::string lowercase_copy(std::string value)
        {
            std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c)
                           { return static_cast<char>(std::tolower(c)); });
            return value;
        }

        std::string parse_paper_alignment_mode(std::string value)
        {
            value = lowercase_copy(value);
            if (value.empty() || value == "off" || value == "none" || value == "disabled" || value == "false")
            {
                return "off";
            }
            if (value == "diagnostics" || value == "diagnostic" || value == "diagnostics_only" || value == "diagnostics-only")
            {
                return "diagnostics_only";
            }
            if (value == "hybrid" || value == "hybrid_metric_cell" || value == "hybrid-metric-cell" || value == "metric_cell")
            {
                return "hybrid_metric_cell";
            }
            return "";
        }

        std::string parse_paper_alignment_profile(std::string value)
        {
            value = lowercase_copy(value);
            if (value.empty() || value == "default")
            {
                return "default";
            }
            if (value == "off" || value == "none" || value == "disabled")
            {
                return "off";
            }
            if (value == "diagnostics" || value == "diagnostics_only" || value == "diagnostics-only" || value == "phase1_diagnostics")
            {
                return "diagnostics_only";
            }
            if (value == "phase1" || value == "paper_alignment_phase1" || value == "hybrid_metric_cell")
            {
                return "phase1";
            }
            return "";
        }

        void apply_paper_alignment_profile(PyObject *params_copy, SolverAlgorithmProfile &profile)
        {
            const bool has_mode = dict_has_key(params_copy, "paper_alignment_mode");
            const std::string raw_mode = param_string(params_copy, "paper_alignment_mode", "");
            const std::string parsed_mode = parse_paper_alignment_mode(raw_mode);

            const bool has_profile = dict_has_key(params_copy, "paper_alignment_profile");
            const std::string raw_profile = param_string(params_copy, "paper_alignment_profile", "");
            const std::string parsed_profile = parse_paper_alignment_profile(raw_profile);

            const bool has_enabled_flag = dict_has_key(params_copy, "paper_alignment");
            const bool paper_alignment_enabled_flag = param_bool(params_copy, "paper_alignment", false);

            std::string requested_mode = "off";
            std::string requested_profile = "default";
            std::string fallback = "none";

            if (has_mode)
            {
                if (!parsed_mode.empty())
                {
                    requested_mode = parsed_mode;
                }
                else
                {
                    fallback = "invalid_requested_mode";
                }
            }
            else if (has_enabled_flag && paper_alignment_enabled_flag)
            {
                requested_mode = "diagnostics_only";
            }

            if (has_profile)
            {
                if (!parsed_profile.empty())
                {
                    requested_profile = parsed_profile;
                }
                else if (fallback == "none")
                {
                    fallback = "invalid_requested_profile";
                }
            }

            if (!has_mode)
            {
                if (requested_profile == "phase1")
                {
                    requested_mode = "hybrid_metric_cell";
                }
                else if (requested_profile == "diagnostics_only")
                {
                    requested_mode = "diagnostics_only";
                }
                else if (requested_profile == "off")
                {
                    requested_mode = "off";
                }
            }

            std::string effective_mode = requested_mode;
            std::string effective_profile = requested_profile;

            if (!profile.acp_energy_mode && requested_mode != "off")
            {
                effective_mode = "off";
                effective_profile = "default";
                fallback = "requires_acp_energy_algorithm";
            }
            else if (requested_mode == "hybrid_metric_cell")
            {
                // Phase 1 hybrid hook: keep interior ACP behavior unchanged, but
                // activate directional boundary-reference seeding.
                effective_mode = "hybrid_metric_cell";
                effective_profile = (requested_profile == "default") ? "phase1" : requested_profile;
            }

            if (effective_mode == "off")
            {
                effective_profile = "default";
            }
            else if (effective_profile == "default")
            {
                effective_profile = effective_mode == "hybrid_metric_cell" ? "phase1" : "diagnostics_only";
            }

            profile.paper_alignment_requested = requested_mode;
            profile.paper_alignment_effective = effective_mode;
            profile.paper_alignment_fallback = fallback;
            profile.paper_alignment_profile_requested = requested_profile;
            profile.paper_alignment_profile_effective = effective_profile;
            profile.paper_alignment_enabled = (effective_mode != "off");
        }

    } // namespace

    // ── Typed parameter accessors ─────────────────────────────────────────────

    double param_double(PyObject *params, const char *key, double fallback)
    {
        if (!params || !PyDict_Check(params) || !key)
        {
            return fallback;
        }
        PyObject *obj = PyDict_GetItemString(params, key);
        if (!obj)
        {
            return fallback;
        }
        double parsed = PyFloat_AsDouble(obj);
        if (PyErr_Occurred() || !std::isfinite(parsed))
        {
            PyErr_Clear();
            return fallback;
        }
        return parsed;
    }

    bool param_bool(PyObject *params, const char *key, bool fallback)
    {
        if (!params || !PyDict_Check(params) || !key)
        {
            return fallback;
        }
        PyObject *obj = PyDict_GetItemString(params, key);
        if (!obj)
        {
            return fallback;
        }
        int truthy = PyObject_IsTrue(obj);
        if (truthy < 0)
        {
            PyErr_Clear();
            return fallback;
        }
        return truthy != 0;
    }

    std::string param_string(PyObject *params, const char *key, const char *fallback)
    {
        if (!params || !PyDict_Check(params) || !key)
        {
            return fallback ? std::string(fallback) : std::string();
        }
        PyObject *obj = PyDict_GetItemString(params, key);
        if (!obj || !PyUnicode_Check(obj))
        {
            return fallback ? std::string(fallback) : std::string();
        }
        const char *value = PyUnicode_AsUTF8(obj);
        if (!value)
        {
            PyErr_Clear();
            return fallback ? std::string(fallback) : std::string();
        }
        return std::string(value);
    }

    bool try_parse_param_vec3(PyObject *params, const char *key, Vec3 &out)
    {
        if (!params || !PyDict_Check(params) || !key)
        {
            return false;
        }
        PyObject *obj = PyDict_GetItemString(params, key);
        if (!obj)
        {
            return false;
        }
        PyObject *seq = PySequence_Fast(obj, "vector parameter must be a sequence");
        if (!seq)
        {
            PyErr_Clear();
            return false;
        }
        bool ok = false;
        if (PySequence_Fast_GET_SIZE(seq) >= 3)
        {
            PyObject **items = PySequence_Fast_ITEMS(seq);
            out.x = PyFloat_AsDouble(items[0]);
            out.y = PyFloat_AsDouble(items[1]);
            out.z = PyFloat_AsDouble(items[2]);
            ok = !PyErr_Occurred() && std::isfinite(out.x) && std::isfinite(out.y) && std::isfinite(out.z);
        }
        if (PyErr_Occurred())
        {
            PyErr_Clear();
        }
        Py_DECREF(seq);
        return ok;
    }

    NormalizedParams normalize_params(PyObject *params_copy)
    {
        NormalizedParams normalized;
        normalized.algorithm_profile = solver_algorithm_profile_from_params(params_copy);
        apply_paper_alignment_profile(params_copy, normalized.algorithm_profile);

        normalized.steps = solver_iterations_from_params(params_copy);
        normalized.fabric_spacing = param_double(params_copy, "fabric_spacing", 0.0);
        normalized.max_length = param_double(params_copy, "max_length", 0.0);

        normalized.has_max_adjacent_normal_angle = dict_has_key(params_copy, "max_adjacent_normal_angle");
        normalized.max_adjacent_normal_angle = param_double(params_copy, "max_adjacent_normal_angle", 0.0);

        normalized.has_max_local_fold_ratio = dict_has_key(params_copy, "max_local_fold_ratio");
        normalized.max_local_fold_ratio = param_double(params_copy, "max_local_fold_ratio", 0.0);

        normalized.has_max_shear_angle_deg = dict_has_key(params_copy, "max_shear_angle_deg");
        normalized.max_shear_angle_deg = param_double(params_copy, "max_shear_angle_deg", 0.0);

        normalized.has_surface_spacing_relax_iterations = dict_has_key(params_copy, "surface_spacing_relax_iterations");
        if (normalized.has_surface_spacing_relax_iterations)
        {
            PyObject *iters_obj = PyDict_GetItemString(params_copy, "surface_spacing_relax_iterations");
            if (iters_obj)
            {
                long parsed_iters = PyLong_AsLong(iters_obj);
                if (!PyErr_Occurred() && parsed_iters > 0)
                {
                    normalized.surface_spacing_relax_iterations = static_cast<int>(parsed_iters);
                }
                else
                {
                    PyErr_Clear();
                }
            }
        }

        normalized.boundary_extend = param_bool(params_copy, "boundary_extend", true);
        normalized.boundary_trim = param_bool(params_copy, "boundary_trim", true);

        normalized.edge_length_tolerance_from_parameter = dict_has_key(params_copy, "edge_length_tolerance");
        normalized.edge_length_tolerance = kDefaultEdgeLengthTolerance;
        if (normalized.edge_length_tolerance_from_parameter)
        {
            const double parsed_tol = param_double(params_copy, "edge_length_tolerance", kDefaultEdgeLengthTolerance);
            if (std::isfinite(parsed_tol) && parsed_tol > 0.0)
            {
                normalized.edge_length_tolerance = parsed_tol;
            }
        }

        normalized.surface_spacing_strict = param_bool(params_copy, "surface_spacing_strict", false);
        normalized.surface_spacing_edge_tolerance_from_parameter = dict_has_key(params_copy, "surface_spacing_edge_tolerance");
        normalized.surface_spacing_edge_tolerance = kDefaultSurfaceSpacingStrictTolerance;
        if (normalized.surface_spacing_edge_tolerance_from_parameter)
        {
            const double parsed_strict_tol = param_double(params_copy, "surface_spacing_edge_tolerance", kDefaultSurfaceSpacingStrictTolerance);
            if (std::isfinite(parsed_strict_tol) && parsed_strict_tol > 0.0)
            {
                normalized.surface_spacing_edge_tolerance = parsed_strict_tol;
            }
        }

        const bool has_surface_spacing_fail_on_violation = dict_has_key(params_copy, "surface_spacing_fail_on_violation");
        normalized.surface_spacing_fail_on_violation = has_surface_spacing_fail_on_violation
                                                           ? param_bool(params_copy, "surface_spacing_fail_on_violation", normalized.surface_spacing_strict)
                                                           : normalized.surface_spacing_strict;

        normalized.material_model = param_string(params_copy, "material_model", "woven");
        normalized.ud_coefficient = param_double(params_copy, "ud_coefficient", 0.0);
        normalized.thickness_correction = param_bool(params_copy, "thickness_correction", false);
        normalized.objective_p_norm = param_double(params_copy, "objective_p_norm", 6.0);
        normalized.pre_shear_deg = param_double(params_copy, "pre_shear_deg", 0.0);

        normalized.has_objective_shear_weight = dict_has_key(params_copy, "objective_shear_weight");
        normalized.objective_shear_weight = param_double(params_copy, "objective_shear_weight", 1.0);

        normalized.has_objective_fiber_weight = dict_has_key(params_copy, "objective_fiber_weight");
        normalized.objective_fiber_weight = param_double(params_copy, "objective_fiber_weight", 0.25);

        normalized.has_objective_cell_gain = dict_has_key(params_copy, "objective_cell_gain");
        normalized.objective_cell_gain = param_double(params_copy, "objective_cell_gain", 0.0);

        if (dict_has_key(params_copy, "seed"))
        {
            PyObject *seed_obj = PyDict_GetItemString(params_copy, "seed");
            if (seed_obj)
            {
                long seed_long = PyLong_AsLong(seed_obj);
                if (!PyErr_Occurred() && seed_long >= 0)
                {
                    normalized.has_seed = true;
                    normalized.seed = static_cast<int>(seed_long);
                }
                else
                {
                    PyErr_Clear();
                }
            }
        }

        normalized.has_seed_point = try_parse_param_vec3(params_copy, "seed_point", normalized.seed_point);
        normalized.has_draping_direction = try_parse_param_vec3(params_copy, "draping_direction", normalized.draping_direction);

        return normalized;
    }

    DrapingAlgorithmPolicy::DrapingAlgorithmPolicy(PyObject *params_copy)
        : requested_algorithm_(solver_algorithm_from_params(params_copy))
    {
    }

    DrapingAlgorithmPolicy::DrapingAlgorithmPolicy(const NormalizedParams &params)
        : requested_algorithm_(params.algorithm_profile.requested_algorithm)
    {
    }

    bool DrapingAlgorithmPolicy::supported() const
    {
        return requested_algorithm_ == "acp_energy" ||
               requested_algorithm_ == "geodesic_heat" ||
               requested_algorithm_ == "geodesic-heat";
    }

    PyObject *DrapingAlgorithmPolicy::build_unsupported_result(PyObject *params_copy) const
    {
        char message[256];
        std::snprintf(
            message,
            sizeof(message),
            "unsupported draping algorithm: %s (supported: acp_energy, geodesic_heat)",
            requested_algorithm_.c_str());
        return build_empty_geometry_result(message, params_copy);
    }

    GeometrySolverConfig build_geometry_solver_config(const NormalizedParams &params, size_t native_face_count)
    {
        GeometrySolverConfig config;
        config.algorithm = params.algorithm_profile.requested_algorithm;
        config.acp_surface_spacing_mode = params.algorithm_profile.surface_spacing_mode;
        config.acp_energy_mode = params.algorithm_profile.acp_energy_mode;

        config.solver_mode = CurrentNodeSolverMode::SphereSurface;

        const bool single_face_run = (native_face_count == 1);
        config.max_adjacent_normal_angle = single_face_run ? kHalfPi : 0.0;
        if (params.has_max_adjacent_normal_angle &&
            std::isfinite(params.max_adjacent_normal_angle) &&
            params.max_adjacent_normal_angle > 0.0)
        {
            config.max_adjacent_normal_angle = params.max_adjacent_normal_angle;
        }

        config.max_local_fold_ratio = single_face_run ? 1.7 : 0.0;
        if (params.has_max_local_fold_ratio &&
            std::isfinite(params.max_local_fold_ratio) &&
            params.max_local_fold_ratio > 1.0)
        {
            config.max_local_fold_ratio = params.max_local_fold_ratio;
        }

        config.max_shear_angle = single_face_run ? kThirtyDegreesInRadians : -1.0;
        if (params.has_max_shear_angle_deg &&
            std::isfinite(params.max_shear_angle_deg) &&
            params.max_shear_angle_deg >= 0.0)
        {
            config.max_shear_angle = params.max_shear_angle_deg * kDegreesToRadians;
        }

        config.surface_spacing_refine = config.acp_surface_spacing_mode;

        config.surface_spacing_relax_iterations = config.acp_surface_spacing_mode ? kDefaultSurfaceSpacingRelaxIterationsAcp : 3;
        const SurfaceSpacingStrictPolicy strict_policy = resolve_surface_spacing_strict_policy(params);
        config.surface_spacing_strict = strict_policy.enabled;
        config.surface_spacing_fail_on_violation = strict_policy.fail_on_violation;
        config.surface_spacing_edge_tolerance = strict_policy.tolerance;
        config.boundary_extend = params.boundary_extend;
        config.boundary_trim = params.boundary_trim;
        config.paper_alignment_boundary_reference = params.algorithm_profile.paper_alignment_enabled;
        config.paper_alignment_directional_reference =
            params.algorithm_profile.paper_alignment_effective == "hybrid_metric_cell";
        config.paper_alignment_has_reference_direction_request = params.has_draping_direction;
        config.paper_alignment_reference_direction = params.draping_direction;
        if (params.has_surface_spacing_relax_iterations && params.surface_spacing_relax_iterations > 0)
        {
            config.surface_spacing_relax_iterations = params.surface_spacing_relax_iterations;
        }

        config.sample_max_length = params.max_length;
        config.nominal_spacing = params.fabric_spacing;

        if (config.sample_max_length <= 0.0)
        {
            config.sample_max_length = config.nominal_spacing;
        }
        if (config.nominal_spacing <= 0.0)
        {
            config.nominal_spacing = config.sample_max_length;
        }

        return config;
    }

    GeometrySolverConfig build_geometry_solver_config(PyObject *params_copy, size_t native_face_count)
    {
        return build_geometry_solver_config(normalize_params(params_copy), native_face_count);
    }

} // namespace fishnet_internal
