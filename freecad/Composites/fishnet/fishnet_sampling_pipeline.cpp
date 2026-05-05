#include "fishnet_sampling_pipeline.hpp"

namespace fishnet_internal
{

    void run_sampling_pipeline(const SamplingPhaseSeams &seams)
    {
        if (seams.initialize)
        {
            seams.initialize();
        }
        if (seams.grow)
        {
            seams.grow();
        }
        if (seams.stitch)
        {
            seams.stitch();
        }
        if (seams.emit)
        {
            seams.emit();
        }
    }

} // namespace fishnet_internal
