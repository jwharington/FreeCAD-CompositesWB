#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "fishnet_result_python_lists.hpp"

#include "fishnet_python_util.hpp"

namespace fishnet_internal
{

    static std::vector<std::vector<int>> triangles_to_mesh_face_vec(
        const std::vector<std::array<int, 3>> &triangles)
    {
        std::vector<std::vector<int>> mesh_face_vec;
        mesh_face_vec.reserve(triangles.size());
        for (const auto &face : triangles)
        {
            mesh_face_vec.push_back({face[0], face[1], face[2]});
        }
        return mesh_face_vec;
    }

    static bool append_origin_face_frame(
        PyObject *face_frames_list,
        const Vec3 &origin,
        const Vec3 &normal,
        const Vec3 &x_axis,
        const Vec3 &y_axis)
    {
        if (!face_frames_list)
        {
            return false;
        }

        PyObject *frame = PyDict_New();
        if (!frame)
        {
            Py_DECREF(face_frames_list);
            return false;
        }
        PyObject *face_index = PyLong_FromLong(0);
        PyObject *origin_obj = build_vec3_tuple(origin);
        PyObject *normal_obj = build_vec3_tuple(normal);
        PyObject *x_axis_obj = build_vec3_tuple(x_axis);
        PyObject *y_axis_obj = build_vec3_tuple(y_axis);
        if (face_index && origin_obj && normal_obj && x_axis_obj && y_axis_obj)
        {
            PyDict_SetItemString(frame, "face_index", face_index);
            PyDict_SetItemString(frame, "origin", origin_obj);
            PyDict_SetItemString(frame, "normal", normal_obj);
            PyDict_SetItemString(frame, "x_axis", x_axis_obj);
            PyDict_SetItemString(frame, "y_axis", y_axis_obj);
            PyDict_SetItemString(frame, "continuous", Py_True);
            PyList_SET_ITEM(face_frames_list, 0, frame);
        }
        else
        {
            Py_DECREF(frame);
            Py_DECREF(face_frames_list);
            face_frames_list = nullptr;
        }
        Py_XDECREF(face_index);
        Py_XDECREF(origin_obj);
        Py_XDECREF(normal_obj);
        Py_XDECREF(x_axis_obj);
        Py_XDECREF(y_axis_obj);
        return face_frames_list != nullptr;
    }

    bool build_geometry_python_lists(
        const GeometryPythonListsInput &input,
        const GeometryPythonListsOutput &output)
    {
        output.fabric_points_list = build_vec3_list(input.fabric_points);
        output.fabric_quads_list = build_quad_list(input.quads);
        output.boundary_loops_list = build_loop_list(input.loops_pts);
        output.strains_list = build_strain_list(input.strains);
        output.mesh_points_list = build_vec3_list(input.points);
        output.mesh_face_vec = triangles_to_mesh_face_vec(input.triangles);
        output.mesh_faces_list = build_quad_list(output.mesh_face_vec);

        if (!output.fabric_points_list || !output.fabric_quads_list || !output.boundary_loops_list ||
            !output.strains_list || !output.mesh_points_list || !output.mesh_faces_list)
        {
            return false;
        }

        output.face_frames_list = PyList_New(0);
        output.orientation_breaks_list = PyList_New(0);
        output.atlas_charts_list = PyList_New(0);
        if (!output.face_frames_list || !output.orientation_breaks_list || !output.atlas_charts_list)
        {
            return false;
        }

        return true;
    }

    bool build_mesh_python_lists(
        const MeshPythonListsInput &input,
        const MeshPythonListsOutput &output)
    {
        output.fabric_points_list = build_vec3_list(input.fabric_points);
        output.fabric_quads_list = build_quad_list(input.fabric_quads);
        output.boundary_loops_list = build_loop_list(input.loops_pts);
        output.strains_list = build_strain_list(input.strains);
        output.mesh_points_list = build_vec3_list(input.points);

        std::vector<std::vector<int>> mesh_face_vec = triangles_to_mesh_face_vec(input.faces);
        output.mesh_faces_list = build_quad_list(mesh_face_vec);
        output.face_frames_list = PyList_New(1);
        output.orientation_breaks_list = PyList_New(0);
        output.atlas_charts_list = PyList_New(0);

        if (output.face_frames_list &&
            !append_origin_face_frame(output.face_frames_list, input.origin, input.normal, input.x_axis, input.y_axis))
        {
            output.face_frames_list = nullptr;
        }

        if (!output.fabric_points_list || !output.fabric_quads_list || !output.boundary_loops_list || !output.strains_list ||
            !output.mesh_points_list || !output.mesh_faces_list || !output.face_frames_list ||
            !output.orientation_breaks_list || !output.atlas_charts_list)
        {
            return false;
        }

        return true;
    }

} // namespace fishnet_internal
