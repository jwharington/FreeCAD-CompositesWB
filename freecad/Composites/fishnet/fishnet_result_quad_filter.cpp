#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "fishnet_result_quad_filter.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <vector>

#include "fishnet_options_api.hpp"

namespace fishnet_internal
{

    static bool quad_within_shear_limit_radians(
        const std::vector<Vec3> &points,
        const std::vector<int> &quad,
        double max_shear_angle)
    {
        if (quad.size() < 4)
        {
            return false;
        }
        if (!std::isfinite(max_shear_angle) || max_shear_angle < 0.0)
        {
            return true;
        }

        const int a = quad[0];
        const int b = quad[1];
        const int c = quad[2];
        const int d = quad[3];
        if (std::min({a, b, c, d}) < 0 ||
            std::max({a, b, c, d}) >= static_cast<int>(points.size()))
        {
            return false;
        }

        constexpr double kHalfPi = 1.5707963267948966;
        const std::array<int, 4> ids{{a, b, c, d}};
        for (int k = 0; k < 4; ++k)
        {
            const Vec3 &prev = points[static_cast<size_t>(ids[static_cast<size_t>((k + 3) % 4)])];
            const Vec3 &curr = points[static_cast<size_t>(ids[static_cast<size_t>(k)])];
            const Vec3 &next = points[static_cast<size_t>(ids[static_cast<size_t>((k + 1) % 4)])];
            const Vec3 e1 = prev - curr;
            const Vec3 e2 = next - curr;
            const double n1 = norm(e1);
            const double n2 = norm(e2);
            if (n1 <= kVectorZeroEpsilon || n2 <= kVectorZeroEpsilon)
            {
                return false;
            }
            const double cos_ang = std::clamp(dot(e1, e2) / (n1 * n2), -1.0, 1.0);
            const double ang = std::acos(cos_ang);
            const double shear = std::fabs(kHalfPi - ang);
            if (shear > max_shear_angle + 1.0e-9)
            {
                return false;
            }
        }
        return true;
    }

    std::vector<std::vector<int>> filtered_geometry_quads_for_output(
        const std::vector<std::vector<int>> &quads,
        const std::vector<Vec3> &points,
        PyObject *params_copy)
    {
        if (quads.empty())
        {
            return quads;
        }

        const SolverAlgorithmProfile profile = solver_algorithm_profile_from_params(params_copy);
        if (profile.surface_spacing_mode)
        {
            return quads;
        }

        const double max_shear_deg = param_double(params_copy, "max_shear_angle_deg", 30.0);
        if (!std::isfinite(max_shear_deg) || max_shear_deg < 0.0)
        {
            return quads;
        }

        const double max_shear_angle = max_shear_deg * 0.017453292519943295;
        std::vector<std::vector<int>> filtered;
        filtered.reserve(quads.size());
        for (const auto &quad : quads)
        {
            if (quad_within_shear_limit_radians(points, quad, max_shear_angle))
            {
                filtered.push_back(quad);
            }
        }

        return filtered;
    }

} // namespace fishnet_internal
