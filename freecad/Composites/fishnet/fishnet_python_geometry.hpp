#pragma once

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <TopoDS_Face.hxx>

namespace fishnet_internal
{

    struct FaceSample;

    bool geometry_like(PyObject *obj);
    bool extract_native_face(PyObject *face_obj, TopoDS_Face &face);
    PyObject *build_face_frame_dict(const FaceSample &sample, int face_index, bool continuous, int chart_index = -1);

} // namespace fishnet_internal
