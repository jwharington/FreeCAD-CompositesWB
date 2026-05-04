#pragma once

#include <functional>
#include <vector>

#include <BRepAdaptor_Surface.hxx>
#include <TopoDS_Face.hxx>

#include "fishnet_sampling_api.hpp"
#include "fishnet_sampling_grid_module.hpp"

namespace fishnet_internal
{

    struct NodeUpdateContextInput
    {
        const TopoDS_Face &face;
        const BRepAdaptor_Surface &surface;
        double max_adjacent_normal_angle;
        double max_local_fold_ratio;
        double max_shear_angle;
        SamplingGridState &grid;
        double u0;
        double u1;
        double v0;
        double v1;
        std::vector<Vec3> &points;
        std::function<int(int, int)> ensure_grid_node;
        ExperimentalSolveStats *experimental_stats;
    };

    class NodeUpdateContext
    {
    public:
        explicit NodeUpdateContext(const NodeUpdateContextInput &input);

        bool attempt(int i, int j, int ib, int jb, int ic, int jc, double rb, double rc);

        bool operator()(int i, int j, int ib, int jb, int ic, int jc, double rb, double rc)
        {
            return attempt(i, j, ib, jb, ic, jc, rb, rc);
        }

    private:
        const TopoDS_Face &face_;
        const BRepAdaptor_Surface &surface_;
        double max_adjacent_normal_angle_;
        double max_local_fold_ratio_;
        double max_shear_angle_;
        SamplingGridState &grid_;
        double u0_;
        double u1_;
        double v0_;
        double v1_;
        std::vector<Vec3> &points_;
        std::function<int(int, int)> ensure_grid_node_;
        ExperimentalSolveStats *experimental_stats_;
    };

} // namespace fishnet_internal
