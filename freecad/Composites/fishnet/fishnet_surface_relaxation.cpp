#include "fishnet_surface_relaxation.hpp"

#include <algorithm>
#include <cmath>

#include <gp_Pnt.hxx>

#include "fishnet_surface_queries.hpp"

namespace fishnet_internal
{

    namespace
    {

        double relaxation_objective(
            int i,
            int j,
            double cu,
            double cv,
            const Vec3 &point,
            const SurfaceRelaxationInput &input)
        {
            double score = 0.0;
            auto add_neighbor = [&](int ni, int nj)
            {
                if (ni < 0 || nj < 0 || ni > input.grid.divisions || nj > input.grid.divisions)
                {
                    return;
                }
                int nidx = input.grid.grid_indices[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
                if (nidx < 0 || nidx >= static_cast<int>(input.points.size()))
                {
                    return;
                }

                double distance = norm(input.points[static_cast<size_t>(nidx)] - point);
                double nu = input.grid.grid_u[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
                double nv = input.grid.grid_v[static_cast<size_t>(ni)][static_cast<size_t>(nj)];
                if (std::isfinite(cu) && std::isfinite(cv) && std::isfinite(nu) && std::isfinite(nv))
                {
                    double geodesic = surface_queries::approx_surface_distance_uv(input.surface, cu, cv, nu, nv);
                    if (std::isfinite(geodesic) && geodesic > kVectorZeroEpsilon)
                    {
                        distance = geodesic;
                    }
                }

                double rel = std::abs(distance - input.grid.target_spacing_len) / input.grid.target_spacing_len;
                score += rel * rel;
            };

            add_neighbor(i - 1, j);
            add_neighbor(i + 1, j);
            add_neighbor(i, j - 1);
            add_neighbor(i, j + 1);
            return score;
        }

    } // namespace

    void run_surface_relaxation(const SurfaceRelaxationInput &input)
    {
        const int relax_iters = std::max(1, input.iterations);

        for (int relax_iter = 0; relax_iter < relax_iters; ++relax_iter)
        {
            bool changed = false;
            for (int i = 1; i < input.grid.divisions; ++i)
            {
                for (int j = 1; j < input.grid.divisions; ++j)
                {
                    int idx = input.grid.grid_indices[static_cast<size_t>(i)][static_cast<size_t>(j)];
                    if (idx < 0 || idx >= static_cast<int>(input.points.size()))
                    {
                        continue;
                    }
                    double u = input.grid.grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)];
                    double v = input.grid.grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)];
                    if (!std::isfinite(u) || !std::isfinite(v))
                    {
                        continue;
                    }

                    Vec3 best_point = input.points[static_cast<size_t>(idx)];
                    double best_u = u;
                    double best_v = v;
                    double best_score = relaxation_objective(i, j, u, v, best_point, input);

                    auto try_pair = [&](int ib, int jb, int ic, int jc)
                    {
                        int idx_b = input.grid.grid_indices[static_cast<size_t>(ib)][static_cast<size_t>(jb)];
                        int idx_c = input.grid.grid_indices[static_cast<size_t>(ic)][static_cast<size_t>(jc)];
                        if (idx_b < 0 || idx_c < 0 ||
                            idx_b >= static_cast<int>(input.points.size()) ||
                            idx_c >= static_cast<int>(input.points.size()))
                        {
                            return;
                        }

                        double su = u;
                        double sv = v;
                        bool solved = surface_queries::solve_uv_two_distance_constraints_spheresurface(
                            input.face,
                            input.surface,
                            su,
                            sv,
                            input.points[static_cast<size_t>(idx_b)],
                            input.grid.target_spacing_len,
                            input.points[static_cast<size_t>(idx_c)],
                            input.grid.target_spacing_len,
                            input.u0,
                            input.u1,
                            input.v0,
                            input.v1,
                            input.experimental_stats);
                        if (!solved)
                        {
                            return;
                        }

                        gp_Pnt p = input.surface.Value(su, sv);
                        if (!surface_queries::native_face_is_inside(input.face, p, kFaceInsideTolerance))
                        {
                            return;
                        }

                        Vec3 candidate{p.X(), p.Y(), p.Z()};
                        if (norm(candidate - input.points[static_cast<size_t>(idx)]) > 2.5 * input.grid.target_spacing_len)
                        {
                            return;
                        }

                        double score = relaxation_objective(i, j, su, sv, candidate, input);
                        if (score + 1.0e-12 < best_score)
                        {
                            best_score = score;
                            best_u = su;
                            best_v = sv;
                            best_point = candidate;
                        }
                    };

                    try_pair(i - 1, j, i + 1, j);
                    try_pair(i, j - 1, i, j + 1);
                    if (std::abs(best_u - u) <= 1.0e-12 && std::abs(best_v - v) <= 1.0e-12)
                    {
                        continue;
                    }

                    input.points[static_cast<size_t>(idx)] = best_point;
                    input.grid.grid_u[static_cast<size_t>(i)][static_cast<size_t>(j)] = best_u;
                    input.grid.grid_v[static_cast<size_t>(i)][static_cast<size_t>(j)] = best_v;
                    Vec3 normal{0.0, 0.0, 1.0};
                    surface_queries::native_face_normal_at(input.face, input.surface, best_u, best_v, normal);
                    if (norm(normal) > kVectorZeroEpsilon)
                    {
                        input.grid.grid_normals[static_cast<size_t>(i)][static_cast<size_t>(j)] = normal;
                    }
                    changed = true;
                }
            }

            if (!changed)
            {
                break;
            }
        }
    }

} // namespace fishnet_internal
