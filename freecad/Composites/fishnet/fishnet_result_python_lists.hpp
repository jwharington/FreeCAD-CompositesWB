#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <array>
#include <vector>

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal
{

    struct GeometryPythonListsInput
    {
        const std::vector<Vec3> &fabric_points;
        const std::vector<std::vector<int>> &quads;
        const std::vector<std::vector<Vec3>> &loops_pts;
        const std::vector<std::array<double, 3>> &strains;
        const std::vector<Vec3> &points;
        const std::vector<std::array<int, 3>> &triangles;
    };

    struct GeometryPythonListsOutput
    {
        PyObject *&fabric_points_list;
        PyObject *&fabric_quads_list;
        PyObject *&boundary_loops_list;
        PyObject *&strains_list;
        PyObject *&mesh_points_list;
        PyObject *&mesh_faces_list;
        PyObject *&face_frames_list;
        PyObject *&orientation_breaks_list;
        PyObject *&atlas_charts_list;
        std::vector<std::vector<int>> &mesh_face_vec;
    };

    struct MeshPythonListsInput
    {
        const std::vector<Vec3> &points;
        const std::vector<std::array<int, 3>> &faces;
        const std::vector<Vec3> &fabric_points;
        const std::vector<std::vector<int>> &fabric_quads;
        const std::vector<std::vector<Vec3>> &loops_pts;
        const std::vector<std::array<double, 3>> &strains;
        const Vec3 &origin;
        const Vec3 &normal;
        const Vec3 &x_axis;
        const Vec3 &y_axis;
    };

    struct MeshPythonListsOutput
    {
        PyObject *&fabric_points_list;
        PyObject *&fabric_quads_list;
        PyObject *&boundary_loops_list;
        PyObject *&strains_list;
        PyObject *&mesh_points_list;
        PyObject *&mesh_faces_list;
        PyObject *&face_frames_list;
        PyObject *&orientation_breaks_list;
        PyObject *&atlas_charts_list;
    };

    bool build_geometry_python_lists(
        const GeometryPythonListsInput &input,
        const GeometryPythonListsOutput &output);

    bool build_mesh_python_lists(
        const MeshPythonListsInput &input,
        const MeshPythonListsOutput &output);

} // namespace fishnet_internal
