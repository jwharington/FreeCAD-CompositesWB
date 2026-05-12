#include "fishnet_result_surface_spacing_strict.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <set>
#include <utility>
#include <vector>

namespace fishnet_internal
{

    static std::pair<long, double> surface_spacing_edge_violation_summary(
        const std::vector<Vec3> &points,
        const std::vector<std::vector<int>> &quads,
        double target_spacing,
        double tolerance,
        std::set<std::pair<int, int>> *violating_edges)
    {
        if (violating_edges)
        {
            violating_edges->clear();
        }
        if (points.empty() || quads.empty() ||
            !std::isfinite(target_spacing) || target_spacing <= kVectorZeroEpsilon ||
            !std::isfinite(tolerance) || tolerance < 0.0)
        {
            return {0L, 0.0};
        }

        std::set<std::pair<int, int>> unique_edges;
        long violations = 0;
        double max_rel_error = 0.0;

        for (const auto &quad : quads)
        {
            if (quad.size() < 4)
            {
                continue;
            }
            const int a = quad[0];
            const int b = quad[1];
            const int c = quad[2];
            const int d = quad[3];
            const std::array<std::pair<int, int>, 4> edge_pairs{{
                {a, b},
                {b, c},
                {c, d},
                {d, a},
            }};

            for (const auto &edge_pair : edge_pairs)
            {
                int e0 = edge_pair.first;
                int e1 = edge_pair.second;
                if (e0 == e1 ||
                    e0 < 0 || e1 < 0 ||
                    e0 >= static_cast<int>(points.size()) ||
                    e1 >= static_cast<int>(points.size()))
                {
                    continue;
                }
                if (e0 > e1)
                {
                    std::swap(e0, e1);
                }
                const auto edge = std::make_pair(e0, e1);
                if (!unique_edges.insert(edge).second)
                {
                    continue;
                }

                const Vec3 delta = points[static_cast<size_t>(e1)] - points[static_cast<size_t>(e0)];
                const double length = norm(delta);
                if (!std::isfinite(length))
                {
                    continue;
                }
                const double rel_error = std::abs(length - target_spacing) / target_spacing;
                if (!std::isfinite(rel_error))
                {
                    continue;
                }
                if (rel_error > tolerance)
                {
                    violations += 1;
                    max_rel_error = std::max(max_rel_error, rel_error);
                    if (violating_edges)
                    {
                        violating_edges->insert(edge);
                    }
                }
            }
        }

        return {violations, max_rel_error};
    }

    static long surface_spacing_structural_edge_count(
        const std::vector<Vec3> &points,
        const std::vector<std::vector<int>> &quads)
    {
        if (points.empty() || quads.empty())
        {
            return 0;
        }

        std::set<std::pair<int, int>> unique_edges;
        for (const auto &quad : quads)
        {
            if (quad.size() < 4)
            {
                continue;
            }
            const int a = quad[0];
            const int b = quad[1];
            const int c = quad[2];
            const int d = quad[3];
            const std::array<std::pair<int, int>, 4> edge_pairs{{
                {a, b},
                {b, c},
                {c, d},
                {d, a},
            }};
            for (const auto &edge_pair : edge_pairs)
            {
                int e0 = edge_pair.first;
                int e1 = edge_pair.second;
                if (e0 == e1 ||
                    e0 < 0 || e1 < 0 ||
                    e0 >= static_cast<int>(points.size()) ||
                    e1 >= static_cast<int>(points.size()))
                {
                    continue;
                }
                if (e0 > e1)
                {
                    std::swap(e0, e1);
                }
                unique_edges.insert({e0, e1});
            }
        }

        return static_cast<long>(unique_edges.size());
    }

    SurfaceSpacingStrictVerification enforce_surface_spacing_strict_mode(
        const SurfaceSpacingStrictPolicy &strict_policy,
        bool surface_spacing_mode,
        const std::vector<Vec3> &points,
        std::vector<std::vector<int>> &quads,
        double target_spacing)
    {
        SurfaceSpacingStrictVerification verification;
        verification.enabled = surface_spacing_mode && strict_policy.enabled;
        verification.fail_on_violation = strict_policy.fail_on_violation;
        verification.tolerance = strict_policy.tolerance;

        if (!verification.enabled)
        {
            return verification;
        }

        if (!std::isfinite(target_spacing) || target_spacing <= kVectorZeroEpsilon)
        {
            verification.pass = false;
            verification.fail_reason = "infeasible_geometry";
            verification.force_nonconverged = verification.fail_on_violation;
            return verification;
        }

        constexpr int kMaxRepairPasses = 3;
        for (int pass = 0; pass < kMaxRepairPasses; ++pass)
        {
            std::set<std::pair<int, int>> violating_edges;
            const auto [violation_count, max_rel_error] = surface_spacing_edge_violation_summary(
                points,
                quads,
                target_spacing,
                verification.tolerance,
                &violating_edges);

            verification.violation_count = violation_count;
            verification.max_rel_error = max_rel_error;
            if (violation_count <= 0)
            {
                break;
            }
            if (quads.empty())
            {
                break;
            }

            std::vector<std::vector<int>> repaired_quads;
            repaired_quads.reserve(quads.size());
            for (const auto &quad : quads)
            {
                if (quad.size() < 4)
                {
                    continue;
                }

                const int a = quad[0];
                const int b = quad[1];
                const int c = quad[2];
                const int d = quad[3];
                const std::array<std::pair<int, int>, 4> edge_pairs{{
                    {std::min(a, b), std::max(a, b)},
                    {std::min(b, c), std::max(b, c)},
                    {std::min(c, d), std::max(c, d)},
                    {std::min(d, a), std::max(d, a)},
                }};

                bool intersects_violation = false;
                for (const auto &edge : edge_pairs)
                {
                    if (violating_edges.find(edge) != violating_edges.end())
                    {
                        intersects_violation = true;
                        break;
                    }
                }
                if (!intersects_violation)
                {
                    repaired_quads.push_back(quad);
                }
            }

            if (repaired_quads.size() == quads.size())
            {
                break;
            }

            quads.swap(repaired_quads);
            verification.repair_passes += 1;
            if (quads.empty())
            {
                break;
            }
        }

        const auto [final_violations, final_max_rel_error] = surface_spacing_edge_violation_summary(
            points,
            quads,
            target_spacing,
            verification.tolerance,
            nullptr);
        verification.violation_count = final_violations;
        verification.max_rel_error = final_max_rel_error;

        verification.edge_count = surface_spacing_structural_edge_count(points, quads);

        verification.pass = verification.edge_count > 0 && verification.violation_count == 0;
        if (!verification.pass)
        {
            verification.fail_reason = verification.edge_count <= 0 ? "insufficient_coverage" : "violations_after_repair";
        }
        verification.force_nonconverged = verification.fail_on_violation && !verification.pass;

        return verification;
    }

} // namespace fishnet_internal
