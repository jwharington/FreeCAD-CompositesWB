#include "fishnet_kindrape_nr.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <limits>

namespace fishnet_internal
{

    namespace
    {

        constexpr double kPi = 3.14159265358979323846;
        constexpr double kHalfPi = 0.5 * kPi;

        double wrap_angle_near(double angle, double reference)
        {
            while ((angle - reference) > kPi)
            {
                angle -= 2.0 * kPi;
            }
            while ((angle - reference) < -kPi)
            {
                angle += 2.0 * kPi;
            }
            return angle;
        }

        bool finite(double value)
        {
            return std::isfinite(value);
        }

        Vec3 unit_from_angle(double theta)
        {
            return {std::cos(theta), std::sin(theta), 0.0};
        }

        double signed_shear_from_vectors(const Vec3 &candidate, const Vec3 &reference)
        {
            const double n_c = std::sqrt(candidate.x * candidate.x + candidate.y * candidate.y);
            const double n_r = std::sqrt(reference.x * reference.x + reference.y * reference.y);
            if (n_c <= kVectorZeroEpsilon || n_r <= kVectorZeroEpsilon)
            {
                return std::numeric_limits<double>::infinity();
            }

            const double c = std::clamp(dot(candidate, reference) / (n_c * n_r), -1.0, 1.0);
            const double angle = std::acos(c);
            const double orientation = candidate.x * reference.y - candidate.y * reference.x;
            const double sign = (orientation >= 0.0) ? 1.0 : -1.0;
            return sign * (kHalfPi - angle);
        }

        double objective_for_theta(double theta, const Vec3 &reference, double target_shear_rad)
        {
            const Vec3 cand = unit_from_angle(theta);
            const double signed_shear = signed_shear_from_vectors(cand, reference);
            if (!finite(signed_shear))
            {
                return std::numeric_limits<double>::infinity();
            }
            const double mismatch = signed_shear - target_shear_rad;
            return mismatch * mismatch;
        }

        double derivative_first(double theta, const Vec3 &reference, double target_shear_rad)
        {
            const double h = 1.0e-4;
            const double f_plus = objective_for_theta(theta + h, reference, target_shear_rad);
            const double f_minus = objective_for_theta(theta - h, reference, target_shear_rad);
            if (!finite(f_plus) || !finite(f_minus))
            {
                return std::numeric_limits<double>::infinity();
            }
            return (f_plus - f_minus) / (2.0 * h);
        }

        double derivative_second(double theta, const Vec3 &reference, double target_shear_rad)
        {
            const double h = 1.0e-4;
            const double f0 = objective_for_theta(theta, reference, target_shear_rad);
            const double f_plus = objective_for_theta(theta + h, reference, target_shear_rad);
            const double f_minus = objective_for_theta(theta - h, reference, target_shear_rad);
            if (!finite(f0) || !finite(f_plus) || !finite(f_minus))
            {
                return std::numeric_limits<double>::infinity();
            }
            return (f_plus - 2.0 * f0 + f_minus) / (h * h);
        }

        double fallback_coarse_refine(double theta_init, const Vec3 &reference, double target_shear_rad)
        {
            double best_theta = theta_init;
            double best_obj = objective_for_theta(theta_init, reference, target_shear_rad);

            constexpr int kSampleCount = 33;
            for (int i = 0; i < kSampleCount; ++i)
            {
                const double t = -kPi + (2.0 * kPi) * static_cast<double>(i) / static_cast<double>(kSampleCount - 1);
                const double theta = wrap_angle_near(theta_init + t, theta_init);
                const double obj = objective_for_theta(theta, reference, target_shear_rad);
                if (!finite(obj))
                {
                    continue;
                }
                if (obj < best_obj - 1.0e-15 ||
                    (std::abs(obj - best_obj) <= 1.0e-15 && std::abs(theta - theta_init) < std::abs(best_theta - theta_init)))
                {
                    best_obj = obj;
                    best_theta = theta;
                }
            }

            double left = best_theta - (kPi / 16.0);
            double right = best_theta + (kPi / 16.0);
            for (int iter = 0; iter < 10; ++iter)
            {
                const double mid = 0.5 * (left + right);
                const double f_left = objective_for_theta(left, reference, target_shear_rad);
                const double f_mid = objective_for_theta(mid, reference, target_shear_rad);
                const double f_right = objective_for_theta(right, reference, target_shear_rad);
                if (!finite(f_left) || !finite(f_mid) || !finite(f_right))
                {
                    break;
                }
                if (f_left < f_right)
                {
                    right = mid;
                }
                else
                {
                    left = mid;
                }
                best_theta = 0.5 * (left + right);
            }

            return best_theta;
        }

    } // namespace

    Step2NrSolveResult solve_step2_generator_cell_nr(
        const Vec3 &current_point,
        const Vec3 &reference_vector,
        const Vec3 &initial_direction,
        double nominal_edge_length,
        double target_pre_shear_deg)
    {
        Step2NrSolveResult result;

        if (!finite(nominal_edge_length) || nominal_edge_length <= kVectorZeroEpsilon)
        {
            result.infeasible = true;
            result.objective_initial = std::numeric_limits<double>::infinity();
            result.objective_final = std::numeric_limits<double>::infinity();
            return result;
        }

        const double n_ref = std::sqrt(reference_vector.x * reference_vector.x + reference_vector.y * reference_vector.y);
        const double n_init = std::sqrt(initial_direction.x * initial_direction.x + initial_direction.y * initial_direction.y);
        if (n_ref <= kVectorZeroEpsilon || n_init <= kVectorZeroEpsilon)
        {
            result.infeasible = true;
            result.objective_initial = std::numeric_limits<double>::infinity();
            result.objective_final = std::numeric_limits<double>::infinity();
            return result;
        }

        const Vec3 ref_unit{reference_vector.x / n_ref, reference_vector.y / n_ref, 0.0};
        const Vec3 init_unit{initial_direction.x / n_init, initial_direction.y / n_init, 0.0};

        const double base_shear = signed_shear_from_vectors(init_unit, ref_unit);
        if (!finite(base_shear))
        {
            result.infeasible = true;
            result.objective_initial = std::numeric_limits<double>::infinity();
            result.objective_final = std::numeric_limits<double>::infinity();
            return result;
        }
        const double pre_shear_rad = std::clamp(target_pre_shear_deg, -45.0, 45.0) * (kPi / 180.0);
        const double target_shear_rad = std::clamp(base_shear + pre_shear_rad, -kHalfPi + 1.0e-6, kHalfPi - 1.0e-6);

        double theta = std::atan2(init_unit.y, init_unit.x);
        const double theta_init = theta;

        double f_cur = objective_for_theta(theta, ref_unit, target_shear_rad);
        result.objective_initial = f_cur;
        if (!finite(f_cur))
        {
            result.infeasible = true;
            result.objective_final = std::numeric_limits<double>::infinity();
            return result;
        }

        constexpr int kMaxNewtonIterations = 10;
        bool converged = false;
        for (int iter = 0; iter < kMaxNewtonIterations; ++iter)
        {
            result.iterations += 1;
            const double f1 = derivative_first(theta, ref_unit, target_shear_rad);
            const double f2 = derivative_second(theta, ref_unit, target_shear_rad);
            if (!finite(f1) || !finite(f2) || std::abs(f2) <= 1.0e-12)
            {
                break;
            }

            if (std::abs(f1) <= 1.0e-9)
            {
                converged = true;
                break;
            }

            const double newton_step = f1 / f2;
            bool accepted = false;
            for (int ls = 0; ls < 8; ++ls)
            {
                const double alpha = std::ldexp(1.0, -ls);
                const double theta_try = wrap_angle_near(theta - alpha * newton_step, theta_init);
                const double f_try = objective_for_theta(theta_try, ref_unit, target_shear_rad);
                if (!finite(f_try))
                {
                    continue;
                }
                if (f_try <= f_cur - 1.0e-14)
                {
                    theta = theta_try;
                    f_cur = f_try;
                    accepted = true;
                    break;
                }
            }

            if (!accepted)
            {
                break;
            }

            if (std::abs(newton_step) <= 1.0e-6 || f_cur <= 1.0e-12)
            {
                converged = true;
                break;
            }
        }

        if (!converged)
        {
            result.used_fallback = true;
            theta = fallback_coarse_refine(theta_init, ref_unit, target_shear_rad);
            theta = wrap_angle_near(theta, theta_init);
            f_cur = objective_for_theta(theta, ref_unit, target_shear_rad);
        }

        if (!finite(f_cur))
        {
            result.infeasible = true;
            result.objective_final = std::numeric_limits<double>::infinity();
            return result;
        }

        const Vec3 solved_unit = unit_from_angle(theta);
        result.solved_point = {
            current_point.x + nominal_edge_length * solved_unit.x,
            current_point.y + nominal_edge_length * solved_unit.y,
            0.0,
        };
        result.objective_final = f_cur;
        result.converged = converged;
        result.success = finite(result.solved_point.x) && finite(result.solved_point.y);

        if (!result.success)
        {
            result.infeasible = true;
            return result;
        }

        return result;
    }

} // namespace fishnet_internal
