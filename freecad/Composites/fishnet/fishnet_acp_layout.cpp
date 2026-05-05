#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <deque>
#include <limits>
#include <string>
#include <unordered_map>
#include <vector>

#include "fishnet_acp_layout.hpp"
#include "fishnet_diagnostics_api.hpp"
#include "fishnet_kindrape_propagation.hpp"

namespace fishnet_internal
{

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

    std::vector<std::vector<int>> build_vertex_adjacency(
        size_t point_count,
        const std::vector<std::pair<int, int>> &edges)
    {
        std::vector<std::vector<int>> adjacency(point_count);
        for (const auto &edge : edges)
        {
            int a = edge.first;
            int b = edge.second;
            if (a < 0 || b < 0 ||
                a >= static_cast<int>(point_count) || b >= static_cast<int>(point_count) ||
                a == b)
            {
                continue;
            }
            adjacency[static_cast<size_t>(a)].push_back(b);
            adjacency[static_cast<size_t>(b)].push_back(a);
        }
        for (auto &nbrs : adjacency)
        {
            std::sort(nbrs.begin(), nbrs.end());
            nbrs.erase(std::unique(nbrs.begin(), nbrs.end()), nbrs.end());
        }
        return adjacency;
    }

    int nearest_point_index(const std::vector<Vec3> &points, const Vec3 &target)
    {
        if (points.empty())
        {
            return -1;
        }
        int best_idx = 0;
        double best_dist2 = std::numeric_limits<double>::infinity();
        for (size_t i = 0; i < points.size(); ++i)
        {
            Vec3 d = points[i] - target;
            double dist2 = dot(d, d);
            if (dist2 < best_dist2)
            {
                best_dist2 = dist2;
                best_idx = static_cast<int>(i);
            }
        }
        return best_idx;
    }

    Vec3 choose_primary_axis(
        const std::vector<Vec3> &local_points,
        const Vec3 &x_axis,
        const Vec3 &y_axis,
        PyObject *params)
    {
        Vec3 requested_dir{};
        bool has_requested = try_parse_param_vec3(params, "draping_direction", requested_dir);
        if (has_requested)
        {
            Vec3 projected = {
                dot(requested_dir, x_axis),
                dot(requested_dir, y_axis),
                0.0,
            };
            if (norm(projected) > kVectorZeroEpsilon)
            {
                return normalize(projected);
            }
        }

        if (!local_points.empty())
        {
            double min_x = local_points.front().x;
            double max_x = local_points.front().x;
            double min_y = local_points.front().y;
            double max_y = local_points.front().y;
            for (const auto &p : local_points)
            {
                min_x = std::min(min_x, p.x);
                max_x = std::max(max_x, p.x);
                min_y = std::min(min_y, p.y);
                max_y = std::max(max_y, p.y);
            }
            if ((max_x - min_x) >= (max_y - min_y))
            {
                return {1.0, 0.0, 0.0};
            }
            return {0.0, 1.0, 0.0};
        }

        return {1.0, 0.0, 0.0};
    }

    AcpPropagationSummary initialize_acp_layout(
        const std::vector<Vec3> &mesh_points,
        const std::vector<Vec3> &local_points,
        const std::vector<std::pair<int, int>> &edges,
        const Vec3 &x_axis,
        const Vec3 &y_axis,
        double nominal_edge_length,
        PyObject *params,
        std::vector<Vec3> &fabric_points)
    {
        AcpPropagationSummary summary;
        if (mesh_points.empty() || local_points.size() != mesh_points.size() || fabric_points.size() != mesh_points.size())
        {
            return summary;
        }

        summary.primary_axis = normalize(choose_primary_axis(local_points, x_axis, y_axis, params));
        if (norm(summary.primary_axis) <= kVectorZeroEpsilon)
        {
            summary.primary_axis = {1.0, 0.0, 0.0};
        }
        summary.orthogonal_axis = {-summary.primary_axis.y, summary.primary_axis.x, 0.0};

        int seed_index = 0;
        if (params && PyDict_Check(params))
        {
            if (PyObject *seed_obj = PyDict_GetItemString(params, "seed"))
            {
                long seed_long = PyLong_AsLong(seed_obj);
                if (!PyErr_Occurred() && seed_long >= 0 && seed_long < static_cast<long>(mesh_points.size()))
                {
                    seed_index = static_cast<int>(seed_long);
                }
                else
                {
                    PyErr_Clear();
                }
            }
            Vec3 seed_point{};
            if (try_parse_param_vec3(params, "seed_point", seed_point))
            {
                int nearest = nearest_point_index(mesh_points, seed_point);
                if (nearest >= 0)
                {
                    seed_index = nearest;
                }
            }
        }
        summary.seed_index = seed_index;

        const double nominal = (std::isfinite(nominal_edge_length) && nominal_edge_length > kVectorZeroEpsilon)
                                   ? nominal_edge_length
                                   : infer_nominal_edge_length(nominal_edge_length, fabric_points, edges);

        std::vector<std::vector<int>> adjacency = build_vertex_adjacency(mesh_points.size(), edges);
        std::vector<double> x_coord(mesh_points.size(), std::numeric_limits<double>::quiet_NaN());
        std::vector<double> y_coord(mesh_points.size(), std::numeric_limits<double>::quiet_NaN());

        run_kindrape_scheduler_skeleton(
            local_points,
            adjacency,
            seed_index,
            nominal,
            summary.primary_axis,
            summary.orthogonal_axis,
            x_coord,
            y_coord,
            summary);

        for (size_t i = 0; i < fabric_points.size(); ++i)
        {
            fabric_points[i] = {x_coord[i], y_coord[i], 0.0};
        }

        return summary;
    }

    void build_acp_edge_objective(
        const std::vector<Vec3> &local_points,
        const std::vector<std::pair<int, int>> &edges,
        const std::vector<std::vector<int>> &objective_quads,
        double nominal_edge_length,
        const Vec3 &primary_axis,
        const std::string &material_model,
        double ud_coefficient,
        bool thickness_correction,
        double objective_p_norm,
        double pre_shear_deg,
        double objective_shear_weight,
        double objective_fiber_weight,
        double objective_cell_gain,
        AcpObjectiveSummary &objective_summary,
        std::vector<double> &edge_targets,
        std::vector<double> &edge_weights)
    {
        const double nominal = (std::isfinite(nominal_edge_length) && nominal_edge_length > kVectorZeroEpsilon)
                                   ? nominal_edge_length
                                   : infer_nominal_edge_length(nominal_edge_length, local_points, edges);

        std::string model = material_model;
        std::transform(model.begin(), model.end(), model.begin(), [](unsigned char c)
                       { return static_cast<char>(std::tolower(c)); });
        const bool ud_model = (model == "ud" || model == "unidirectional");
        const double ud = std::clamp(ud_coefficient, 0.0, 1.0);
        const double p_norm = std::clamp(
            std::isfinite(objective_p_norm) ? objective_p_norm : 6.0,
            2.0,
            16.0);
        const double clamped_pre_shear_deg = std::clamp(
            std::isfinite(pre_shear_deg) ? pre_shear_deg : 0.0,
            -45.0,
            45.0);
        const double pre_shear_ratio = clamped_pre_shear_deg / 45.0;
        const double shear_weight = std::clamp(
            std::isfinite(objective_shear_weight) ? objective_shear_weight : (ud_model ? 0.6 : 1.0),
            0.0,
            4.0);
        const double fiber_weight = std::clamp(
            std::isfinite(objective_fiber_weight) ? objective_fiber_weight : (ud_model ? 1.0 : 0.25),
            0.0,
            4.0);
        const double cell_gain = std::clamp(
            std::isfinite(objective_cell_gain) ? objective_cell_gain : 0.0,
            0.0,
            1.0);

        objective_summary = {};
        objective_summary.objective_p_norm = p_norm;
        objective_summary.objective_pre_shear_deg = clamped_pre_shear_deg;
        objective_summary.objective_shear_weight = shear_weight;
        objective_summary.objective_fiber_weight = fiber_weight;
        objective_summary.objective_cell_gain = cell_gain;

        edge_targets.clear();
        edge_weights.clear();
        edge_targets.reserve(edges.size());
        edge_weights.reserve(edges.size());

        std::vector<double> edge_along_primary;
        std::vector<double> edge_signed_transverse;
        edge_along_primary.reserve(edges.size());
        edge_signed_transverse.reserve(edges.size());

        Vec3 primary = normalize(primary_axis);
        if (norm(primary) <= kVectorZeroEpsilon)
        {
            primary = {1.0, 0.0, 0.0};
        }

        const auto safe_mean = [](double sum, long count, double fallback = 1.0)
        {
            return count > 0 ? (sum / static_cast<double>(count)) : fallback;
        };

        auto classify_orientation = [](double along_primary)
        {
            if (along_primary >= 0.8)
            {
                return 0; // primary
            }
            if (along_primary <= 0.2)
            {
                return 1; // transverse
            }
            return 2; // bias
        };

        double signed_shear_proxy_sum = 0.0;
        double abs_shear_proxy_sum = 0.0;
        long shear_proxy_count = 0;

        for (const auto &edge : edges)
        {
            int a = edge.first;
            int b = edge.second;
            double target = nominal;
            double weight = 1.0;
            double along_primary = 0.5;
            double signed_transverse = 0.0;

            if (a >= 0 && b >= 0 &&
                a < static_cast<int>(local_points.size()) && b < static_cast<int>(local_points.size()))
            {
                Vec3 d = local_points[static_cast<size_t>(b)] - local_points[static_cast<size_t>(a)];
                double len = std::sqrt(d.x * d.x + d.y * d.y);
                if (len > kVectorZeroEpsilon)
                {
                    if (thickness_correction)
                    {
                        const double spatial = std::sqrt(d.x * d.x + d.y * d.y + d.z * d.z);
                        const double ratio = std::clamp(spatial / len, 1.0, 1.25);
                        target *= ratio;
                    }

                    Vec3 e2 = {d.x / len, d.y / len, 0.0};
                    const double signed_primary = std::clamp(dot(e2, primary), -1.0, 1.0);
                    along_primary = std::abs(signed_primary);
                    signed_transverse = (primary.x * e2.y) - (primary.y * e2.x);
                    const double transverse = std::sqrt(std::max(0.0, 1.0 - along_primary * along_primary));
                    const double shear_mix_abs = 2.0 * along_primary * transverse;
                    const double shear_mix_signed = 2.0 * signed_primary * signed_transverse;
                    const double along_p = std::pow(along_primary, p_norm);
                    const double transverse_p = std::pow(transverse, p_norm);
                    const double shear_p = std::pow(shear_mix_abs, std::max(1.0, 0.5 * p_norm));
                    const double bias_factor = std::clamp(1.0 - std::abs(2.0 * along_primary - 1.0), 0.0, 1.0);

                    signed_shear_proxy_sum += shear_mix_signed;
                    abs_shear_proxy_sum += std::abs(shear_mix_signed);
                    ++shear_proxy_count;

                    if (ud_model)
                    {
                        target *= 1.0 + ud * (0.45 * transverse_p + 0.12 * shear_p);
                        weight = 1.0 + ud * (0.8 * along_p + 0.2 * along_primary * along_primary);
                    }

                    if (std::abs(pre_shear_ratio) > 1.0e-12 && bias_factor > 0.0)
                    {
                        const double signed_bias = (signed_transverse >= 0.0 ? 1.0 : -1.0) * bias_factor;
                        const double asym_scale = std::clamp(1.0 + 0.18 * pre_shear_ratio * signed_bias, 0.75, 1.25);
                        target *= asym_scale;
                        weight *= 1.0 + 0.2 * std::abs(pre_shear_ratio) * bias_factor;
                    }
                }
            }

            edge_targets.push_back(target);
            edge_weights.push_back(weight);
            edge_along_primary.push_back(along_primary);
            edge_signed_transverse.push_back(signed_transverse);
        }

        const double pi = std::acos(-1.0);
        const double target_shear_rad = clamped_pre_shear_deg * (pi / 180.0);
        const double shear_norm_denom = std::max(1.0e-9, 0.25 * pi);
        const double fiber_norm_denom = std::max(1.0e-9, 0.5 * pi);

        if (!objective_quads.empty() && !edges.empty() && (shear_weight > 0.0 || fiber_weight > 0.0))
        {
            std::unordered_map<uint64_t, size_t> edge_lookup;
            edge_lookup.reserve(edges.size());
            for (size_t ei = 0; ei < edges.size(); ++ei)
            {
                edge_lookup[edge_key(edges[ei].first, edges[ei].second)] = ei;
            }

            auto normalize2d = [](const Vec3 &v)
            {
                const double len = std::sqrt(v.x * v.x + v.y * v.y);
                if (len <= kVectorZeroEpsilon)
                {
                    return Vec3{0.0, 0.0, 0.0};
                }
                return Vec3{v.x / len, v.y / len, 0.0};
            };

            double cell_shear_abs_sum_deg = 0.0;
            double cell_shear_signed_sum_deg = 0.0;
            double cell_shear_target_err_sum_deg = 0.0;
            double cell_fiber_angle_sum_deg = 0.0;
            double cell_objective_sum = 0.0;

            for (const auto &quad : objective_quads)
            {
                if (quad.size() < 4)
                {
                    continue;
                }
                const int i0 = quad[0];
                const int i1 = quad[1];
                const int i2 = quad[2];
                const int i3 = quad[3];
                if (i0 < 0 || i1 < 0 || i2 < 0 || i3 < 0 ||
                    i0 >= static_cast<int>(local_points.size()) ||
                    i1 >= static_cast<int>(local_points.size()) ||
                    i2 >= static_cast<int>(local_points.size()) ||
                    i3 >= static_cast<int>(local_points.size()))
                {
                    continue;
                }

                const Vec3 &p0 = local_points[static_cast<size_t>(i0)];
                const Vec3 &p1 = local_points[static_cast<size_t>(i1)];
                const Vec3 &p2 = local_points[static_cast<size_t>(i2)];
                const Vec3 &p3 = local_points[static_cast<size_t>(i3)];

                const Vec3 u = normalize2d((p1 - p0) + (p2 - p3));
                const Vec3 v = normalize2d((p3 - p0) + (p2 - p1));
                if (norm(u) <= kVectorZeroEpsilon || norm(v) <= kVectorZeroEpsilon)
                {
                    continue;
                }

                const double u_align = std::abs(dot(u, primary));
                const double v_align = std::abs(dot(v, primary));
                const Vec3 fiber_dir = (u_align >= v_align) ? u : v;
                const Vec3 cross_dir = (u_align >= v_align) ? v : u;

                const double fiber_cos = std::clamp(std::abs(dot(fiber_dir, primary)), 0.0, 1.0);
                const double fiber_angle_rad = std::acos(fiber_cos);

                const double orth_dot = std::clamp(std::abs(dot(fiber_dir, cross_dir)), 0.0, 1.0);
                const double orth_angle_rad = std::acos(orth_dot);
                const double shear_abs_rad = std::abs((0.5 * pi) - orth_angle_rad);
                const double orientation = (fiber_dir.x * cross_dir.y) - (fiber_dir.y * cross_dir.x);
                const double shear_signed_rad = (orientation >= 0.0 ? 1.0 : -1.0) * shear_abs_rad;
                const double shear_target_error_rad = std::abs(shear_signed_rad - target_shear_rad);

                const double shear_norm = std::clamp(shear_target_error_rad / shear_norm_denom, 0.0, 4.0);
                const double fiber_norm = std::clamp(fiber_angle_rad / fiber_norm_denom, 0.0, 4.0);
                const double shear_term = std::pow(shear_norm, p_norm);
                const double fiber_term = std::pow(fiber_norm, p_norm);
                const double term_weight_sum = std::max(1.0e-9, shear_weight + fiber_weight);
                const double combined_term = std::pow(
                    (shear_weight * shear_term + fiber_weight * fiber_term) / term_weight_sum,
                    1.0 / p_norm);

                std::array<std::pair<int, int>, 4> qedges = {
                    std::make_pair(i0, i1),
                    std::make_pair(i1, i2),
                    std::make_pair(i2, i3),
                    std::make_pair(i3, i0),
                };

                long edges_applied = 0;
                for (const auto &qe : qedges)
                {
                    auto it = edge_lookup.find(edge_key(qe.first, qe.second));
                    if (it == edge_lookup.end())
                    {
                        continue;
                    }
                    const size_t ei = it->second;
                    if (ei >= edge_targets.size() || ei >= edge_weights.size())
                    {
                        continue;
                    }

                    const double along = (ei < edge_along_primary.size()) ? edge_along_primary[ei] : 0.5;
                    const double transverse_factor = std::clamp(1.0 - along * along, 0.0, 1.0);
                    if (cell_gain > 0.0)
                    {
                        const double weight_factor = 1.0 + cell_gain * combined_term * (0.75 + 0.25 * transverse_factor);
                        edge_weights[ei] *= std::clamp(weight_factor, 0.5, 2.0);

                        const double target_factor = 1.0 + 0.06 * cell_gain * (shear_norm * transverse_factor + 0.5 * fiber_norm * (1.0 - along));
                        edge_targets[ei] *= std::clamp(target_factor, 0.8, 1.25);
                    }
                    ++edges_applied;
                }

                if (edges_applied <= 0)
                {
                    continue;
                }

                ++objective_summary.cell_count;
                cell_shear_abs_sum_deg += shear_abs_rad * (180.0 / pi);
                cell_shear_signed_sum_deg += shear_signed_rad * (180.0 / pi);
                cell_shear_target_err_sum_deg += shear_target_error_rad * (180.0 / pi);
                cell_fiber_angle_sum_deg += fiber_angle_rad * (180.0 / pi);
                cell_objective_sum += combined_term;
            }

            if (objective_summary.cell_count > 0)
            {
                objective_summary.cell_shear_abs_mean_deg =
                    cell_shear_abs_sum_deg / static_cast<double>(objective_summary.cell_count);
                objective_summary.cell_shear_signed_mean_deg =
                    cell_shear_signed_sum_deg / static_cast<double>(objective_summary.cell_count);
                objective_summary.cell_shear_target_error_mean_deg =
                    cell_shear_target_err_sum_deg / static_cast<double>(objective_summary.cell_count);
                objective_summary.cell_fiber_angle_mean_deg =
                    cell_fiber_angle_sum_deg / static_cast<double>(objective_summary.cell_count);
                objective_summary.cell_combined_objective_mean =
                    cell_objective_sum / static_cast<double>(objective_summary.cell_count);
            }
        }

        objective_summary.edge_count = static_cast<long>(edges.size());
        objective_summary.signed_shear_proxy_mean = safe_mean(signed_shear_proxy_sum, shear_proxy_count, 0.0);
        objective_summary.abs_shear_proxy_mean = safe_mean(abs_shear_proxy_sum, shear_proxy_count, 0.0);

        double target_scale_sum = 0.0;
        double weight_sum = 0.0;
        double target_scale_min = std::numeric_limits<double>::infinity();
        double target_scale_max = 0.0;
        double weight_min = std::numeric_limits<double>::infinity();
        double weight_max = 0.0;

        double primary_target_sum = 0.0;
        double transverse_target_sum = 0.0;
        double bias_target_sum = 0.0;
        double primary_weight_sum = 0.0;
        double transverse_weight_sum = 0.0;
        double bias_weight_sum = 0.0;
        double positive_bias_target_sum = 0.0;
        double negative_bias_target_sum = 0.0;

        for (size_t ei = 0; ei < edge_targets.size(); ++ei)
        {
            const double target = edge_targets[ei];
            const double weight = edge_weights[ei];
            const double along_primary = (ei < edge_along_primary.size()) ? edge_along_primary[ei] : 0.5;
            const double signed_transverse = (ei < edge_signed_transverse.size()) ? edge_signed_transverse[ei] : 0.0;

            const double target_scale = (nominal > kVectorZeroEpsilon) ? (target / nominal) : 1.0;
            target_scale_sum += target_scale;
            weight_sum += weight;
            target_scale_min = std::min(target_scale_min, target_scale);
            target_scale_max = std::max(target_scale_max, target_scale);
            weight_min = std::min(weight_min, weight);
            weight_max = std::max(weight_max, weight);

            const int bucket = classify_orientation(along_primary);
            if (bucket == 0)
            {
                ++objective_summary.primary_edge_count;
                primary_target_sum += target_scale;
                primary_weight_sum += weight;
            }
            else if (bucket == 1)
            {
                ++objective_summary.transverse_edge_count;
                transverse_target_sum += target_scale;
                transverse_weight_sum += weight;
            }
            else
            {
                ++objective_summary.bias_edge_count;
                bias_target_sum += target_scale;
                bias_weight_sum += weight;
                if (signed_transverse >= 0.0)
                {
                    ++objective_summary.positive_bias_edge_count;
                    positive_bias_target_sum += target_scale;
                }
                else
                {
                    ++objective_summary.negative_bias_edge_count;
                    negative_bias_target_sum += target_scale;
                }
            }
        }

        if (objective_summary.edge_count > 0)
        {
            objective_summary.target_scale_mean = target_scale_sum / static_cast<double>(objective_summary.edge_count);
            objective_summary.weight_mean = weight_sum / static_cast<double>(objective_summary.edge_count);
            objective_summary.target_scale_min = std::isfinite(target_scale_min) ? target_scale_min : 1.0;
            objective_summary.target_scale_max = std::isfinite(target_scale_max) ? target_scale_max : 1.0;
            objective_summary.weight_min = std::isfinite(weight_min) ? weight_min : 1.0;
            objective_summary.weight_max = std::isfinite(weight_max) ? weight_max : 1.0;
        }

        objective_summary.primary_target_scale_mean = safe_mean(primary_target_sum, objective_summary.primary_edge_count);
        objective_summary.transverse_target_scale_mean = safe_mean(transverse_target_sum, objective_summary.transverse_edge_count);
        objective_summary.bias_target_scale_mean = safe_mean(bias_target_sum, objective_summary.bias_edge_count);
        objective_summary.primary_weight_mean = safe_mean(primary_weight_sum, objective_summary.primary_edge_count);
        objective_summary.transverse_weight_mean = safe_mean(transverse_weight_sum, objective_summary.transverse_edge_count);
        objective_summary.bias_weight_mean = safe_mean(bias_weight_sum, objective_summary.bias_edge_count);
        objective_summary.positive_bias_target_scale_mean = safe_mean(
            positive_bias_target_sum,
            objective_summary.positive_bias_edge_count,
            objective_summary.bias_target_scale_mean);
        objective_summary.negative_bias_target_scale_mean = safe_mean(
            negative_bias_target_sum,
            objective_summary.negative_bias_edge_count,
            objective_summary.bias_target_scale_mean);

        objective_summary.signed_bias_target_asymmetry =
            objective_summary.positive_bias_target_scale_mean - objective_summary.negative_bias_target_scale_mean;

        if (objective_summary.primary_target_scale_mean > kVectorZeroEpsilon)
        {
            objective_summary.target_anisotropy_ratio =
                objective_summary.transverse_target_scale_mean / objective_summary.primary_target_scale_mean;
        }
        if (objective_summary.transverse_weight_mean > kVectorZeroEpsilon)
        {
            objective_summary.weight_anisotropy_ratio =
                objective_summary.primary_weight_mean / objective_summary.transverse_weight_mean;
        }
    }

} // namespace fishnet_internal
