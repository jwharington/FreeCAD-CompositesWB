#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <array>
#include <vector>

#include "fishnet_algorithm_types.hpp"
#include "fishnet_options_api.hpp"

namespace fishnet_internal
{

    enum class SolveInputKind
    {
        GeometryLike,
        MeshLike,
    };

    struct SolveRequest
    {
        SolveInputKind input_kind{SolveInputKind::MeshLike};
        PyObject *geometry_obj{nullptr}; // borrowed reference
        std::vector<Vec3> mesh_points;
        std::vector<std::array<int, 3>> mesh_faces;

        PyObject *params_copy{nullptr};
        SolverAlgorithmProfile algorithm_profile{};
        bool acp_energy_mode{false};

        SolveRequest() = default;
        SolveRequest(const SolveRequest &) = delete;
        SolveRequest &operator=(const SolveRequest &) = delete;

        SolveRequest(SolveRequest &&other) noexcept;
        SolveRequest &operator=(SolveRequest &&other) noexcept;

        ~SolveRequest();

        PyObject *release_params_copy();
    };

    PyObject *copy_params_dict(PyObject *params_obj);
    bool parse_solve_request(PyObject *args, PyObject *kwargs, SolveRequest &request);

} // namespace fishnet_internal
