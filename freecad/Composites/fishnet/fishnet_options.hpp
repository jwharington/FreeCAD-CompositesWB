#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <cstddef>
#include <string>
#include <utility>

#include "fishnet_algorithm_types.hpp"
#include "fishnet_options_api.hpp"

namespace fishnet_internal
{

    struct GeometrySolverConfig
    {
        std::string algorithm{"acp_energy"};
        bool acp_surface_spacing_mode{false};
        bool acp_energy_mode{false};
        CurrentNodeSolverMode solver_mode{CurrentNodeSolverMode::SphereSurface};
        double max_adjacent_normal_angle{1.5707963267948966};
        double max_local_fold_ratio{0.0};
        double max_shear_angle{-1.0};
        bool surface_spacing_refine{false};
        int surface_spacing_relax_iterations{3};
        bool surface_spacing_strict{false};
        bool surface_spacing_fail_on_violation{false};
        double surface_spacing_edge_tolerance{0.02};
        bool boundary_extend{true};
        bool boundary_trim{true};
        bool paper_alignment_boundary_reference{false};
        bool paper_alignment_directional_reference{false};
        bool paper_alignment_has_reference_direction_request{false};
        Vec3 paper_alignment_reference_direction{1.0, 0.0, 0.0};
        double sample_max_length{0.0};
        double nominal_spacing{0.0};
    };

    class DrapingAlgorithmPolicy
    {
    public:
        explicit DrapingAlgorithmPolicy(PyObject *params_copy);
        explicit DrapingAlgorithmPolicy(const NormalizedParams &params);

        bool supported() const;
        PyObject *build_unsupported_result(PyObject *params_copy) const;

    private:
        std::string requested_algorithm_;
    };

    GeometrySolverConfig build_geometry_solver_config(PyObject *params_copy, size_t native_face_count);
    GeometrySolverConfig build_geometry_solver_config(const NormalizedParams &params, size_t native_face_count);

} // namespace fishnet_internal
