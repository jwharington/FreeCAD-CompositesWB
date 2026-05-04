#pragma once
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <vector>

#include <TopoDS_Face.hxx>

namespace fishnet_internal {

void release_py_faces(std::vector<PyObject *> &faces);
bool collect_geometry_faces(PyObject *geometry_obj, std::vector<PyObject *> &faces);
bool extract_native_faces_from_py(const std::vector<PyObject *> &faces, std::vector<TopoDS_Face> &native_faces);

} // namespace fishnet_internal
