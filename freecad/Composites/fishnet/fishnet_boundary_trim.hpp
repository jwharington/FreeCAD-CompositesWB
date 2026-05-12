#pragma once

#include <array>
#include <vector>

#include <TopoDS_Face.hxx>

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal
{

    struct BoundaryTrimInput
    {
        const std::vector<TopoDS_Face> &native_faces;
        const std::vector<Vec3> &mesh_points;
        const std::vector<Vec3> &local_points;
        const std::vector<Vec3> &fabric_points;
        const std::vector<Vec3> &layout_points;
        const std::vector<std::array<int, 3>> &triangles;
        const std::vector<std::vector<int>> &quads;
        const std::vector<std::array<double, 2>> &point_uv;
        const std::vector<unsigned char> &point_face_state;
        const std::vector<int> &point_face_indices;
    };

    struct BoundaryTrimOutput
    {
        std::vector<Vec3> mesh_points;
        std::vector<Vec3> local_points;
        std::vector<Vec3> fabric_points;
        std::vector<Vec3> layout_points;
        std::vector<std::array<double, 2>> point_uv;
        std::vector<int> point_face_indices;
        std::vector<std::array<int, 3>> triangles;
        std::vector<std::vector<int>> quads;
        long clipped_cell_count{0};
        long generated_trim_vertex_count{0};
    };

    BoundaryTrimOutput trim_boundary_cells(const BoundaryTrimInput &input);

} // namespace fishnet_internal
