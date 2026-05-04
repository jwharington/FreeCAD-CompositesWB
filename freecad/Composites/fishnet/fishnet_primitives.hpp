#pragma once

#include <cstdint>

struct Vec3 {
    double x{0.0};
    double y{0.0};
    double z{0.0};
};

constexpr double kVectorZeroEpsilon = 1.0e-12;

Vec3 operator+(const Vec3 &a, const Vec3 &b);
Vec3 operator-(const Vec3 &a, const Vec3 &b);
Vec3 operator*(const Vec3 &a, double s);

double dot(const Vec3 &a, const Vec3 &b);
Vec3 cross(const Vec3 &a, const Vec3 &b);
double norm(const Vec3 &a);
Vec3 normalize(const Vec3 &a);

uint64_t edge_key(int a, int b);
