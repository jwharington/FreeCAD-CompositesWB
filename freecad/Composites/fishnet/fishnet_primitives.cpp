#include "fishnet_primitives.hpp"

#include <algorithm>
#include <cmath>

Vec3 operator+(const Vec3 &a, const Vec3 &b) {
    return {a.x + b.x, a.y + b.y, a.z + b.z};
}

Vec3 operator-(const Vec3 &a, const Vec3 &b) {
    return {a.x - b.x, a.y - b.y, a.z - b.z};
}

Vec3 operator*(const Vec3 &a, double s) {
    return {a.x * s, a.y * s, a.z * s};
}

double dot(const Vec3 &a, const Vec3 &b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

Vec3 cross(const Vec3 &a, const Vec3 &b) {
    return {
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    };
}

double norm(const Vec3 &a) {
    return std::sqrt(dot(a, a));
}

Vec3 normalize(const Vec3 &a) {
    double n = norm(a);
    if (n <= kVectorZeroEpsilon) {
        return {0.0, 0.0, 0.0};
    }
    return {a.x / n, a.y / n, a.z / n};
}

uint64_t edge_key(int a, int b) {
    uint32_t lo = static_cast<uint32_t>(std::min(a, b));
    uint32_t hi = static_cast<uint32_t>(std::max(a, b));
    return (static_cast<uint64_t>(lo) << 32) ^ static_cast<uint64_t>(hi);
}
