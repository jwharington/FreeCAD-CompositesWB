#include "fishnet_sampling_node_update.hpp"

#include <array>
#include <cmath>
#include <limits>
#include <utility>

#include <gp_Pnt.hxx>

#include "fishnet_surface_queries.hpp"

namespace fishnet_internal
{

    namespace
    {

        struct CandidateState
        {
            double u{0.0};
            double v{0.0};
            Vec3 point{0.0, 0.0, 0.0};
            Vec3 normal{0.0, 0.0, 1.0};
            double objective{std::numeric_limits<double>::infinity()};
        };

        std::vector<std::pair<double, double>> build_candidate_start_seeds(double u, double v)
        {
            return {{u, v}};
        }

        double candidate_pair_distance(
            const BRepAdaptor_Surface &surface,
            double su,
            double sv,
            double nu,
            double nv,
            const Vec3 &cand,
            const Vec3 &neighbor)
        {
            double d = norm(cand - neighbor);
            if (!std::isfinite(nu) || !std::isfinite(nv))
            {
                return d;
            }
            double g = surface_queries::approx_surface_distance_uv(surface, su, sv, nu, nv);
            if (std::isfinite(g) && g > kVectorZeroEpsilon)
            {
                return g;
            }
            return d;
        }

        double candidate_objective(
            double rb,
            double rc,
            double db,
            double dc)
        {
            double rel_b = (rb > kVectorZeroEpsilon) ? std::abs(db - rb) / rb : 0.0;
            double rel_c = (rc > kVectorZeroEpsilon) ? std::abs(dc - rc) / rc : 0.0;
            return rel_b * rel_b + rel_c * rel_c;
        }

        bool candidate_motion_ok(
            double rb,
            double rc,
            const Vec3 &old_point,
            const Vec3 &seed_point,
            const Vec3 &cand)
        {
            double max_branch_shift = std::max(4.0 * std::max(rb, rc), 1.0);
            if (norm(cand - old_point) > max_branch_shift)
            {
                return false;
            }
            double max_seed_shift = std::max(12.0 * std::max(rb, rc), 1.0);
            return norm(cand - seed_point) <= max_seed_shift;
        }

        bool adjacent_normals_compatible(
            int divisions,
            int i,
            int j,
            double cos_limit,
            const Vec3 &n_candidate,
            const std::vector<std::vector<int>> &grid_indices,
            const std::vector<std::vector<Vec3>> &grid_normals,
            const std::vector<Vec3> &points)
        {
            const std::array<std::pair<int, int>, 4> neigh = {{{i - 1, j}, {i + 1, j}, {i, j - 1}, {i, j + 1}}};
            for (const auto &ij : neigh)
            {
                int ni = ij.first;
                int nj = ij.second;
                if (ni < 0 || nj < 0 || ni > divisions || nj > divisions)
                {
                    continue;
                }
                int nidx = grid_indices[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
                if (nidx < 0 || nidx >= static_cast<int>(points.size()))
                {
                    continue;
                }
                Vec3 nn = normalize(grid_normals[static_cast<size_t>(ni)][static_cast<size_t>(nj)]);
                if (norm(nn) > kVectorZeroEpsilon && dot(n_candidate, nn) < cos_limit)
                {
                    return false;
                }
            }
            return true;
        }

        bool triangle_ring_compatible(
            int divisions,
            int i,
            int j,
            int idx,
            double cos_limit,
            const Vec3 &new_point,
            const std::vector<Vec3> &points,
            const std::vector<Vec3> &seed_points,
            const std::vector<std::vector<int>> &grid_indices)
        {
            auto idx_at = [&](int ii, int jj)
            {
                if (ii < 0 || jj < 0 || ii > divisions || jj > divisions)
                {
                    return -1;
                }
                return grid_indices[static_cast<size_t>(ii)][static_cast<size_t>(jj)];
            };

            const std::array<std::array<int, 4>, 4> ring = {{
                {{i - 1, j, i, j - 1}},
                {{i, j - 1, i + 1, j}},
                {{i + 1, j, i, j + 1}},
                {{i, j + 1, i - 1, j}},
            }};

            for (const auto &r : ring)
            {
                int n1 = idx_at(r[0], r[1]);
                int n2 = idx_at(r[2], r[3]);
                if (n1 < 0 || n2 < 0 || n1 >= static_cast<int>(points.size()) || n2 >= static_cast<int>(points.size()))
                {
                    continue;
                }
                Vec3 tri_n_new = normalize(cross(points[static_cast<size_t>(n1)] - new_point, points[static_cast<size_t>(n2)] - new_point));
                Vec3 tri_n_seed = normalize(cross(seed_points[static_cast<size_t>(n1)] - seed_points[static_cast<size_t>(idx)],
                                                  seed_points[static_cast<size_t>(n2)] - seed_points[static_cast<size_t>(idx)]));
                if (norm(tri_n_new) > kVectorZeroEpsilon && norm(tri_n_seed) > kVectorZeroEpsilon && dot(tri_n_new, tri_n_seed) < cos_limit)
                {
                    return false;
                }
            }
            return true;
        }

        bool passes_normal_gate(
            double max_adjacent_normal_angle,
            int divisions,
            int i,
            int j,
            int idx,
            const Vec3 &new_point,
            const Vec3 &n_candidate,
            const std::vector<Vec3> &points,
            const std::vector<Vec3> &seed_points,
            const std::vector<std::vector<int>> &grid_indices,
            const std::vector<std::vector<Vec3>> &grid_normals)
        {
            if (!std::isfinite(max_adjacent_normal_angle) ||
                max_adjacent_normal_angle <= 0.0)
            {
                return true;
            }

            double angle = std::min(max_adjacent_normal_angle, 3.14159265358979323846);
            double cos_limit = std::cos(angle);
            if (norm(n_candidate) > kVectorZeroEpsilon &&
                !adjacent_normals_compatible(divisions, i, j, cos_limit, n_candidate, grid_indices, grid_normals, points))
            {
                return false;
            }
            return triangle_ring_compatible(divisions, i, j, idx, cos_limit, new_point, points, seed_points, grid_indices);
        }

        bool passes_fold_gate(
            double max_local_fold_ratio,
            int divisions,
            int i,
            int j,
            double target_spacing_len,
            const Vec3 &new_point,
            const std::vector<Vec3> &points,
            const std::vector<std::vector<int>> &grid_indices)
        {
            if (!(std::isfinite(max_local_fold_ratio) && max_local_fold_ratio > 1.0))
            {
                return true;
            }

            const std::array<std::pair<int, int>, 4> neigh = {{{i - 1, j}, {i + 1, j}, {i, j - 1}, {i, j + 1}}};
            for (const auto &ij : neigh)
            {
                int ni = ij.first;
                int nj = ij.second;
                if (ni < 0 || nj < 0 || ni > divisions || nj > divisions)
                {
                    continue;
                }
                int nidx = grid_indices[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
                if (nidx < 0 || nidx >= static_cast<int>(points.size()) || target_spacing_len <= kVectorZeroEpsilon)
                {
                    continue;
                }
                double d_new = norm(new_point - points[static_cast<size_t>(nidx)]);
                if (d_new > target_spacing_len * max_local_fold_ratio || d_new < target_spacing_len / max_local_fold_ratio)
                {
                    return false;
                }
            }
            return true;
        }

        bool passes_shear_gate(
            double max_shear_angle,
            int divisions,
            int i,
            int j,
            int idx,
            const Vec3 &new_point,
            const std::vector<Vec3> &points,
            const std::vector<std::vector<int>> &grid_indices)
        {
            if (!(std::isfinite(max_shear_angle) && max_shear_angle >= 0.0))
            {
                return true;
            }

            double cos_limit = std::sin(std::min(max_shear_angle, 1.5533430342749532));
            auto shear_idx_at = [&](int ii, int jj)
            {
                if (ii < 0 || jj < 0 || ii > divisions || jj > divisions)
                {
                    return -1;
                }
                int nidx = grid_indices[static_cast<size_t>(ii)][static_cast<size_t>(jj)];
                return (nidx < 0 || nidx >= static_cast<int>(points.size())) ? -1 : nidx;
            };
            auto shear_pair_ok = [&](int i1, int j1, int i2, int j2)
            {
                int n1 = shear_idx_at(i1, j1);
                int n2 = shear_idx_at(i2, j2);
                if (n1 < 0 || n2 < 0 || n1 == idx || n2 == idx || n1 == n2)
                {
                    return true;
                }
                Vec3 v1p = points[static_cast<size_t>(n1)] - new_point;
                Vec3 v2p = points[static_cast<size_t>(n2)] - new_point;
                double n1_len = norm(v1p);
                double n2_len = norm(v2p);
                if (n1_len <= kVectorZeroEpsilon || n2_len <= kVectorZeroEpsilon)
                {
                    return false;
                }
                double cos_angle = dot(v1p, v2p) / (n1_len * n2_len);
                cos_angle = std::max(-1.0, std::min(1.0, cos_angle));
                return std::abs(cos_angle) <= cos_limit;
            };

            return shear_pair_ok(i - 1, j, i, j - 1) &&
                   shear_pair_ok(i, j - 1, i + 1, j) &&
                   shear_pair_ok(i + 1, j, i, j + 1) &&
                   shear_pair_ok(i, j + 1, i - 1, j);
        }

        bool commit_uv_update(
            int i,
            int j,
            int idx,
            double u,
            double v,
            double old_u,
            double old_v,
            const Vec3 &new_point,
            const Vec3 &n,
            std::vector<Vec3> &points,
            std::vector<std::vector<double>> &grid_u,
            std::vector<std::vector<double>> &grid_v,
            std::vector<std::vector<Vec3>> &grid_normals,
            std::vector<std::vector<unsigned char>> &active_nodes)
        {
            points[static_cast<size_t>(idx)] = new_point;
            if (norm(n) > kVectorZeroEpsilon)
            {
                grid_normals[static_cast<size_t>(i)][static_cast<size_t>(j)] = n;
            }
            grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)] = u;
            grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)] = v;
            bool was_active = active_nodes[static_cast<size_t>(i)][static_cast<size_t>(j)] != 0;
            active_nodes[static_cast<size_t>(i)][static_cast<size_t>(j)] = 1;
            return (!was_active) || (std::abs(u - old_u) > 1.0e-9 || std::abs(v - old_v) > 1.0e-9);
        }

        struct UpdateNodeIndices
        {
            int idx{-1};
            int idx_b{-1};
            int idx_c{-1};
            double rb{0.0};
            double rc{0.0};
        };

        bool resolve_update_indices(
            int i,
            int j,
            int ib,
            int jb,
            int ic,
            int jc,
            double rb,
            double rc,
            std::function<int(int, int)> &ensure_grid_node,
            UpdateNodeIndices &out)
        {
            out.rb = rb;
            out.rc = rc;
            out.idx = ensure_grid_node(i, j);
            out.idx_b = ensure_grid_node(ib, jb);
            out.idx_c = ensure_grid_node(ic, jc);

            if (out.idx < 0 || out.idx_b < 0 || out.idx_c < 0)
            {
                return false;
            }
            return out.rb > kVectorZeroEpsilon && out.rc > kVectorZeroEpsilon;
        }

        struct NodeUpdateRequest
        {
            int divisions{0};
            int i{0};
            int j{0};
            int idx{-1};
            int idx_b{-1};
            int idx_c{-1};
            double rb{0.0};
            double rc{0.0};
            double target_spacing_len{0.0};
            double u{0.0};
            double v{0.0};
            double u0{0.0};
            double u1{0.0};
            double v0{0.0};
            double v1{0.0};
            double ub{0.0};
            double vb{0.0};
            double uc{0.0};
            double vc{0.0};
            Vec3 old_point{0.0, 0.0, 0.0};
        };

        class NodeUpdateEvaluator
        {
        public:
            NodeUpdateEvaluator(
                const TopoDS_Face &face,
                const BRepAdaptor_Surface &surface,
                double max_adjacent_normal_angle,
                double max_local_fold_ratio,
                double max_shear_angle,
                const std::vector<Vec3> &points,
                const std::vector<Vec3> &seed_points,
                const std::vector<std::vector<int>> &grid_indices,
                const std::vector<std::vector<Vec3>> &grid_normals,
                ExperimentalSolveStats *experimental_stats)
                : face_(face),
                  surface_(surface),
                  max_adjacent_normal_angle_(max_adjacent_normal_angle),
                  max_local_fold_ratio_(max_local_fold_ratio),
                  max_shear_angle_(max_shear_angle),
                  points_(points),
                  seed_points_(seed_points),
                  grid_indices_(grid_indices),
                  grid_normals_(grid_normals),
                  experimental_stats_(experimental_stats)
            {
            }

            bool select_best_candidate(const NodeUpdateRequest &request, CandidateState &best) const
            {
                auto start_seeds = build_candidate_start_seeds(request.u, request.v);

                bool have_candidate = false;
                for (const auto &seed : start_seeds)
                {
                    double su = seed.first;
                    double sv = seed.second;
                    if (!surface_queries::solve_uv_two_distance_constraints_spheresurface(
                            face_,
                            surface_,
                            su,
                            sv,
                            points_[static_cast<size_t>(request.idx_b)],
                            request.rb,
                            points_[static_cast<size_t>(request.idx_c)],
                            request.rc,
                            request.u0,
                            request.u1,
                            request.v0,
                            request.v1,
                            experimental_stats_))
                    {
                        continue;
                    }

                    gp_Pnt p = surface_.Value(su, sv);
                    if (!surface_queries::native_face_is_inside(face_, p, kFaceInsideTolerance))
                    {
                        continue;
                    }

                    Vec3 cand_point{p.X(), p.Y(), p.Z()};
                    if (!candidate_motion_ok(
                            request.rb,
                            request.rc,
                            request.old_point,
                            seed_points_[static_cast<size_t>(request.idx)],
                            cand_point))
                    {
                        continue;
                    }

                    double db = candidate_pair_distance(surface_, su, sv, request.ub, request.vb, cand_point, points_[static_cast<size_t>(request.idx_b)]);
                    double dc = candidate_pair_distance(surface_, su, sv, request.uc, request.vc, cand_point, points_[static_cast<size_t>(request.idx_c)]);
                    double objective = candidate_objective(
                        request.rb,
                        request.rc,
                        db,
                        dc);

                    if (have_candidate && objective >= best.objective)
                    {
                        continue;
                    }

                    Vec3 cand_n{0.0, 0.0, 1.0};
                    surface_queries::native_face_normal_at(face_, surface_, su, sv, cand_n);
                    best.u = su;
                    best.v = sv;
                    best.point = cand_point;
                    best.normal = cand_n;
                    best.objective = objective;
                    have_candidate = true;
                }
                return have_candidate;
            }

            bool passes_all_gates(const NodeUpdateRequest &request, const CandidateState &best) const
            {
                Vec3 n_candidate = normalize(best.normal);
                return passes_normal_gate(
                           max_adjacent_normal_angle_,
                           request.divisions,
                           request.i,
                           request.j,
                           request.idx,
                           best.point,
                           n_candidate,
                           points_,
                           seed_points_,
                           grid_indices_,
                           grid_normals_) &&
                       passes_fold_gate(
                           max_local_fold_ratio_,
                           request.divisions,
                           request.i,
                           request.j,
                           request.target_spacing_len,
                           best.point,
                           points_,
                           grid_indices_) &&
                       passes_shear_gate(
                           max_shear_angle_,
                           request.divisions,
                           request.i,
                           request.j,
                           request.idx,
                           best.point,
                           points_,
                           grid_indices_);
            }

        private:
            const TopoDS_Face &face_;
            const BRepAdaptor_Surface &surface_;
            double max_adjacent_normal_angle_;
            double max_local_fold_ratio_;
            double max_shear_angle_;
            const std::vector<Vec3> &points_;
            const std::vector<Vec3> &seed_points_;
            const std::vector<std::vector<int>> &grid_indices_;
            const std::vector<std::vector<Vec3>> &grid_normals_;
            ExperimentalSolveStats *experimental_stats_;
        };

    } // namespace

    NodeUpdateContext::NodeUpdateContext(const NodeUpdateContextInput &input)
        : face_(input.face),
          surface_(input.surface),
          max_adjacent_normal_angle_(input.max_adjacent_normal_angle),
          max_local_fold_ratio_(input.max_local_fold_ratio),
          max_shear_angle_(input.max_shear_angle),
          grid_(input.grid),
          u0_(input.u0),
          u1_(input.u1),
          v0_(input.v0),
          v1_(input.v1),
          points_(input.points),
          ensure_grid_node_(input.ensure_grid_node),
          experimental_stats_(input.experimental_stats)
    {
    }

    bool NodeUpdateContext::attempt(int i, int j, int ib, int jb, int ic, int jc, double rb, double rc)
    {
        UpdateNodeIndices node{};
        if (!resolve_update_indices(
                i,
                j,
                ib,
                jb,
                ic,
                jc,
                rb,
                rc,
                ensure_grid_node_,
                node))
        {
            return false;
        }

        double u = std::isfinite(grid_.grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)])
                       ? grid_.grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)]
                       : (u0_ + (u1_ - u0_) * static_cast<double>(i) / static_cast<double>(grid_.divisions));
        double v = std::isfinite(grid_.grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)])
                       ? grid_.grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)]
                       : (v0_ + (v1_ - v0_) * static_cast<double>(j) / static_cast<double>(grid_.divisions));
        double old_u = u;
        double old_v = v;
        Vec3 old_point = points_[static_cast<size_t>(node.idx)];

        double ub = grid_.grid_u[static_cast<size_t>(ib)][static_cast<size_t>(jb)];
        double vb = grid_.grid_v[static_cast<size_t>(ib)][static_cast<size_t>(jb)];
        double uc = grid_.grid_u[static_cast<size_t>(ic)][static_cast<size_t>(jc)];
        double vc = grid_.grid_v[static_cast<size_t>(ic)][static_cast<size_t>(jc)];

        NodeUpdateRequest request{};
        request.divisions = grid_.divisions;
        request.i = i;
        request.j = j;
        request.idx = node.idx;
        request.idx_b = node.idx_b;
        request.idx_c = node.idx_c;
        request.rb = node.rb;
        request.rc = node.rc;
        request.target_spacing_len = grid_.target_spacing_len;
        request.u = u;
        request.v = v;
        request.u0 = u0_;
        request.u1 = u1_;
        request.v0 = v0_;
        request.v1 = v1_;
        request.ub = ub;
        request.vb = vb;
        request.uc = uc;
        request.vc = vc;
        request.old_point = old_point;

        NodeUpdateEvaluator evaluator(
            face_,
            surface_,
            max_adjacent_normal_angle_,
            max_local_fold_ratio_,
            max_shear_angle_,
            points_,
            grid_.seed_points,
            grid_.grid_indices,
            grid_.grid_normals,
            experimental_stats_);

        CandidateState best{};
        if (!evaluator.select_best_candidate(request, best))
        {
            return false;
        }
        if (!evaluator.passes_all_gates(request, best))
        {
            return false;
        }

        return commit_uv_update(
            i,
            j,
            node.idx,
            best.u,
            best.v,
            old_u,
            old_v,
            best.point,
            best.normal,
            points_,
            grid_.grid_u,
            grid_.grid_v,
            grid_.grid_normals,
            grid_.active_nodes);
    }

} // namespace fishnet_internal
