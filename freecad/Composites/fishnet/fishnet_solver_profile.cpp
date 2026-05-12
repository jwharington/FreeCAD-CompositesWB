#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <cctype>
#include <string>

#include "fishnet_options_api.hpp"

namespace fishnet_internal
{

    namespace
    {

        std::string lowercase_copy(std::string value)
        {
            std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c)
                           { return static_cast<char>(std::tolower(c)); });
            return value;
        }

        bool is_acp_energy_algorithm_name(const std::string &algorithm)
        {
            return algorithm == "acp_energy";
        }

        bool is_geodesic_heat_algorithm_name(const std::string &algorithm)
        {
            return algorithm == "geodesic_heat" || algorithm == "geodesic-heat";
        }

        std::string parse_acp_strategy_name(const std::string &raw_value)
        {
            const std::string value = lowercase_copy(raw_value);
            if (value == "surface_spacing" || value == "surface-spacing" || value == "v2")
            {
                return "surface_spacing";
            }
            if (value == "woven" || value == "v1" || value == "default")
            {
                return "woven";
            }
            return "";
        }

    } // namespace

    std::string solver_algorithm_from_params(PyObject *params_copy)
    {
        if (!params_copy || !PyDict_Check(params_copy))
        {
            return "acp_energy";
        }
        PyObject *alg_obj = PyDict_GetItemString(params_copy, "algorithm");
        if (!alg_obj || !PyUnicode_Check(alg_obj))
        {
            return "acp_energy";
        }
        const char *alg_name = PyUnicode_AsUTF8(alg_obj);
        if (!alg_name || !*alg_name)
        {
            PyErr_Clear();
            return "acp_energy";
        }
        return std::string(alg_name);
    }

    SolverAlgorithmProfile solver_algorithm_profile_from_params(PyObject *params_copy)
    {
        SolverAlgorithmProfile profile;
        profile.requested_algorithm = solver_algorithm_from_params(params_copy);

        const std::string algorithm = lowercase_copy(profile.requested_algorithm);
        profile.acp_energy_mode = is_acp_energy_algorithm_name(algorithm);
        profile.geodesic_heat_mode = is_geodesic_heat_algorithm_name(algorithm);
        if (!profile.acp_energy_mode)
        {
            profile.acp_strategy = "none";
            profile.surface_spacing_mode = false;
            return profile;
        }

        std::string strategy = "woven";

        const std::string explicit_strategy = parse_acp_strategy_name(
            param_string(params_copy, "acp_strategy", ""));
        if (!explicit_strategy.empty())
        {
            strategy = explicit_strategy;
        }

        if (param_bool(params_copy, "objective_surface_spacing", false))
        {
            strategy = "surface_spacing";
        }

        profile.acp_strategy = strategy;
        profile.surface_spacing_mode = (strategy == "surface_spacing");
        return profile;
    }

    int solver_iterations_from_params(PyObject *params_copy)
    {
        if (!params_copy || !PyDict_Check(params_copy))
        {
            return 0;
        }
        PyObject *steps_obj = PyDict_GetItemString(params_copy, "steps");
        if (!steps_obj)
        {
            return 0;
        }
        long parsed = PyLong_AsLong(steps_obj);
        if (PyErr_Occurred())
        {
            PyErr_Clear();
            return 0;
        }
        if (parsed < 0)
        {
            return 0;
        }
        return static_cast<int>(parsed);
    }

} // namespace fishnet_internal
