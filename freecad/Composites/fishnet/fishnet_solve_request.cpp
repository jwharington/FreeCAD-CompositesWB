#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "fishnet_solve_request.hpp"

#include <utility>

#include "fishnet_python_geometry.hpp"
#include "fishnet_python_parse.hpp"

namespace fishnet_internal
{

    SolveRequest::SolveRequest(SolveRequest &&other) noexcept
        : input_kind(other.input_kind),
          geometry_obj(other.geometry_obj),
          mesh_points(std::move(other.mesh_points)),
          mesh_faces(std::move(other.mesh_faces)),
          params_copy(other.params_copy),
          algorithm_profile(std::move(other.algorithm_profile)),
          acp_energy_mode(other.acp_energy_mode)
    {
        other.geometry_obj = nullptr;
        other.params_copy = nullptr;
        other.acp_energy_mode = false;
    }

    SolveRequest &SolveRequest::operator=(SolveRequest &&other) noexcept
    {
        if (this == &other)
        {
            return *this;
        }

        Py_XDECREF(params_copy);

        input_kind = other.input_kind;
        geometry_obj = other.geometry_obj;
        mesh_points = std::move(other.mesh_points);
        mesh_faces = std::move(other.mesh_faces);
        params_copy = other.params_copy;
        algorithm_profile = std::move(other.algorithm_profile);
        acp_energy_mode = other.acp_energy_mode;

        other.geometry_obj = nullptr;
        other.params_copy = nullptr;
        other.acp_energy_mode = false;

        return *this;
    }

    SolveRequest::~SolveRequest()
    {
        Py_XDECREF(params_copy);
    }

    PyObject *SolveRequest::release_params_copy()
    {
        PyObject *released = params_copy;
        params_copy = nullptr;
        return released;
    }

    PyObject *copy_params_dict(PyObject *params_obj)
    {
        PyObject *params_copy = (!params_obj || params_obj == Py_None)
                                    ? PyDict_New()
                                    : PyDict_Copy(params_obj);
        if (!params_copy)
        {
            return nullptr;
        }
        if (!PyDict_Check(params_copy))
        {
            Py_DECREF(params_copy);
            PyErr_SetString(PyExc_TypeError, "parameters must be a dict or None");
            return nullptr;
        }
        return params_copy;
    }

    bool parse_solve_request(PyObject *args, PyObject *kwargs, SolveRequest &request)
    {
        static const char *kwlist[] = {"mesh_points", "mesh_faces", "parameters", nullptr};

        PyObject *points_obj = nullptr;
        PyObject *faces_obj = Py_None;
        PyObject *params_obj = Py_None;

        if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OO", const_cast<char **>(kwlist), &points_obj, &faces_obj, &params_obj))
        {
            return false;
        }

        Py_XDECREF(request.params_copy);
        request.params_copy = copy_params_dict(params_obj);
        if (!request.params_copy)
        {
            return false;
        }

        request.algorithm_profile = solver_algorithm_profile_from_params(request.params_copy);
        request.acp_energy_mode = request.algorithm_profile.acp_energy_mode;

        if (geometry_like(points_obj))
        {
            request.input_kind = SolveInputKind::GeometryLike;
            request.geometry_obj = points_obj;
            request.mesh_points.clear();
            request.mesh_faces.clear();
            return true;
        }

        request.input_kind = SolveInputKind::MeshLike;
        request.geometry_obj = nullptr;

        if (!collect_mesh_points(points_obj, request.mesh_points))
        {
            return false;
        }
        if (!collect_mesh_faces(faces_obj, request.mesh_points.size(), request.mesh_faces))
        {
            return false;
        }

        return true;
    }

} // namespace fishnet_internal
