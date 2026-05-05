#pragma once

#include <functional>

namespace fishnet_internal
{

    struct SamplingPhaseSeams
    {
        std::function<void()> initialize;
        std::function<void()> grow;
        std::function<void()> stitch;
        std::function<void()> emit;
    };

    void run_sampling_pipeline(const SamplingPhaseSeams &seams);

} // namespace fishnet_internal
