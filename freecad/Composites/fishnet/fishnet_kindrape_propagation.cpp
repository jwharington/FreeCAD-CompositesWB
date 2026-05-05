#include "fishnet_kindrape_propagation.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <deque>
#include <limits>

#include "fishnet_kindrape_nr.hpp"

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

        int choose_step2_reference_neighbor(
            const std::vector<Vec3> &local_points,
            const std::vector<std::vector<int>> &adjacency,
            const std::vector<double> &x_coord,
            const std::vector<double> &y_coord,
            int current,
            int target,
            const Vec3 &orthogonal_axis)
        {
            if (current < 0 || current >= static_cast<int>(adjacency.size()))
            {
                return -1;
            }

            int best = -1;
            double best_score = -std::numeric_limits<double>::infinity();
            for (int nbr : adjacency[static_cast<size_t>(current)])
            {
                if (nbr < 0 || nbr >= static_cast<int>(local_points.size()) || nbr == target)
                {
                    continue;
                }
                if (!has_full_coordinates(x_coord, y_coord, nbr))
                {
                    continue;
                }

                const Vec3 edge = local_points[static_cast<size_t>(nbr)] - local_points[static_cast<size_t>(current)];
                const double len = std::sqrt(edge.x * edge.x + edge.y * edge.y);
                if (len <= kVectorZeroEpsilon)
                {
                    continue;
                }
                const Vec3 unit_edge{edge.x / len, edge.y / len, 0.0};
                const double score = std::abs(dot(unit_edge, orthogonal_axis));
                if (score > best_score + 1.0e-12 ||
                    (std::abs(score - best_score) <= 1.0e-12 && (best < 0 || nbr < best)))
                {
                    best = nbr;
                    best_score = score;
                }
            }

            return best;
        }

    } // namespace

    void run_kindrape_scheduler_skeleton(
        const std::vector<Vec3> &local_points,
        const std::vector<std::vector<int>> &adjacency,
        int seed_index,
        double nominal_edge_length,
        double target_pre_shear_deg,
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
        summary.step2_nr_attempts = 0;
        summary.step2_nr_converged = 0;
        summary.step2_nr_fallback_count = 0;
        summary.step2_nr_infeasible = 0;
        summary.step2_nr_decrease_count = 0;
        summary.step2_nr_iterations = 0;
        summary.step2_nr_initial_objective_sum = 0.0;
        summary.step2_nr_final_objective_sum = 0.0;

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

        // Step 2: deterministic generator traversal skeleton with local NR solve.
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
                if (!has_full_coordinates(x_coord, y_coord, cur) || !is_unassigned(x_coord, y_coord, nbr))
                {
                    continue;
                }

                Vec3 edge = local_points[static_cast<size_t>(nbr)] - local_points[static_cast<size_t>(cur)];
                const double edge_length = std::sqrt(edge.x * edge.x + edge.y * edge.y);
                if (edge_length <= kVectorZeroEpsilon)
                {
                    ++summary.step2_nr_infeasible;
                    continue;
                }

                const Vec3 unit_edge{edge.x / edge_length, edge.y / edge_length, 0.0};
                const double primary_align = std::abs(dot(unit_edge, primary_axis));
                const double orthogonal_align = std::abs(dot(unit_edge, orthogonal_axis));

                if (std::abs(target_pre_shear_deg) <= 1.0e-12)
                {
                    // Preserve pre-Slice-C deterministic behavior when no pre-shear target is requested.
                    if (primary_align >= orthogonal_align)
                    {
                        const double sign = dot(unit_edge, primary_axis) >= 0.0 ? 1.0 : -1.0;
                        x_coord[static_cast<size_t>(nbr)] = x_coord[static_cast<size_t>(cur)] + sign * step;
                        y_coord[static_cast<size_t>(nbr)] = y_coord[static_cast<size_t>(cur)];
                        ++summary.primary_assigned;
                    }
                    else
                    {
                        const double sign = dot(unit_edge, orthogonal_axis) >= 0.0 ? 1.0 : -1.0;
                        y_coord[static_cast<size_t>(nbr)] = y_coord[static_cast<size_t>(cur)] + sign * step;
                        x_coord[static_cast<size_t>(nbr)] = x_coord[static_cast<size_t>(cur)];
                        ++summary.orthogonal_assigned;
                    }
                    ++summary.step2_assigned;
                    queue.push_back(nbr);
                    continue;
                }

                const int ref_nbr = choose_step2_reference_neighbor(
                    local_points,
                    adjacency,
                    x_coord,
                    y_coord,
                    cur,
                    nbr,
                    orthogonal_axis);
                if (ref_nbr < 0)
                {
                    ++summary.step2_nr_infeasible;
                    continue;
                }

                const Vec3 current_point{
                    x_coord[static_cast<size_t>(cur)],
                    y_coord[static_cast<size_t>(cur)],
                    0.0,
                };
                const Vec3 ref_point{
                    x_coord[static_cast<size_t>(ref_nbr)],
                    y_coord[static_cast<size_t>(ref_nbr)],
                    0.0,
                };
                const Vec3 reference_vec = ref_point - current_point;

                const Step2NrSolveResult nr = solve_step2_generator_cell_nr(
                    current_point,
                    reference_vec,
                    edge,
                    step,
                    target_pre_shear_deg);

                ++summary.step2_nr_attempts;
                summary.step2_nr_iterations += nr.iterations;
                summary.step2_nr_initial_objective_sum += nr.objective_initial;
                summary.step2_nr_final_objective_sum += nr.objective_final;
                if (nr.converged)
                {
                    ++summary.step2_nr_converged;
                }
                if (nr.used_fallback)
                {
                    ++summary.step2_nr_fallback_count;
                }
                if (nr.infeasible || !nr.success)
                {
                    ++summary.step2_nr_infeasible;
                    continue;
                }
                if (nr.objective_final <= nr.objective_initial + 1.0e-12)
                {
                    ++summary.step2_nr_decrease_count;
                }

                x_coord[static_cast<size_t>(nbr)] = nr.solved_point.x;
                y_coord[static_cast<size_t>(nbr)] = nr.solved_point.y;
                ++summary.step2_assigned;

                if (primary_align >= orthogonal_align)
                {
                    ++summary.primary_assigned;
                }
                else
                {
                    ++summary.orthogonal_assigned;
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
