#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <vector>

#include <BRepAdaptor_Surface.hxx>
#include <GeomAbs_SurfaceType.hxx>
#include <TopoDS_Face.hxx>
#include "fishnet_primitives.hpp"
#include "fishnet_surface_queries.hpp"

namespace fishnet_internal
{

    struct MetricCellResidualDiagnostics
    {
        long cell_count_total{0};
        long cell_count_valid{0};
        long cell_count_invalid{0};
        double eq410_residual_mean{0.0};
        double eq410_residual_max{0.0};
        double eq410_residual_p95{0.0};
        double eq411_residual_mean{0.0};
        double eq411_residual_max{0.0};
        double eq411_residual_p95{0.0};
        double eq412_residual_mean{0.0};
        double eq412_residual_max{0.0};
        double eq412_residual_p95{0.0};
        double residual_combined_l2{0.0};
        double residual_combined_linf{0.0};
        double residual_combined_p95{0.0};
        double cell_valid_ratio{0.0};
        double cell_invalid_ratio{0.0};
    };

    inline double finite_or_zero(double value)
    {
        return std::isfinite(value) ? value : 0.0;
    }

    inline double percentile95_abs(const std::vector<double> &values)
    {
        if (values.empty())
        {
            return 0.0;
        }

        std::vector<double> sorted = values;
        std::sort(sorted.begin(), sorted.end());

        const double position = 0.95 * static_cast<double>(sorted.size() - 1);
        const size_t lower = static_cast<size_t>(position);
        const size_t upper = std::min(lower + 1, sorted.size() - 1);
        const double blend = position - static_cast<double>(lower);

        const double lower_value = sorted[lower];
        const double upper_value = sorted[upper];
        const double p95 = lower_value + (upper_value - lower_value) * blend;
        return finite_or_zero(p95);
    }

    inline MetricCellResidualDiagnostics compute_metric_cell_residual_diagnostics(
        const std::vector<Vec3> &surface_points,
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::vector<int>> &cells,
        const std::vector<TopoDS_Face> *native_faces = nullptr,
        const std::vector<std::array<double, 2>> *point_uv = nullptr,
        const std::vector<int> *point_face_indices = nullptr)
    {
        MetricCellResidualDiagnostics diagnostics;
        diagnostics.cell_count_total = static_cast<long>(cells.size());

        if (surface_points.empty() || fabric_points.empty() || cells.empty())
        {
            return diagnostics;
        }

        constexpr double kMetricDenominatorEps = 1.0e-12;

        double eq410_sum_abs = 0.0;
        double eq411_sum_abs = 0.0;
        double eq412_sum_abs = 0.0;
        double eq410_max_abs = 0.0;
        double eq411_max_abs = 0.0;
        double eq412_max_abs = 0.0;

        double combined_sum_sq = 0.0;
        double combined_linf = 0.0;

        std::vector<double> eq410_abs_values;
        std::vector<double> eq411_abs_values;
        std::vector<double> eq412_abs_values;
        std::vector<double> combined_abs_values;
        eq410_abs_values.reserve(cells.size());
        eq411_abs_values.reserve(cells.size());
        eq412_abs_values.reserve(cells.size());
        combined_abs_values.reserve(cells.size());

        auto valid_index = [](int idx, size_t size)
        {
            return idx >= 0 && static_cast<size_t>(idx) < size;
        };

        auto finite_uv = [](const std::array<double, 2> &uv)
        {
            return std::isfinite(uv[0]) && std::isfinite(uv[1]);
        };

        std::vector<BRepAdaptor_Surface> surfaces;
        if (native_faces && !native_faces->empty())
        {
            surfaces.reserve(native_faces->size());
            for (const auto &face : *native_faces)
            {
                surfaces.emplace_back(face, Standard_True);
            }
        }

        for (const auto &cell : cells)
        {
            if (cell.size() < 4)
            {
                diagnostics.cell_count_invalid += 1;
                continue;
            }

            const int a = cell[0];
            const int b = cell[1];
            const int c = cell[2];
            const int d = cell[3];

            if (!valid_index(a, surface_points.size()) ||
                !valid_index(b, surface_points.size()) ||
                !valid_index(c, surface_points.size()) ||
                !valid_index(d, surface_points.size()) ||
                !valid_index(a, fabric_points.size()) ||
                !valid_index(b, fabric_points.size()) ||
                !valid_index(c, fabric_points.size()) ||
                !valid_index(d, fabric_points.size()))
            {
                diagnostics.cell_count_invalid += 1;
                continue;
            }

            const Vec3 &sa = surface_points[static_cast<size_t>(a)];
            const Vec3 &sb = surface_points[static_cast<size_t>(b)];
            const Vec3 &sc = surface_points[static_cast<size_t>(c)];
            const Vec3 &sd = surface_points[static_cast<size_t>(d)];

            const Vec3 &fa = fabric_points[static_cast<size_t>(a)];
            const Vec3 &fb = fabric_points[static_cast<size_t>(b)];
            const Vec3 &fc = fabric_points[static_cast<size_t>(c)];
            const Vec3 &fd = fabric_points[static_cast<size_t>(d)];

            const Vec3 surface_dir_1 = ((sb - sa) + (sc - sd)) * 0.5;
            const Vec3 surface_dir_2 = ((sd - sa) + (sc - sb)) * 0.5;

            const Vec3 fabric_dir_1 = ((fb - fa) + (fc - fd)) * 0.5;
            const Vec3 fabric_dir_2 = ((fd - fa) + (fc - fb)) * 0.5;

            const double textile11 = dot(fabric_dir_1, fabric_dir_1);
            const double textile22 = dot(fabric_dir_2, fabric_dir_2);
            const double textile12 = dot(fabric_dir_1, fabric_dir_2);

            double surface11 = dot(surface_dir_1, surface_dir_1);
            double surface22 = dot(surface_dir_2, surface_dir_2);
            double surface12 = dot(surface_dir_1, surface_dir_2);

            if (!surfaces.empty() && point_uv && point_face_indices)
            {
                const int face_idx_a = valid_index(a, point_face_indices->size())
                                           ? (*point_face_indices)[static_cast<size_t>(a)]
                                           : -1;
                const int face_idx_b = valid_index(b, point_face_indices->size())
                                           ? (*point_face_indices)[static_cast<size_t>(b)]
                                           : -1;
                const int face_idx_c = valid_index(c, point_face_indices->size())
                                           ? (*point_face_indices)[static_cast<size_t>(c)]
                                           : -1;
                const int face_idx_d = valid_index(d, point_face_indices->size())
                                           ? (*point_face_indices)[static_cast<size_t>(d)]
                                           : -1;

                auto edge_surface_distance = [&](int i, int j)
                {
                    if (!valid_index(i, point_uv->size()) ||
                        !valid_index(j, point_uv->size()) ||
                        !valid_index(i, point_face_indices->size()) ||
                        !valid_index(j, point_face_indices->size()))
                    {
                        return norm(surface_points[static_cast<size_t>(j)] - surface_points[static_cast<size_t>(i)]);
                    }

                    const int fi = (*point_face_indices)[static_cast<size_t>(i)];
                    const int fj = (*point_face_indices)[static_cast<size_t>(j)];
                    const std::array<double, 2> uv_i = (*point_uv)[static_cast<size_t>(i)];
                    const std::array<double, 2> uv_j = (*point_uv)[static_cast<size_t>(j)];

                    if (fi >= 0 && fi == fj && valid_index(fi, surfaces.size()) && finite_uv(uv_i) && finite_uv(uv_j))
                    {
                        const double geodesic = surface_queries::approx_surface_distance_uv(
                            surfaces[static_cast<size_t>(fi)],
                            uv_i[0],
                            uv_i[1],
                            uv_j[0],
                            uv_j[1]);
                        if (std::isfinite(geodesic) && geodesic > 0.0)
                        {
                            return geodesic;
                        }
                    }

                    return norm(surface_points[static_cast<size_t>(j)] - surface_points[static_cast<size_t>(i)]);
                };

                const double lab = edge_surface_distance(a, b);
                const double lcd = edge_surface_distance(c, d);
                const double lad = edge_surface_distance(a, d);
                const double lbc = edge_surface_distance(b, c);
                const double lac = edge_surface_distance(a, c);
                const double lbd = edge_surface_distance(b, d);

                if (std::isfinite(lab) && std::isfinite(lcd) &&
                    std::isfinite(lad) && std::isfinite(lbc) &&
                    std::isfinite(lac) && std::isfinite(lbd))
                {
                    const double g11 = 0.5 * (lab * lab + lcd * lcd);
                    const double g22 = 0.5 * (lad * lad + lbc * lbc);
                    const double g12 = 0.25 * (lac * lac - lbd * lbd);

                    if (std::isfinite(g11) && std::isfinite(g22) && std::isfinite(g12))
                    {
                        surface11 = g11;
                        surface22 = g22;
                        surface12 = g12;
                    }
                }
            }

            const double textile_norm12 = std::sqrt(std::max(textile11 * textile22, 0.0));

            if (!(std::isfinite(textile11) && std::isfinite(textile22) && std::isfinite(textile12) &&
                  std::isfinite(surface11) && std::isfinite(surface22) && std::isfinite(surface12) &&
                  textile11 > kMetricDenominatorEps && textile22 > kMetricDenominatorEps &&
                  textile_norm12 > kMetricDenominatorEps))
            {
                diagnostics.cell_count_invalid += 1;
                continue;
            }

            const double residual410 = (surface11 - textile11) / textile11;
            const double residual411 = (surface22 - textile22) / textile22;
            const double residual412 = (surface12 - textile12) / textile_norm12;

            if (!(std::isfinite(residual410) && std::isfinite(residual411) && std::isfinite(residual412)))
            {
                diagnostics.cell_count_invalid += 1;
                continue;
            }

            diagnostics.cell_count_valid += 1;

            const double abs410 = std::abs(residual410);
            const double abs411 = std::abs(residual411);
            const double abs412 = std::abs(residual412);
            const double abs_combined = std::max({abs410, abs411, abs412});

            eq410_abs_values.push_back(abs410);
            eq411_abs_values.push_back(abs411);
            eq412_abs_values.push_back(abs412);
            combined_abs_values.push_back(abs_combined);

            eq410_sum_abs += abs410;
            eq411_sum_abs += abs411;
            eq412_sum_abs += abs412;

            eq410_max_abs = std::max(eq410_max_abs, abs410);
            eq411_max_abs = std::max(eq411_max_abs, abs411);
            eq412_max_abs = std::max(eq412_max_abs, abs412);

            combined_sum_sq += residual410 * residual410;
            combined_sum_sq += residual411 * residual411;
            combined_sum_sq += residual412 * residual412;
            combined_linf = std::max({combined_linf, abs410, abs411, abs412});
        }

        if (diagnostics.cell_count_valid > 0)
        {
            const double inv_valid = 1.0 / static_cast<double>(diagnostics.cell_count_valid);
            diagnostics.eq410_residual_mean = finite_or_zero(eq410_sum_abs * inv_valid);
            diagnostics.eq411_residual_mean = finite_or_zero(eq411_sum_abs * inv_valid);
            diagnostics.eq412_residual_mean = finite_or_zero(eq412_sum_abs * inv_valid);

            diagnostics.eq410_residual_max = finite_or_zero(eq410_max_abs);
            diagnostics.eq411_residual_max = finite_or_zero(eq411_max_abs);
            diagnostics.eq412_residual_max = finite_or_zero(eq412_max_abs);

            diagnostics.eq410_residual_p95 = percentile95_abs(eq410_abs_values);
            diagnostics.eq411_residual_p95 = percentile95_abs(eq411_abs_values);
            diagnostics.eq412_residual_p95 = percentile95_abs(eq412_abs_values);

            const double term_count = static_cast<double>(diagnostics.cell_count_valid) * 3.0;
            diagnostics.residual_combined_l2 = term_count > 0.0
                                                   ? finite_or_zero(std::sqrt(combined_sum_sq / term_count))
                                                   : 0.0;
            diagnostics.residual_combined_linf = finite_or_zero(combined_linf);
            diagnostics.residual_combined_p95 = percentile95_abs(combined_abs_values);
        }

        diagnostics.cell_count_invalid = std::max(0L, diagnostics.cell_count_total - diagnostics.cell_count_valid);
        if (diagnostics.cell_count_total > 0)
        {
            const double inv_total = 1.0 / static_cast<double>(diagnostics.cell_count_total);
            diagnostics.cell_valid_ratio = finite_or_zero(static_cast<double>(diagnostics.cell_count_valid) * inv_total);
            diagnostics.cell_invalid_ratio = finite_or_zero(static_cast<double>(diagnostics.cell_count_invalid) * inv_total);
        }

        return diagnostics;
    }

} // namespace fishnet_internal
