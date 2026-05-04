#include "fishnet_boundary_atlas.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <unordered_map>
#include <unordered_set>
#include <utility>

#include "fishnet_diagnostics_api.hpp"
#include "fishnet_layout_geometry_api.hpp"
#include "fishnet_options_api.hpp"
#include "fishnet_result_api.hpp"
#include "fishnet_sampling_api.hpp"

namespace fishnet_internal
{
    namespace boundary_atlas
    {

        namespace
        {

            struct BoundaryGraphData
            {
                std::unordered_map<uint64_t, int> counts;
                std::unordered_map<uint64_t, std::pair<int, int>> oriented;
            };

            BoundaryGraphData build_boundary_graph_data(const std::vector<std::array<int, 3>> &faces)
            {
                BoundaryGraphData data;
                for (const auto &face : faces)
                {
                    for (int k = 0; k < 3; ++k)
                    {
                        int a = face[static_cast<size_t>(k)];
                        int b = face[static_cast<size_t>((k + 1) % 3)];
                        uint64_t key = edge_key(a, b);
                        data.counts[key] += 1;
                        data.oriented.emplace(key, std::make_pair(a, b));
                    }
                }
                return data;
            }

            void append_boundary_edges(
                const BoundaryGraphData &data,
                std::unordered_map<int, std::vector<int>> &adjacency,
                std::vector<std::pair<int, int>> &boundary_edges)
            {
                for (const auto &entry : data.counts)
                {
                    if (entry.second != 1)
                    {
                        continue;
                    }
                    const auto &edge = data.oriented.at(entry.first);
                    boundary_edges.push_back(edge);
                    adjacency[edge.first].push_back(edge.second);
                    adjacency[edge.second].push_back(edge.first);
                }
            }

            std::vector<int> trace_boundary_loop(
                int start,
                int next,
                const std::unordered_map<int, std::vector<int>> &adjacency,
                std::unordered_set<uint64_t> &visited)
            {
                std::vector<int> path{start, next};
                visited.insert(edge_key(start, next));
                int prev = start;
                int cur = next;

                while (true)
                {
                    auto it = adjacency.find(cur);
                    if (it == adjacency.end())
                    {
                        break;
                    }
                    std::vector<int> candidates;
                    for (int nxt : it->second)
                    {
                        if (nxt == prev || visited.count(edge_key(cur, nxt)) > 0)
                        {
                            continue;
                        }
                        candidates.push_back(nxt);
                    }
                    if (candidates.empty())
                    {
                        break;
                    }
                    std::sort(candidates.begin(), candidates.end());
                    int nxt = candidates.front();
                    visited.insert(edge_key(cur, nxt));
                    path.push_back(nxt);
                    prev = cur;
                    cur = nxt;
                    if (cur == path.front())
                    {
                        break;
                    }
                }
                return path;
            }

            bool chart_overlaps_poly(
                const AtlasChartBuild &chart,
                const std::array<std::array<double, 2>, 4> &poly)
            {
                for (const auto &existing : chart.quad_polys)
                {
                    if (quads_overlap(poly, existing, kOverlapEpsilon))
                    {
                        return true;
                    }
                }
                return false;
            }

            void append_quad_to_chart(
                AtlasChartBuild &chart,
                const std::vector<Vec3> &fabric_points,
                const std::vector<int> &quad,
                const std::array<std::array<double, 2>, 4> &poly)
            {
                std::vector<int> local_quad;
                local_quad.reserve(4);
                for (int gidx : quad)
                {
                    auto it = chart.global_to_local.find(gidx);
                    if (it != chart.global_to_local.end())
                    {
                        local_quad.push_back(it->second);
                        continue;
                    }
                    int lidx = static_cast<int>(chart.points.size());
                    chart.global_to_local[gidx] = lidx;
                    chart.points.push_back(fabric_points[static_cast<size_t>(gidx)]);
                    local_quad.push_back(lidx);
                }
                chart.quads.push_back(std::move(local_quad));
                chart.quad_polys.push_back(poly);
            }

            AtlasChartBuild build_single_quad_chart(
                const std::vector<Vec3> &fabric_points,
                const std::vector<int> &quad,
                const std::array<std::array<double, 2>, 4> &poly)
            {
                AtlasChartBuild chart;
                append_quad_to_chart(chart, fabric_points, quad, poly);
                return chart;
            }

            bool overlaps_existing_charts(
                const std::vector<AtlasChartBuild> &charts,
                const std::array<std::array<double, 2>, 4> &poly)
            {
                for (const auto &chart : charts)
                {
                    if (chart_overlaps_poly(chart, poly))
                    {
                        return true;
                    }
                }
                return false;
            }

        } // namespace

        std::vector<std::vector<int>> boundary_loops(const std::vector<std::array<int, 3>> &faces)
        {
            const BoundaryGraphData data = build_boundary_graph_data(faces);
            std::unordered_map<int, std::vector<int>> adjacency;
            std::vector<std::pair<int, int>> boundary_edges;
            boundary_edges.reserve(data.counts.size());
            append_boundary_edges(data, adjacency, boundary_edges);

            std::unordered_set<uint64_t> visited;
            std::vector<std::vector<int>> loops;
            for (const auto &edge : boundary_edges)
            {
                if (visited.count(edge_key(edge.first, edge.second)) > 0)
                {
                    continue;
                }
                auto loop = trace_boundary_loop(edge.first, edge.second, adjacency, visited);
                if (loop.size() >= 2)
                {
                    loops.push_back(std::move(loop));
                }
            }
            return loops;
        }

        std::vector<Vec3> loop_to_points(const std::vector<int> &loop, const std::vector<Vec3> &fabric_points)
        {
            std::vector<Vec3> coords;
            coords.reserve(loop.size() + 1);
            for (int idx : loop)
            {
                coords.push_back(fabric_points[static_cast<size_t>(idx)]);
            }
            if (!coords.empty() &&
                !(coords.front().x == coords.back().x && coords.front().y == coords.back().y && coords.front().z == coords.back().z))
            {
                coords.push_back(coords.front());
            }
            return coords;
        }

        std::array<std::array<double, 2>, 4> quad_poly2d(const std::vector<Vec3> &points, const std::vector<int> &quad)
        {
            std::array<std::array<double, 2>, 4> poly{};
            for (size_t i = 0; i < 4; ++i)
            {
                int idx = quad[i];
                poly[i] = {points[static_cast<size_t>(idx)].x, points[static_cast<size_t>(idx)].y};
            }
            return poly;
        }

        std::vector<AtlasChartBuild> split_into_non_overlapping_charts(
            const std::vector<Vec3> &fabric_points,
            const std::vector<std::vector<int>> &quads,
            int &overlap_rejections)
        {
            std::vector<AtlasChartBuild> charts;
            overlap_rejections = 0;

            for (const auto &quad : quads)
            {
                if (quad.size() < 4)
                {
                    continue;
                }
                auto poly = quad_poly2d(fabric_points, quad);
                bool placed = false;
                for (auto &chart : charts)
                {
                    if (chart_overlaps_poly(chart, poly))
                    {
                        continue;
                    }
                    append_quad_to_chart(chart, fabric_points, quad, poly);
                    placed = true;
                    break;
                }
                if (placed)
                {
                    continue;
                }
                if (overlaps_existing_charts(charts, poly))
                {
                    ++overlap_rejections;
                }
                charts.push_back(build_single_quad_chart(fabric_points, quad, poly));
            }
            return charts;
        }

        namespace
        {

            struct Match
            {
                size_t prev_idx{0};
                size_t curr_idx{0};
                double d2{0.0};
            };

            struct Rotation2D
            {
                bool valid{false};
                double c{1.0};
                double s{0.0};
            };

            bool unit_2d(double x, double y, double &ux, double &uy)
            {
                double n = std::sqrt(x * x + y * y);
                if (n <= kVectorZeroEpsilon)
                {
                    return false;
                }
                ux = x / n;
                uy = y / n;
                return true;
            }

            std::vector<Match> collect_nearest_matches(const FaceSample &prev, const FaceSample &curr)
            {
                std::vector<Match> matches;
                matches.reserve(curr.points.size());
                for (size_t j = 0; j < curr.points.size(); ++j)
                {
                    const Vec3 &b = curr.points[j];
                    double best_d2 = std::numeric_limits<double>::infinity();
                    size_t best_i = 0;
                    for (size_t i = 0; i < prev.points.size(); ++i)
                    {
                        const Vec3 &a = prev.points[i];
                        double dx = a.x - b.x;
                        double dy = a.y - b.y;
                        double dz = a.z - b.z;
                        double d2 = dx * dx + dy * dy + dz * dz;
                        if (d2 < best_d2)
                        {
                            best_d2 = d2;
                            best_i = i;
                        }
                    }
                    if (std::isfinite(best_d2))
                    {
                        matches.push_back({best_i, j, best_d2});
                    }
                }
                return matches;
            }

            bool anchor_from_matches(
                const std::vector<Match> &matches,
                size_t &anchor_prev,
                size_t &anchor_curr,
                double &best_d2)
            {
                best_d2 = std::numeric_limits<double>::infinity();
                for (const auto &m : matches)
                {
                    if (m.d2 >= best_d2)
                    {
                        continue;
                    }
                    best_d2 = m.d2;
                    anchor_prev = m.prev_idx;
                    anchor_curr = m.curr_idx;
                }
                return std::isfinite(best_d2);
            }

            std::vector<Match> close_matches(
                const std::vector<Match> &matches,
                double tol2,
                size_t anchor_prev,
                size_t anchor_curr,
                double best_d2)
            {
                std::vector<Match> close;
                for (const auto &m : matches)
                {
                    if (m.d2 <= tol2)
                    {
                        close.push_back(m);
                    }
                }
                if (close.empty())
                {
                    close.push_back({anchor_prev, anchor_curr, best_d2});
                }
                return close;
            }

            Rotation2D layout_rotation(
                const FaceSample &prev,
                const FaceSample &curr,
                const std::vector<Match> &matches,
                size_t anchor_prev,
                size_t anchor_curr)
            {
                Vec3 prev_dir{1.0, 0.0, 0.0};
                Vec3 curr_dir{1.0, 0.0, 0.0};
                double best_dir_norm = 0.0;
                const Vec3 &prev_anchor_lp = prev.layout_points[anchor_prev];
                const Vec3 &curr_anchor_lp = curr.layout_points[anchor_curr];

                for (const auto &m : matches)
                {
                    if (m.prev_idx == anchor_prev || m.curr_idx == anchor_curr)
                    {
                        continue;
                    }
                    Vec3 pv = prev.layout_points[m.prev_idx] - prev_anchor_lp;
                    Vec3 cv = curr.layout_points[m.curr_idx] - curr_anchor_lp;
                    double n = std::min(std::sqrt(pv.x * pv.x + pv.y * pv.y), std::sqrt(cv.x * cv.x + cv.y * cv.y));
                    if (n > best_dir_norm)
                    {
                        best_dir_norm = n;
                        prev_dir = pv;
                        curr_dir = cv;
                    }
                }

                double pnx = 0.0, pny = 0.0, cnx = 0.0, cny = 0.0;
                if (best_dir_norm <= kVectorZeroEpsilon || !unit_2d(prev_dir.x, prev_dir.y, pnx, pny) || !unit_2d(curr_dir.x, curr_dir.y, cnx, cny))
                {
                    return {};
                }
                return {true, cnx * pnx + cny * pny, cnx * pny - cny * pnx};
            }

            Rotation2D basis_rotation(
                const FaceSample &prev,
                const FaceSample &curr,
                const std::vector<Match> &matches,
                size_t anchor_prev,
                size_t anchor_curr)
            {
                double best_edge_len = 0.0;
                Vec3 shared_tangent{0.0, 0.0, 0.0};
                const Vec3 &anchor_prev_point = prev.points[anchor_prev];
                for (const auto &m : matches)
                {
                    if (m.prev_idx == anchor_prev || m.curr_idx == anchor_curr)
                    {
                        continue;
                    }
                    Vec3 edge_vec = prev.points[m.prev_idx] - anchor_prev_point;
                    double edge_len = norm(edge_vec);
                    if (edge_len > best_edge_len)
                    {
                        best_edge_len = edge_len;
                        shared_tangent = edge_vec;
                    }
                }
                if (best_edge_len <= kVectorZeroEpsilon)
                {
                    return {};
                }

                shared_tangent = normalize(shared_tangent);
                double ptx = dot(shared_tangent, prev.x_axis), pty = dot(shared_tangent, prev.y_axis);
                double ctx = dot(shared_tangent, curr.x_axis), cty = dot(shared_tangent, curr.y_axis);
                double pnx = 0.0, pny = 0.0, cnx = 0.0, cny = 0.0;
                if (!unit_2d(ptx, pty, pnx, pny) || !unit_2d(ctx, cty, cnx, cny))
                {
                    return {};
                }
                return {true, cnx * pnx + cny * pny, cnx * pny - cny * pnx};
            }

            Rotation2D blend_rotation_estimates(const Rotation2D &layout, const Rotation2D &basis)
            {
                Rotation2D out;
                if (layout.valid && basis.valid)
                {
                    out.c = layout.c + basis.c;
                    out.s = layout.s + basis.s;
                    out.valid = true;
                }
                else if (basis.valid)
                {
                    out = basis;
                }
                else if (layout.valid)
                {
                    out = layout;
                }
                double nrm = std::sqrt(out.c * out.c + out.s * out.s);
                if (nrm <= kVectorZeroEpsilon)
                {
                    return {false, 1.0, 0.0};
                }
                out.c /= nrm;
                out.s /= nrm;
                return out;
            }

            Vec3 rotate_xy(const Vec3 &p, const Rotation2D &r)
            {
                return {r.c * p.x - r.s * p.y, r.s * p.x + r.c * p.y, p.z};
            }

        } // namespace

        void transfer_layout_between_faces(const FaceSample &prev, FaceSample &curr)
        {
            if (prev.points.empty() || prev.layout_points.empty() || curr.points.empty() || curr.layout_points.empty())
            {
                return;
            }

            auto matches = collect_nearest_matches(prev, curr);
            size_t anchor_prev = 0;
            size_t anchor_curr = 0;
            double best_d2 = 0.0;
            if (matches.empty() || !anchor_from_matches(matches, anchor_prev, anchor_curr, best_d2))
            {
                return;
            }

            double span = std::max(point_set_span(prev.points), point_set_span(curr.points));
            double tol = std::max(1.0e-6, span * 0.05);
            auto near = close_matches(matches, tol * tol, anchor_prev, anchor_curr, best_d2);

            Rotation2D layout = layout_rotation(prev, curr, near, anchor_prev, anchor_curr);
            Rotation2D basis = basis_rotation(prev, curr, near, anchor_prev, anchor_curr);
            Rotation2D rot = blend_rotation_estimates(layout, basis);

            const Vec3 &prev_anchor_lp = prev.layout_points[anchor_prev];
            const Vec3 &curr_anchor_lp = curr.layout_points[anchor_curr];
            Vec3 translation = prev_anchor_lp - rotate_xy(curr_anchor_lp, rot);
            for (auto &lp : curr.layout_points)
            {
                lp = rotate_xy(lp, rot) + translation;
            }
        }

    } // namespace boundary_atlas
} // namespace fishnet_internal
