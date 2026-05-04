#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <Mod/Part/App/TopoShapePy.h>

#include "fishnet_algorithm_sections.hpp"
#include "fishnet_python_geometry.hpp"
#include "fishnet_python_util.hpp"
#include "fishnet_surface_queries.hpp"

namespace fishnet_internal
{

    bool geometry_like(PyObject *obj)
    {
        if (!obj)
        {
            return false;
        }
        if (PyObject_TypeCheck(obj, &(Part::TopoShapePy::Type)) > 0)
        {
            return true;
        }
        if (PyObject_HasAttrString(obj, "Faces") > 0)
        {
            return true;
        }
        if (PyObject_HasAttrString(obj, "ParameterRange") > 0)
        {
            return true;
        }
        PyObject *surface = PyObject_GetAttrString(obj, "Surface");
        if (!surface)
        {
            PyErr_Clear();
            return false;
        }
        bool result = PyObject_HasAttrString(surface, "valueAt") > 0 || PyObject_HasAttrString(surface, "normalAt") > 0;
        Py_DECREF(surface);
        return result;
    }

    bool extract_native_face(PyObject *face_obj, TopoDS_Face &face)
    {
        return surface_queries::extract_native_face(face_obj, face);
    }

    PyObject *build_face_frame_dict(const FaceSample &sample, int face_index, bool continuous, int chart_index)
    {
        PyObject *frame = PyDict_New();
        if (!frame)
        {
            return nullptr;
        }

        PyObject *face_index_obj = PyLong_FromLong(face_index);
        PyObject *origin_obj = build_vec3_tuple(sample.origin);
        PyObject *normal_obj = build_vec3_tuple(sample.normal);
        PyObject *x_axis_obj = build_vec3_tuple(sample.x_axis);
        PyObject *y_axis_obj = build_vec3_tuple(sample.y_axis);
        if (!face_index_obj || !origin_obj || !normal_obj || !x_axis_obj || !y_axis_obj)
        {
            Py_XDECREF(face_index_obj);
            Py_XDECREF(origin_obj);
            Py_XDECREF(normal_obj);
            Py_XDECREF(x_axis_obj);
            Py_XDECREF(y_axis_obj);
            Py_DECREF(frame);
            return nullptr;
        }

        PyDict_SetItemString(frame, "face_index", face_index_obj);
        PyDict_SetItemString(frame, "origin", origin_obj);
        PyDict_SetItemString(frame, "normal", normal_obj);
        PyDict_SetItemString(frame, "x_axis", x_axis_obj);
        PyDict_SetItemString(frame, "y_axis", y_axis_obj);
        PyDict_SetItemString(frame, "continuous", continuous ? Py_True : Py_False);
        if (chart_index >= 0)
        {
            PyObject *chart_index_obj = PyLong_FromLong(chart_index);
            if (chart_index_obj)
            {
                PyDict_SetItemString(frame, "chart_index", chart_index_obj);
                Py_DECREF(chart_index_obj);
            }
        }

        Py_DECREF(face_index_obj);
        Py_DECREF(origin_obj);
        Py_DECREF(normal_obj);
        Py_DECREF(x_axis_obj);
        Py_DECREF(y_axis_obj);
        return frame;
    }

} // namespace fishnet_internal
