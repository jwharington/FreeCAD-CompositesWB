#include "fishnet_kindrape_propagation.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <deque>
#include <limits>

namespace fishnet_internal
{

    namespace
    {

        constexpr int kDirPrimaryPositive = 0;

        double directional_dot(const Vec3 &unit_edge, const Vec3 &primary_axis, const Vec3 &orthogonal_axis, int direction)
        {
            switch (direction)
            {
            case kDirPrimaryPositive:
                return dot(unit_edge, primary_axis);
            default:
                return -std::numeric_limits<double>::infinity();
            }
        }

        bool is_nan(double value)
        {
            return std::isnan(value);
        }

        bool has_full_coordinates(const std::vector<double> &x_coord, const std::vector<double> &y_coord, int index)
        {
            return !is_nan(x_coord[static_cast<size_t>(index)]) && !is_nan(y_coord[static_cast<size_t>(index)]);
        }

        bool is_unassigned(const std::vector<double> &x_coord, const std::vector<double> &y_coord, int index)
        {
            return is_nan(x_coord[static_cast<size_t>(index)]) && is_nan(y_coord[static_cast<size_t>(index)]);
        }

        int choose_directional_neighbor(
            const std::vector<Vec3> &local_points,
            const std::vector<std::vector<int>> &adjacency,
            int seed_index,
            const Vec3 &primary_axis,
            const Vec3 &orthogonal_axis,
            int direction)
        {
            if (seed_index < 0 || seed_index >= static_cast<int>(local_points.size()))
            {
                return -1;
            }
            if (seed_index >= static_cast<int>(adjacency.size()))
            {
                return -1;
            }

            int best_nbr = -1;
            double best_score = 0.0;
            for (int nbr : adjacency[static_cast<size_t>(seed_index)])
            {
                if (nbr < 0 || nbr >= static_cast<int>(local_points.size()))
                {
                    continue;
                }
                Vec3 edge = local_points[static_cast<size_t>(nbr)] - local_points[static_cast<size_t>(seed_index)];
                const double length = std::sqrt(edge.x * edge.x + edge.y * edge.y);
                if (length <= kVectorZeroEpsilon)
                {
                    continue;
                }
                const Vec3 unit_edge{edge.x / length, edge.y / length, 0.0};
                const double score = directional_dot(unit_edge, primary_axis, orthogonal_axis, direction);
                if (score <= 1.0e-9)
                {
                    continue;
                }
                if (score > best_score + 1.0e-12 ||
                    (std::abs(score - best_score) <= 1.0e-12 && (best_nbr < 0 || nbr < best_nbr)))
                {
                    best_score = score;
                    best_nbr = nbr;
                }
            }
            return best_nbr;
        }

    } // namespace

    void run_kindrape_scheduler_skeleton(
        const std::vector<Vec3> &local_points,
        const std::vector<std::vector<int>> &adjacency,
        int seed_index,
        double nominal_edge_length,
        const Vec3 &primary_axis,
        const Vec3 &orthogonal_axis,
        std::vector<double> &x_coord,
        std::vector<double> &y_coord,
        AcpPropagationSummary &summary)
    {
        summary.stage_trace.clear();
        summary.step1_assigned = 0;
        summary.step2_assigned = 0;
        summary.step3_assigned = 0;
        summary.primary_assigned = 0;
        summary.orthogonal_assigned = 0;
        summary.fill_assigned = 0;

        if (local_points.empty() ||
            local_points.size() != x_coord.size() ||
            local_points.size() != y_coord.size() ||
            seed_index < 0 ||
            seed_index >= static_cast<int>(local_points.size()))
        {
            return;
        }

        const double step = (std::isfinite(nominal_edge_length) && nominal_edge_length > kVectorZeroEpsilon)
                                ? nominal_edge_length
                                : 1.0;
        const double nan = std::numeric_limits<double>::quiet_NaN();

        std::fill(x_coord.begin(), x_coord.end(), nan);
        std::fill(y_coord.begin(), y_coord.end(), nan);

        // Step 1: seed + second node from primary draping direction.
        summary.stage_trace.push_back("step1");
        x_coord[static_cast<size_t>(seed_index)] = 0.0;
        y_coord[static_cast<size_t>(seed_index)] = 0.0;
        summary.step1_assigned = 1;

        int heading_index = choose_directional_neighbor(
            local_points,
            adjacency,
            seed_index,
            primary_axis,
            orthogonal_axis,
            kDirPrimaryPositive);
        if (heading_index < 0 && seed_index < static_cast<int>(adjacency.size()) && !adjacency[static_cast<size_t>(seed_index)].empty())
        {
            heading_index = adjacency[static_cast<size_t>(seed_index)].front();
        }
        if (heading_index >= 0)
        {
            if (is_nan(x_coord[static_cast<size_t>(heading_index)]))
            {
                x_coord[static_cast<size_t>(heading_index)] = step;
                ++summary.primary_assigned;
            }
            if (is_nan(y_coord[static_cast<size_t>(heading_index)]))
            {
                y_coord[static_cast<size_t>(heading_index)] = 0.0;
            }
            summary.step1_assigned = 2;
        }

        // Step 2: deterministic generator traversal skeleton (queue-based).
        summary.stage_trace.push_back("step2");
        std::deque<int> queue;
        queue.push_back(seed_index);
        if (heading_index >= 0)
        {
            queue.push_back(heading_index);
        }

        while (!queue.empty())
        {
            const int cur = queue.front();
            queue.pop_front();
            if (cur < 0 || cur >= static_cast<int>(local_points.size()) || cur >= static_cast<int>(adjacency.size()))
            {
                continue;
            }

            for (int nbr : adjacency[static_cast<size_t>(cur)])
            {
                if (nbr < 0 || nbr >= static_cast<int>(local_points.size()))
                {
                    continue;
                }

                const bool was_unassigned = is_unassigned(x_coord, y_coord, nbr);
                bool progressed = false;

                Vec3 edge = local_points[static_cast<size_t>(nbr)] - local_points[static_cast<size_t>(cur)];
                const double edge_length = std::sqrt(edge.x * edge.x + edge.y * edge.y);
                if (edge_length <= kVectorZeroEpsilon)
                {
                    continue;
                }

                const Vec3 unit_edge{edge.x / edge_length, edge.y / edge_length, 0.0};
                const double primary_align = std::abs(dot(unit_edge, primary_axis));
                const double orthogonal_align = std::abs(dot(unit_edge, orthogonal_axis));

                if (primary_align >= orthogonal_align &&
                    !is_nan(x_coord[static_cast<size_t>(cur)]) &&
                    is_nan(x_coord[static_cast<size_t>(nbr)]))
                {
                    const double sign = dot(unit_edge, primary_axis) >= 0.0 ? 1.0 : -1.0;
                    x_coord[static_cast<size_t>(nbr)] = x_coord[static_cast<size_t>(cur)] + sign * step;
                    if (is_nan(y_coord[static_cast<size_t>(nbr)]) && !is_nan(y_coord[static_cast<size_t>(cur)]))
                    {
                        y_coord[static_cast<size_t>(nbr)] = y_coord[static_cast<size_t>(cur)];
                    }
                    ++summary.primary_assigned;
                    progressed = true;
                }

                if (orthogonal_align > primary_align &&
                    !is_nan(y_coord[static_cast<size_t>(cur)]) &&
                    is_nan(y_coord[static_cast<size_t>(nbr)]))
                {
                    const double sign = dot(unit_edge, orthogonal_axis) >= 0.0 ? 1.0 : -1.0;
                    y_coord[static_cast<size_t>(nbr)] = y_coord[static_cast<size_t>(cur)] + sign * step;
                    if (is_nan(x_coord[static_cast<size_t>(nbr)]) && !is_nan(x_coord[static_cast<size_t>(cur)]))
                    {
                        x_coord[static_cast<size_t>(nbr)] = x_coord[static_cast<size_t>(cur)];
                    }
                    ++summary.orthogonal_assigned;
                    progressed = true;
                }

                if (!progressed)
                {
                    continue;
                }

                if (was_unassigned)
                {
                    ++summary.step2_assigned;
                }
                queue.push_back(nbr);
            }
        }

        // Step 3: constrained fill for remaining nodes.
        summary.stage_trace.push_back("step3");
        bool changed = true;
        while (changed)
        {
            changed = false;
            for (size_t i = 0; i < local_points.size(); ++i)
            {
                if (has_full_coordinates(x_coord, y_coord, static_cast<int>(i)))
                {
                    continue;
                }

                const bool was_unassigned = is_unassigned(x_coord, y_coord, static_cast<int>(i));
                double x_sum = 0.0;
                double y_sum = 0.0;
                int x_count = 0;
                int y_count = 0;

                if (i >= adjacency.size())
                {
                    continue;
                }
                for (int nbr : adjacency[i])
                {
                    if (nbr < 0 || nbr >= static_cast<int>(local_points.size()))
                    {
                        continue;
                    }
                    if (!is_nan(x_coord[static_cast<size_t>(nbr)]))
                    {
                        x_sum += x_coord[static_cast<size_t>(nbr)];
                        ++x_count;
                    }
                    if (!is_nan(y_coord[static_cast<size_t>(nbr)]))
                    {
                        y_sum += y_coord[static_cast<size_t>(nbr)];
                        ++y_count;
                    }
                }

                bool progressed = false;
                if (is_nan(x_coord[i]) && x_count > 0)
                {
                    x_coord[i] = x_sum / static_cast<double>(x_count);
                    progressed = true;
                }
                if (is_nan(y_coord[i]) && y_count > 0)
                {
                    y_coord[i] = y_sum / static_cast<double>(y_count);
                    progressed = true;
                }

                if (progressed)
                {
                    changed = true;
                    if (was_unassigned)
                    {
                        ++summary.step3_assigned;
                    }
                }
            }
        }

        const Vec3 seed_local = local_points[static_cast<size_t>(seed_index)];
        for (size_t i = 0; i < local_points.size(); ++i)
        {
            if (!is_nan(x_coord[i]) && !is_nan(y_coord[i]))
            {
                continue;
            }

            const bool was_unassigned = is_unassigned(x_coord, y_coord, static_cast<int>(i));
            const Vec3 delta = local_points[i] - seed_local;
            if (is_nan(x_coord[i]))
            {
                x_coord[i] = dot(delta, primary_axis);
            }
            if (is_nan(y_coord[i]))
            {
                y_coord[i] = dot(delta, orthogonal_axis);
            }
            if (was_unassigned)
            {
                ++summary.step3_assigned;
            }
        }

        summary.fill_assigned = summary.step3_assigned;
    }

} // namespace fishnet_internal
