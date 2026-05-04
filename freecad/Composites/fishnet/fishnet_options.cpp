#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "fishnet_options.hpp"

#include <cmath>
#include <cstdio>
#include <string>

#include "fishnet_options_api.hpp"
#include "fishnet_result_api.hpp"

namespace fishnet_internal
{

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

    // ─────────────────────────────────────────────────────────────────────────

    namespace
    {

        constexpr double kHalfPi = 1.5707963267948966;
        constexpr double kThirtyDegreesInRadians = 0.5235987755982988;
        constexpr double kDegreesToRadians = 0.017453292519943295;
        constexpr int kDefaultSurfaceSpacingRelaxIterationsAcp = 12;
        constexpr int kDefaultRelaxIterations = 120;

    } // namespace

    DrapingAlgorithmPolicy::DrapingAlgorithmPolicy(PyObject *params_copy)
        : requested_algorithm_(solver_algorithm_from_params(params_copy))
    {
    }

    bool DrapingAlgorithmPolicy::supported() const
    {
        return requested_algorithm_ == "acp_energy";
    }

    PyObject *DrapingAlgorithmPolicy::build_unsupported_result(PyObject *params_copy) const
    {
        char message[256];
        std::snprintf(
            message,
            sizeof(message),
            "unsupported draping algorithm: %s (supported: acp_energy)",
            requested_algorithm_.c_str());
        return build_empty_geometry_result(message, params_copy);
    }

    GeometrySolverConfig build_geometry_solver_config(PyObject *params_copy, size_t native_face_count)
    {
        GeometrySolverConfig config;
        const SolverAlgorithmProfile algorithm_profile = solver_algorithm_profile_from_params(params_copy);
        config.algorithm = algorithm_profile.requested_algorithm;
        config.acp_surface_spacing_mode = algorithm_profile.surface_spacing_mode;
        config.acp_energy_mode = algorithm_profile.acp_energy_mode;

        config.solver_mode = CurrentNodeSolverMode::SphereSurface;

        bool single_face_run = (native_face_count == 1);
        config.max_adjacent_normal_angle = single_face_run ? kHalfPi : 0.0;
        if (PyObject *angle_obj = PyDict_GetItemString(params_copy, "max_adjacent_normal_angle"))
        {
            double parsed_angle = PyFloat_AsDouble(angle_obj);
            if (!PyErr_Occurred() && std::isfinite(parsed_angle) && parsed_angle > 0.0)
            {
                config.max_adjacent_normal_angle = parsed_angle;
            }
            else
            {
                PyErr_Clear();
            }
        }

        config.max_local_fold_ratio = single_face_run ? 1.7 : 0.0;
        if (PyObject *ratio_obj = PyDict_GetItemString(params_copy, "max_local_fold_ratio"))
        {
            double parsed_ratio = PyFloat_AsDouble(ratio_obj);
            if (!PyErr_Occurred() && std::isfinite(parsed_ratio) && parsed_ratio > 1.0)
            {
                config.max_local_fold_ratio = parsed_ratio;
            }
            else
            {
                PyErr_Clear();
            }
        }

        config.max_shear_angle = single_face_run ? kThirtyDegreesInRadians : -1.0;
        if (PyObject *shear_obj = PyDict_GetItemString(params_copy, "max_shear_angle_deg"))
        {
            double parsed_deg = PyFloat_AsDouble(shear_obj);
            if (!PyErr_Occurred() && std::isfinite(parsed_deg) && parsed_deg >= 0.0)
            {
                config.max_shear_angle = parsed_deg * kDegreesToRadians;
            }
            else
            {
                PyErr_Clear();
            }
        }

        config.surface_spacing_refine = config.acp_surface_spacing_mode;

        config.surface_spacing_relax_iterations = config.acp_surface_spacing_mode ? kDefaultSurfaceSpacingRelaxIterationsAcp : 3;
        if (PyObject *iters_obj = PyDict_GetItemString(params_copy, "surface_spacing_relax_iterations"))
        {
            long parsed_iters = PyLong_AsLong(iters_obj);
            if (!PyErr_Occurred() && parsed_iters > 0)
            {
                config.surface_spacing_relax_iterations = static_cast<int>(parsed_iters);
            }
            else
            {
                PyErr_Clear();
            }
        }

        if (PyObject *max_length_obj = PyDict_GetItemString(params_copy, "max_length"))
        {
            config.sample_max_length = PyFloat_AsDouble(max_length_obj);
            if (PyErr_Occurred())
            {
                PyErr_Clear();
                config.sample_max_length = 0.0;
            }
        }
        if (PyObject *spacing_obj = PyDict_GetItemString(params_copy, "fabric_spacing"))
        {
            config.nominal_spacing = PyFloat_AsDouble(spacing_obj);
            if (PyErr_Occurred())
            {
                PyErr_Clear();
                config.nominal_spacing = 0.0;
            }
        }
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

    std::pair<double, bool> resolve_edge_rel_tolerance(PyObject *params_copy)
    {
        double rel_tol = kDefaultEdgeLengthTolerance;
        bool rel_tol_from_parameter = false;
        if (PyObject *tol_obj = PyDict_GetItemString(params_copy, "edge_length_tolerance"))
        {
            rel_tol_from_parameter = true;
            double parsed_tol = PyFloat_AsDouble(tol_obj);
            if (!PyErr_Occurred() && std::isfinite(parsed_tol) && parsed_tol > 0.0)
            {
                rel_tol = parsed_tol;
            }
            else
            {
                PyErr_Clear();
            }
        }
        return {rel_tol, rel_tol_from_parameter};
    }

    int resolve_relax_iterations(PyObject *params_copy)
    {
        int relax_iterations = solver_iterations_from_params(params_copy);
        if (relax_iterations <= 0)
        {
            relax_iterations = kDefaultRelaxIterations;
        }
        return relax_iterations;
    }

    double read_nominal_edge_length(PyObject *params_copy)
    {
        double nominal_edge_length = 0.0;
        if (PyObject *spacing_obj = PyDict_GetItemString(params_copy, "fabric_spacing"))
        {
            nominal_edge_length = PyFloat_AsDouble(spacing_obj);
            if (PyErr_Occurred())
            {
                PyErr_Clear();
                nominal_edge_length = 0.0;
            }
        }
        return nominal_edge_length;
    }

} // namespace fishnet_internal
