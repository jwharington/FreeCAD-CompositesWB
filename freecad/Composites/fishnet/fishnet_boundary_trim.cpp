#include "fishnet_boundary_trim.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <unordered_map>
#include <utility>
#include <vector>

#include <BRepAdaptor_Surface.hxx>
#include <gp_Pnt.hxx>

#include "fishnet_face_state_utils.hpp"
#include "fishnet_primitives.hpp"
#include "fishnet_surface_queries.hpp"

namespace fishnet_internal
{

    namespace
    {

        constexpr double kTrimStateTolerance = 1.0e-9;
        constexpr int kIntersectionBisectionSteps = 48;
        constexpr double kIntersectionEndpointSnap = 1.0e-9;
        constexpr double kMinimumTriangleArea = 1.0e-16;

        struct EdgeIntersectionKey
        {
            uint64_t edge{0};
            int face_index{-1};

            bool operator==(const EdgeIntersectionKey &other) const
            {
                return edge == other.edge && face_index == other.face_index;
            }
        };

        struct EdgeIntersectionKeyHash
        {
            std::size_t operator()(const EdgeIntersectionKey &key) const
            {
                const std::size_t h1 = std::hash<uint64_t>{}(key.edge);
                const std::size_t h2 = std::hash<int>{}(key.face_index);
                return h1 ^ (h2 + 0x9e3779b97f4a7c15ULL + (h1 << 6) + (h1 >> 2));
            }
        };

        bool finite_uv(const std::array<double, 2> &uv)
        {
            return std::isfinite(uv[0]) && std::isfinite(uv[1]);
        }

        FacePointState face_point_state_from_raw(unsigned char raw)
        {
            switch (raw)
            {
            case static_cast<unsigned char>(FacePointState::In):
                return FacePointState::In;
            case static_cast<unsigned char>(FacePointState::On):
                return FacePointState::On;
            case static_cast<unsigned char>(FacePointState::Out):
                return FacePointState::Out;
            default:
                return FacePointState::Unknown;
            }
        }

        uint64_t point_face_cache_key(int point_idx, int face_index)
        {
            const uint64_t p = static_cast<uint64_t>(static_cast<uint32_t>(point_idx));
            const uint64_t f = static_cast<uint64_t>(static_cast<uint32_t>(face_index));
            return (p << 32) | f;
        }

        Vec3 lerp(const Vec3 &a, const Vec3 &b, double t)
        {
            return a * (1.0 - t) + b * t;
        }

        double triangle_area_twice(const Vec3 &a, const Vec3 &b, const Vec3 &c)
        {
            return norm(cross(b - a, c - a));
        }

        void dedupe_polygon_indices(std::vector<int> &indices)
        {
            if (indices.empty())
            {
                return;
            }

            std::vector<int> deduped;
            deduped.reserve(indices.size());
            for (int idx : indices)
            {
                if (!deduped.empty() && deduped.back() == idx)
                {
                    continue;
                }
                deduped.push_back(idx);
            }
            if (deduped.size() > 1 && deduped.front() == deduped.back())
            {
                deduped.pop_back();
            }
            indices.swap(deduped);
        }

        class BoundaryTrimBuilder
        {
        public:
            explicit BoundaryTrimBuilder(const BoundaryTrimInput &input)
                : input_(input)
            {
                surfaces_.reserve(input_.native_faces.size());
                for (const auto &face : input_.native_faces)
                {
                    surfaces_.emplace_back(face, Standard_True);
                }
            }

            BoundaryTrimOutput run()
            {
                BoundaryTrimOutput out;
                out.mesh_points.clear();
                out.local_points.clear();
                out.fabric_points.clear();
                out.layout_points.clear();
                out.point_uv.clear();
                out.point_face_indices.clear();

                process_triangles(out);
                process_quads(out);

                out.generated_trim_vertex_count = generated_trim_vertex_count_;
                out.clipped_cell_count = clipped_cell_count_;
                return out;
            }

        private:
            int map_original_vertex(int old_idx, BoundaryTrimOutput &out)
            {
                auto it = original_to_trimmed_.find(old_idx);
                if (it != original_to_trimmed_.end())
                {
                    return it->second;
                }

                if (old_idx < 0 || old_idx >= static_cast<int>(input_.mesh_points.size()))
                {
                    return -1;
                }

                const int new_idx = static_cast<int>(out.mesh_points.size());
                out.mesh_points.push_back(input_.mesh_points[static_cast<size_t>(old_idx)]);
                out.local_points.push_back(input_.local_points[static_cast<size_t>(old_idx)]);
                out.fabric_points.push_back(input_.fabric_points[static_cast<size_t>(old_idx)]);
                if (old_idx < static_cast<int>(input_.layout_points.size()))
                {
                    out.layout_points.push_back(input_.layout_points[static_cast<size_t>(old_idx)]);
                }
                else
                {
                    out.layout_points.push_back(input_.local_points[static_cast<size_t>(old_idx)]);
                }

                if (old_idx < static_cast<int>(input_.point_uv.size()))
                {
                    out.point_uv.push_back(input_.point_uv[static_cast<size_t>(old_idx)]);
                }
                else
                {
                    out.point_uv.push_back({std::numeric_limits<double>::quiet_NaN(),
                                            std::numeric_limits<double>::quiet_NaN()});
                }

                if (old_idx < static_cast<int>(input_.point_face_indices.size()))
                {
                    out.point_face_indices.push_back(input_.point_face_indices[static_cast<size_t>(old_idx)]);
                }
                else
                {
                    out.point_face_indices.push_back(-1);
                }

                original_to_trimmed_[old_idx] = new_idx;
                return new_idx;
            }

            FacePointState classify_point_for_face(int point_idx, int face_index) const
            {
                if (point_idx < 0 ||
                    point_idx >= static_cast<int>(input_.mesh_points.size()) ||
                    face_index < 0 ||
                    face_index >= static_cast<int>(input_.native_faces.size()))
                {
                    return FacePointState::Unknown;
                }

                if (point_idx < static_cast<int>(input_.point_face_indices.size()) &&
                    point_idx < static_cast<int>(input_.point_face_state.size()) &&
                    input_.point_face_indices[static_cast<size_t>(point_idx)] == face_index)
                {
                    const FacePointState sampled_state = face_point_state_from_raw(
                        input_.point_face_state[static_cast<size_t>(point_idx)]);
                    if (sampled_state != FacePointState::Unknown)
                    {
                        return sampled_state;
                    }
                }

                const uint64_t cache_key = point_face_cache_key(point_idx, face_index);
                auto cached = point_face_state_cache_.find(cache_key);
                if (cached != point_face_state_cache_.end())
                {
                    return cached->second;
                }

                const Vec3 &p = input_.mesh_points[static_cast<size_t>(point_idx)];
                gp_Pnt gp{p.x, p.y, p.z};
                const FacePointState state = face_point_state_from_topabs(
                    surface_queries::native_face_point_state(
                        input_.native_faces[static_cast<size_t>(face_index)],
                        gp,
                        kTrimStateTolerance));
                point_face_state_cache_[cache_key] = state;
                return state;
            }

            FacePointState classify_gp_for_face(const gp_Pnt &point, int face_index) const
            {
                return face_point_state_from_topabs(
                    surface_queries::native_face_point_state(
                        input_.native_faces[static_cast<size_t>(face_index)],
                        point,
                        kTrimStateTolerance));
            }

            bool vertex_inside_for_face(int point_idx, int face_index) const
            {
                return face_point_state_is_inside(classify_point_for_face(point_idx, face_index));
            }

            int resolve_cell_face_index(const std::vector<int> &cell) const
            {
                for (int idx : cell)
                {
                    if (idx >= 0 && idx < static_cast<int>(input_.point_face_indices.size()))
                    {
                        const int face_index = input_.point_face_indices[static_cast<size_t>(idx)];
                        if (face_index >= 0 && face_index < static_cast<int>(input_.native_faces.size()))
                        {
                            return face_index;
                        }
                    }
                }
                return -1;
            }

            int create_or_get_intersection_vertex(
                int a,
                int b,
                int face_index,
                BoundaryTrimOutput &out)
            {
                if (a == b)
                {
                    return map_original_vertex(a, out);
                }

                const EdgeIntersectionKey key{edge_key(a, b), face_index};
                auto cached = edge_intersection_cache_.find(key);
                if (cached != edge_intersection_cache_.end())
                {
                    return cached->second;
                }

                const FacePointState state_a = classify_point_for_face(a, face_index);
                const FacePointState state_b = classify_point_for_face(b, face_index);
                const bool inside_a = face_point_state_is_inside(state_a);
                const bool inside_b = face_point_state_is_inside(state_b);

                if (state_a == FacePointState::On)
                {
                    const int idx = map_original_vertex(a, out);
                    edge_intersection_cache_[key] = idx;
                    return idx;
                }
                if (state_b == FacePointState::On)
                {
                    const int idx = map_original_vertex(b, out);
                    edge_intersection_cache_[key] = idx;
                    return idx;
                }
                if (inside_a == inside_b)
                {
                    return -1;
                }

                const std::array<double, 2> uv_a = (a >= 0 && a < static_cast<int>(input_.point_uv.size()))
                                                       ? input_.point_uv[static_cast<size_t>(a)]
                                                       : std::array<double, 2>{std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::quiet_NaN()};
                const std::array<double, 2> uv_b = (b >= 0 && b < static_cast<int>(input_.point_uv.size()))
                                                       ? input_.point_uv[static_cast<size_t>(b)]
                                                       : std::array<double, 2>{std::numeric_limits<double>::quiet_NaN(), std::numeric_limits<double>::quiet_NaN()};

                const bool uv_mode = finite_uv(uv_a) && finite_uv(uv_b);
                const BRepAdaptor_Surface &surface = surfaces_[static_cast<size_t>(face_index)];

                double t_inside = inside_a ? 0.0 : 1.0;
                double t_outside = inside_a ? 1.0 : 0.0;

                auto eval_point = [&](double t)
                {
                    if (uv_mode)
                    {
                        const double u = uv_a[0] + t * (uv_b[0] - uv_a[0]);
                        const double v = uv_a[1] + t * (uv_b[1] - uv_a[1]);
                        return surface.Value(u, v);
                    }
                    const Vec3 p = lerp(
                        input_.mesh_points[static_cast<size_t>(a)],
                        input_.mesh_points[static_cast<size_t>(b)],
                        t);
                    return gp_Pnt(p.x, p.y, p.z);
                };

                for (int iter = 0; iter < kIntersectionBisectionSteps; ++iter)
                {
                    const double t_mid = 0.5 * (t_inside + t_outside);
                    const gp_Pnt p_mid = eval_point(t_mid);
                    const bool inside_mid = face_point_state_is_inside(classify_gp_for_face(p_mid, face_index));
                    if (inside_mid)
                    {
                        t_inside = t_mid;
                    }
                    else
                    {
                        t_outside = t_mid;
                    }
                }

                double t_intersection = std::clamp(t_inside, 0.0, 1.0);
                if (t_intersection <= kIntersectionEndpointSnap)
                {
                    const int idx = map_original_vertex(a, out);
                    edge_intersection_cache_[key] = idx;
                    return idx;
                }
                if (t_intersection >= 1.0 - kIntersectionEndpointSnap)
                {
                    const int idx = map_original_vertex(b, out);
                    edge_intersection_cache_[key] = idx;
                    return idx;
                }

                const int new_idx = static_cast<int>(out.mesh_points.size());
                const gp_Pnt p = eval_point(t_intersection);
                out.mesh_points.push_back({p.X(), p.Y(), p.Z()});
                out.local_points.push_back(lerp(
                    input_.local_points[static_cast<size_t>(a)],
                    input_.local_points[static_cast<size_t>(b)],
                    t_intersection));
                out.fabric_points.push_back(lerp(
                    input_.fabric_points[static_cast<size_t>(a)],
                    input_.fabric_points[static_cast<size_t>(b)],
                    t_intersection));

                const Vec3 layout_a = (a >= 0 && a < static_cast<int>(input_.layout_points.size()))
                                          ? input_.layout_points[static_cast<size_t>(a)]
                                          : input_.local_points[static_cast<size_t>(a)];
                const Vec3 layout_b = (b >= 0 && b < static_cast<int>(input_.layout_points.size()))
                                          ? input_.layout_points[static_cast<size_t>(b)]
                                          : input_.local_points[static_cast<size_t>(b)];
                out.layout_points.push_back(lerp(layout_a, layout_b, t_intersection));

                if (uv_mode)
                {
                    const double u = uv_a[0] + t_intersection * (uv_b[0] - uv_a[0]);
                    const double v = uv_a[1] + t_intersection * (uv_b[1] - uv_a[1]);
                    out.point_uv.push_back({u, v});
                }
                else
                {
                    out.point_uv.push_back({std::numeric_limits<double>::quiet_NaN(),
                                            std::numeric_limits<double>::quiet_NaN()});
                }
                out.point_face_indices.push_back(face_index);

                edge_intersection_cache_[key] = new_idx;
                generated_trim_vertex_count_ += 1;
                return new_idx;
            }

            std::vector<int> clip_cell_to_face(
                const std::vector<int> &cell,
                int face_index,
                bool &mixed_cell,
                BoundaryTrimOutput &out)
            {
                mixed_cell = false;
                if (cell.size() < 3)
                {
                    return {};
                }

                int inside_count = 0;
                for (int idx : cell)
                {
                    if (vertex_inside_for_face(idx, face_index))
                    {
                        inside_count += 1;
                    }
                }
                if (inside_count <= 0)
                {
                    return {};
                }

                mixed_cell = inside_count < static_cast<int>(cell.size());

                std::vector<int> clipped;
                clipped.reserve(cell.size() + 2);

                int prev = cell.back();
                bool prev_inside = vertex_inside_for_face(prev, face_index);
                for (int curr : cell)
                {
                    bool curr_inside = vertex_inside_for_face(curr, face_index);
                    if (prev_inside && curr_inside)
                    {
                        clipped.push_back(map_original_vertex(curr, out));
                    }
                    else if (prev_inside && !curr_inside)
                    {
                        const int isect = create_or_get_intersection_vertex(prev, curr, face_index, out);
                        if (isect >= 0)
                        {
                            clipped.push_back(isect);
                        }
                    }
                    else if (!prev_inside && curr_inside)
                    {
                        const int isect = create_or_get_intersection_vertex(prev, curr, face_index, out);
                        if (isect >= 0)
                        {
                            clipped.push_back(isect);
                        }
                        clipped.push_back(map_original_vertex(curr, out));
                    }

                    prev = curr;
                    prev_inside = curr_inside;
                }

                dedupe_polygon_indices(clipped);
                if (clipped.size() < 3)
                {
                    return {};
                }
                return clipped;
            }

            void append_polygon_as_triangles(
                const std::vector<int> &polygon,
                int face_index,
                BoundaryTrimOutput &out)
            {
                if (polygon.size() < 3)
                {
                    return;
                }
                const int anchor = polygon[0];
                for (size_t i = 1; i + 1 < polygon.size(); ++i)
                {
                    const int b = polygon[i];
                    const int c = polygon[i + 1];
                    if (anchor < 0 || b < 0 || c < 0 ||
                        anchor >= static_cast<int>(out.mesh_points.size()) ||
                        b >= static_cast<int>(out.mesh_points.size()) ||
                        c >= static_cast<int>(out.mesh_points.size()))
                    {
                        continue;
                    }
                    const Vec3 &pa = out.mesh_points[static_cast<size_t>(anchor)];
                    const Vec3 &pb = out.mesh_points[static_cast<size_t>(b)];
                    const Vec3 &pc = out.mesh_points[static_cast<size_t>(c)];
                    if (triangle_area_twice(pa, pb, pc) <= kMinimumTriangleArea)
                    {
                        continue;
                    }

                    const gp_Pnt centroid(
                        (pa.x + pb.x + pc.x) / 3.0,
                        (pa.y + pb.y + pc.y) / 3.0,
                        (pa.z + pb.z + pc.z) / 3.0);
                    if (!face_point_state_is_inside(classify_gp_for_face(centroid, face_index)))
                    {
                        continue;
                    }

                    out.triangles.push_back({anchor, b, c});
                }
            }

            void process_triangles(BoundaryTrimOutput &out)
            {
                out.triangles.clear();
                out.triangles.reserve(input_.triangles.size());

                for (const auto &tri : input_.triangles)
                {
                    const std::vector<int> cell = {tri[0], tri[1], tri[2]};
                    const int face_index = resolve_cell_face_index(cell);
                    if (face_index < 0)
                    {
                        continue;
                    }

                    bool mixed_cell = false;
                    std::vector<int> clipped = clip_cell_to_face(cell, face_index, mixed_cell, out);
                    if (mixed_cell)
                    {
                        clipped_cell_count_ += 1;
                    }
                    append_polygon_as_triangles(clipped, face_index, out);
                }
            }

            void process_quads(BoundaryTrimOutput &out)
            {
                out.quads.clear();
                out.quads.reserve(input_.quads.size());

                for (const auto &quad : input_.quads)
                {
                    if (quad.size() < 4)
                    {
                        continue;
                    }
                    const std::vector<int> cell = {quad[0], quad[1], quad[2], quad[3]};
                    const int face_index = resolve_cell_face_index(cell);
                    if (face_index < 0)
                    {
                        continue;
                    }

                    bool mixed_cell = false;
                    std::vector<int> clipped = clip_cell_to_face(cell, face_index, mixed_cell, out);
                    if (clipped.size() != 4)
                    {
                        continue;
                    }

                    const Vec3 &pa = out.mesh_points[static_cast<size_t>(clipped[0])];
                    const Vec3 &pb = out.mesh_points[static_cast<size_t>(clipped[1])];
                    const Vec3 &pc = out.mesh_points[static_cast<size_t>(clipped[2])];
                    const Vec3 &pd = out.mesh_points[static_cast<size_t>(clipped[3])];
                    const double area = triangle_area_twice(pa, pb, pc) + triangle_area_twice(pa, pc, pd);
                    if (area <= 2.0 * kMinimumTriangleArea)
                    {
                        continue;
                    }

                    const gp_Pnt centroid(
                        0.25 * (pa.x + pb.x + pc.x + pd.x),
                        0.25 * (pa.y + pb.y + pc.y + pd.y),
                        0.25 * (pa.z + pb.z + pc.z + pd.z));
                    if (!face_point_state_is_inside(classify_gp_for_face(centroid, face_index)))
                    {
                        continue;
                    }

                    if (mixed_cell)
                    {
                        clipped_cell_count_ += 1;
                    }
                    out.quads.push_back(std::move(clipped));
                }
            }

            const BoundaryTrimInput &input_;
            std::vector<BRepAdaptor_Surface> surfaces_;
            std::unordered_map<int, int> original_to_trimmed_;
            std::unordered_map<EdgeIntersectionKey, int, EdgeIntersectionKeyHash> edge_intersection_cache_;
            mutable std::unordered_map<uint64_t, FacePointState> point_face_state_cache_;
            long clipped_cell_count_{0};
            long generated_trim_vertex_count_{0};
        };

    } // namespace

    BoundaryTrimOutput trim_boundary_cells(const BoundaryTrimInput &input)
    {
        BoundaryTrimBuilder builder(input);
        return builder.run();
    }

} // namespace fishnet_internal
