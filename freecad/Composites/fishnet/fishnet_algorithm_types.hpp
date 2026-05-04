#pragma once

#include "fishnet_primitives.hpp"

constexpr double kFallbackNormalAlignment = 0.9;
constexpr double kFaceInsideTolerance = 1.0e-6;
constexpr double kAxisPerturbationScale = 1.0e-3;
constexpr double kAxisPerturbationFloor = 1.0e-4;
constexpr double kMinimumMaxLength = 1.0;
constexpr double kFaceDivisionTargetSegments = 32.0;
constexpr double kDefaultFaceSpan = 4.0;
constexpr int kMinimumFaceDivisions = 2;
constexpr int kMaximumFaceDivisions = 64;
constexpr double kAtlasChartGap = 4.0;
constexpr double kDefaultEdgeLengthTolerance = 1.0e-6;
constexpr double kOverlapEpsilon = 1.0e-9;

enum class CurrentNodeSolverMode {
    UvNewton,
    SphereSurfaceExperimental,
};

