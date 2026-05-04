#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>

struct Vec3 {
    double x{0.0};
    double y{0.0};
    double z{0.0};
};

constexpr double kVectorZeroEpsilon = 1.0e-12;
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

static inline Vec3 operator+(const Vec3 &a, const Vec3 &b) {
    return {a.x + b.x, a.y + b.y, a.z + b.z};
}

static inline Vec3 operator-(const Vec3 &a, const Vec3 &b) {
    return {a.x - b.x, a.y - b.y, a.z - b.z};
}

static inline Vec3 operator*(const Vec3 &a, double s) {
    return {a.x * s, a.y * s, a.z * s};
}

static inline double dot(const Vec3 &a, const Vec3 &b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

static inline Vec3 cross(const Vec3 &a, const Vec3 &b) {
    return {
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    };
}

static inline double norm(const Vec3 &a) {
    return std::sqrt(dot(a, a));
}

static inline Vec3 normalize(const Vec3 &a) {
    double n = norm(a);
    if (n <= kVectorZeroEpsilon) {
        return {0.0, 0.0, 0.0};
    }
    return {a.x / n, a.y / n, a.z / n};
}

static inline uint64_t edge_key(int a, int b) {
    uint32_t lo = static_cast<uint32_t>(std::min(a, b));
    uint32_t hi = static_cast<uint32_t>(std::max(a, b));
    return (static_cast<uint64_t>(lo) << 32) ^ static_cast<uint64_t>(hi);
}
