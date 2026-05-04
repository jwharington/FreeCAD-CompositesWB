#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "fishnet_python_input.hpp"

#include "fishnet_surface_queries.hpp"

namespace fishnet_internal {

void release_py_faces(std::vector<PyObject *> &faces)
{
    for (PyObject *face : faces)
    {
        Py_DECREF(face);
    }
    faces.clear();
}

bool collect_geometry_faces(PyObject *geometry_obj, std::vector<PyObject *> &faces)
{
    faces.clear();
    PyObject *faces_attr = PyObject_GetAttrString(geometry_obj, "Faces");
    if (faces_attr)
    {
        PyObject *faces_seq = PySequence_Fast(faces_attr, "Faces must be a sequence");
        Py_DECREF(faces_attr);
        if (faces_seq)
        {
            faces.reserve(static_cast<size_t>(PySequence_Fast_GET_SIZE(faces_seq)));
            for (Py_ssize_t i = 0; i < PySequence_Fast_GET_SIZE(faces_seq); ++i)
            {
                PyObject *item = PySequence_Fast_GET_ITEM(faces_seq, i);
                Py_INCREF(item);
                faces.push_back(item);
            }
            Py_DECREF(faces_seq);
        }
        else
        {
            PyErr_Clear();
        }
    }
    else
    {
        PyErr_Clear();
    }

    if (faces.empty() && PyObject_HasAttrString(geometry_obj, "ParameterRange") > 0)
    {
        Py_INCREF(geometry_obj);
        faces.push_back(geometry_obj);
    }
    return !faces.empty();
}

bool extract_native_faces_from_py(
    const std::vector<PyObject *> &faces,
    std::vector<TopoDS_Face> &native_faces)
{
    native_faces.clear();
    native_faces.reserve(faces.size());
    for (PyObject *face_obj : faces)
    {
        TopoDS_Face native_face;
        if (!surface_queries::extract_native_face(face_obj, native_face))
        {
            return false;
        }
        native_faces.push_back(native_face);
    }
    return true;
}

} // namespace fishnet_internal
