#pragma once

#include <vector>

#include <BRepAdaptor_Surface.hxx>
#include <TopoDS_Face.hxx>

#include "fishnet_algorithm_types.hpp"
#include "fishnet_sampling_grid_module.hpp"

namespace fishnet_internal
{

    struct ExperimentalSolveStats;

    struct SurfaceRelaxationInput
    {
        const TopoDS_Face &face;
        const BRepAdaptor_Surface &surface;
        SamplingGridState &grid;
        int iterations;
        double u0;
        double u1;
        double v0;
        double v1;
        bool boundary_extend;
        std::vector<Vec3> &points;
        ExperimentalSolveStats *experimental_stats;
    };

    void run_surface_relaxation(const SurfaceRelaxationInput &input);

} // namespace fishnet_internal
