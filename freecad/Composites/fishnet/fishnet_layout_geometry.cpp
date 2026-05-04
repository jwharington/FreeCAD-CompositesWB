#include <algorithm>
#include <array>
#include <cmath>
#include <vector>

#include "fishnet_layout_geometry.hpp"

#include "fishnet_boundary_atlas.hpp"
#include "fishnet_surface_queries.hpp"

namespace fishnet_internal
{
    Vec3 centroid(const std::vector<Vec3> &points)
    {
        if (points.empty())
        {
            return {0.0, 0.0, 0.0};
        }

        Vec3 c{};
        for (const auto &p : points)
        {
            c = c + p;
        }
        double inv = 1.0 / static_cast<double>(points.size());
        return c * inv;
    }

    void build_basis(
        const std::vector<Vec3> &points,
        const std::vector<std::array<int, 3>> &faces,
        Vec3 &normal,
        Vec3 &x_axis,
        Vec3 &y_axis)
    {
        Vec3 accum{};
        for (const auto &face : faces)
        {
            const Vec3 &a = points[static_cast<size_t>(face[0])];
            const Vec3 &b = points[static_cast<size_t>(face[1])];
            const Vec3 &c = points[static_cast<size_t>(face[2])];
            accum = accum + cross(b - a, c - a);
        }
        normal = normalize(accum);
        if (norm(normal) <= kVectorZeroEpsilon)
        {
            normal = {0.0, 0.0, 1.0};
        }

        Vec3 ref = std::fabs(normal.z) < kFallbackNormalAlignment ? Vec3{0.0, 0.0, 1.0} : Vec3{1.0, 0.0, 0.0};
        x_axis = normalize(cross(ref, normal));
        if (norm(x_axis) <= kVectorZeroEpsilon)
        {
            ref = {0.0, 1.0, 0.0};
            x_axis = normalize(cross(ref, normal));
        }
        if (norm(x_axis) <= kVectorZeroEpsilon)
        {
            x_axis = {1.0, 0.0, 0.0};
        }
        y_axis = normalize(cross(normal, x_axis));
        if (norm(y_axis) <= kVectorZeroEpsilon)
        {
            y_axis = {0.0, 1.0, 0.0};
        }
    }

    Vec3 project_point(
        const Vec3 &point,
        const Vec3 &origin,
        const Vec3 &x_axis,
        const Vec3 &y_axis,
        const Vec3 &normal)
    {
        Vec3 rel = point - origin;
        return {
            dot(rel, x_axis),
            dot(rel, y_axis),
            dot(rel, normal),
        };
    }

    std::vector<std::vector<int>> boundary_loops(
        const std::vector<std::array<int, 3>> &faces)
    {
        return boundary_atlas::boundary_loops(faces);
    }

    std::vector<std::array<double, 3>> face_strains(
        const std::vector<std::array<int, 3>> &faces,
        const std::vector<Vec3> &local_points,
        const Vec3 &normal)
    {
        std::vector<std::array<double, 3>> result;
        result.reserve(faces.size());
        for (const auto &face : faces)
        {
            const Vec3 &p0 = local_points[static_cast<size_t>(face[0])];
            const Vec3 &p1 = local_points[static_cast<size_t>(face[1])];
            const Vec3 &p2 = local_points[static_cast<size_t>(face[2])];
            double w0 = p0.z;
            double w1 = p1.z;
            double w2 = p2.z;
            double spread = std::max({w0, w1, w2}) - std::min({w0, w1, w2});
            double avg_abs = (std::fabs(w0) + std::fabs(w1) + std::fabs(w2)) / 3.0;
            Vec3 face_normal = normalize(cross(p1 - p0, p2 - p0));
            double d = std::max(-1.0, std::min(1.0, dot(face_normal, normal)));
            double angle = std::acos(d);
            result.push_back({avg_abs, angle, spread});
        }
        return result;
    }

    std::vector<int> order_quad_indices(
        const std::vector<int> &indices,
        const std::vector<Vec3> &points)
    {
        Vec3 center{0.0, 0.0, 0.0};
        for (int idx : indices)
        {
            center = center + points[static_cast<size_t>(idx)];
        }
        center = center * (1.0 / static_cast<double>(indices.size()));

        Vec3 normal{0.0, 0.0, 0.0};
        if (indices.size() >= 3)
        {
            const Vec3 &p0 = points[static_cast<size_t>(indices[0])];
            const Vec3 &p1 = points[static_cast<size_t>(indices[1])];
            const Vec3 &p2 = points[static_cast<size_t>(indices[2])];
            normal = normal + cross(p1 - p0, p2 - p0);
        }
        if (norm(normal) <= kVectorZeroEpsilon && indices.size() >= 4)
        {
            const Vec3 &p0 = points[static_cast<size_t>(indices[0])];
            const Vec3 &p2 = points[static_cast<size_t>(indices[2])];
            const Vec3 &p3 = points[static_cast<size_t>(indices[3])];
            normal = normal + cross(p2 - p0, p3 - p0);
        }
        normal = normalize(normal);
        if (norm(normal) <= kVectorZeroEpsilon)
        {
            normal = {0.0, 0.0, 1.0};
        }

        Vec3 ref = points[static_cast<size_t>(indices[0])] - center;
        if (norm(ref) <= kVectorZeroEpsilon && indices.size() > 1)
        {
            ref = points[static_cast<size_t>(indices[1])] - center;
        }
        if (norm(ref) <= kVectorZeroEpsilon)
        {
            ref = {1.0, 0.0, 0.0};
        }
        ref = normalize(ref);
        Vec3 y_axis = normalize(cross(normal, ref));
        if (norm(y_axis) <= kVectorZeroEpsilon)
        {
            y_axis = {0.0, 1.0, 0.0};
        }

        std::vector<std::pair<double, int>> angles;
        angles.reserve(indices.size());
        for (int idx : indices)
        {
            Vec3 rel = points[static_cast<size_t>(idx)] - center;
            double x = dot(rel, ref);
            double y = dot(rel, y_axis);
            angles.emplace_back(std::atan2(y, x), idx);
        }
        std::sort(angles.begin(), angles.end(), [](const auto &a, const auto &b)
                  { return a.first < b.first; });

        std::vector<int> ordered;
        ordered.reserve(indices.size());
        for (const auto &entry : angles)
        {
            ordered.push_back(entry.second);
        }
        return ordered;
    }

    std::vector<std::vector<int>> extract_quads(
        const std::vector<std::array<int, 3>> &faces,
        const std::vector<Vec3> &points)
    {
        std::vector<std::vector<int>> quads;
        for (size_t i = 0; i + 1 < faces.size(); i += 2)
        {
            std::vector<int> face_a{faces[i][0], faces[i][1], faces[i][2]};
            std::vector<int> face_b{faces[i + 1][0], faces[i + 1][1], faces[i + 1][2]};
            std::vector<int> shared;
            for (int a : face_a)
            {
                if (std::find(face_b.begin(), face_b.end(), a) != face_b.end())
                {
                    shared.push_back(a);
                }
            }
            if (shared.size() == 2)
            {
                std::vector<int> union_indices = face_a;
                union_indices.insert(union_indices.end(), face_b.begin(), face_b.end());
                std::sort(union_indices.begin(), union_indices.end());
                union_indices.erase(std::unique(union_indices.begin(), union_indices.end()), union_indices.end());
                if (union_indices.size() == 4)
                {
                    quads.push_back(order_quad_indices(union_indices, points));
                }
            }
        }
        return quads;
    }

    std::vector<Vec3> loop_to_points(
        const std::vector<int> &loop,
        const std::vector<Vec3> &fabric_points)
    {
        return boundary_atlas::loop_to_points(loop, fabric_points);
    }

    std::array<std::array<double, 2>, 4> quad_poly2d(const std::vector<Vec3> &points, const std::vector<int> &quad)
    {
        return boundary_atlas::quad_poly2d(points, quad);
    }

    std::vector<AtlasChartBuild> split_into_non_overlapping_charts(
        const std::vector<Vec3> &fabric_points,
        const std::vector<std::vector<int>> &quads,
        int &overlap_rejections)
    {
        return boundary_atlas::split_into_non_overlapping_charts(fabric_points, quads, overlap_rejections);
    }

    double point_set_span(const std::vector<Vec3> &pts)
    {
        if (pts.empty())
        {
            return 0.0;
        }
        double min_x = pts[0].x;
        double max_x = pts[0].x;
        double min_y = pts[0].y;
        double max_y = pts[0].y;
        double min_z = pts[0].z;
        double max_z = pts[0].z;
        for (const auto &p : pts)
        {
            min_x = std::min(min_x, p.x);
            max_x = std::max(max_x, p.x);
            min_y = std::min(min_y, p.y);
            max_y = std::max(max_y, p.y);
            min_z = std::min(min_z, p.z);
            max_z = std::max(max_z, p.z);
        }
        double dx = max_x - min_x;
        double dy = max_y - min_y;
        double dz = max_z - min_z;
        return std::sqrt(dx * dx + dy * dy + dz * dz);
    }

    void transfer_layout_between_faces(const FaceSample &prev, FaceSample &curr)
    {
        boundary_atlas::transfer_layout_between_faces(prev, curr);
    }

    bool ensure_part_module_loaded()
    {
        return surface_queries::ensure_part_module_loaded();
    }


} // namespace fishnet_internal
