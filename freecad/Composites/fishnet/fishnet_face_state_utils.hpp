#pragma once

#include <TopAbs_State.hxx>

#include "fishnet_algorithm_types.hpp"

namespace fishnet_internal
{

    inline FacePointState face_point_state_from_topabs(TopAbs_State state)
    {
        switch (state)
        {
        case TopAbs_IN:
            return FacePointState::In;
        case TopAbs_ON:
            return FacePointState::On;
        case TopAbs_OUT:
            return FacePointState::Out;
        default:
            return FacePointState::Unknown;
        }
    }

} // namespace fishnet_internal
