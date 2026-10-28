#include "pulse/core.hpp"
#include <limits>
#include <unsupported/Eigen/MatrixFunctions>
namespace pulse {
void validate_physical(const Mode &mode, const Vector &out) {
    require(!mode.classification_only, 12, "UNACCEPTED_CANDIDATE",
            "region-classification candidate cannot be used as a physical solution");
    require(out.allFinite(), 7, "NONFINITE_PROPAGATION", "nonfinite validated state");
    if (mode.constraints.rows()) {
        const double scale = mode.constraints.lpNorm<Eigen::Infinity>() * out.lpNorm<Eigen::Infinity>() + 1.;
        require((mode.constraints * out).norm() <= 1e-9 * scale, 10, "PHYSICAL_CONSTRAINT_VIOLATION",
                "validated descriptor constraint drift");
    }
    if (mode.residual_map.rows()) {
        double scale = std::max(1., (mode.residual_reference * out).norm());
        require((mode.residual_map * out).norm() <= 1e-8 * scale, 10, "PHYSICAL_CONSTRAINT_VIOLATION",
                "validated propagated algebraic residual exceeds budget");
    }
}
Vector propagate(const Mode &mode, const Vector &s, double h, Stats &stats) {
    require(h >= 0 && std::isfinite(h), 7, "TIME_ORDER", "invalid propagation duration", true);
    if (h == 0)
        return s;
    ++stats.exponentials;
    Matrix e = (mode.M * h).exp();
    Vector out = e * s;
    out[out.size() - 1] = 1;
    require(out.allFinite(), 7, "NONFINITE_PROPAGATION", "matrix exponential produced nonfinite state");
    if (mode.constraints.rows()) {
        // Absolute 2e-9 is scale-blind: the LLC constraint row has norm ~1.56e9
        // and a valid state at 1.75us has |C s| ~1.13e-6 (relative 2.1e-12).
        // Use a scale-aware numerical residual; a genuine C s=1 inconsistency
        // still fails because ||C|| ||out|| is then O(1), not 1e9.
        const double scale = mode.constraints.lpNorm<Eigen::Infinity>() * out.lpNorm<Eigen::Infinity>() + 1.;
        require((mode.constraints * out).norm() <= 1e-9 * scale, 10, "PHYSICAL_CONSTRAINT_VIOLATION",
                "descriptor constraint drift");
    }
    if (mode.residual_map.rows()) {
        Matrix R = mode.residual_map;
        Vector residual = R * out;
        double scale = std::max(1., (mode.residual_reference * out).norm());
        if (residual.norm() > 1e-8 * scale) {
            // A single bounded algebraic projection is used only for
            // roundoff-scale drift in the descriptor residual map.  A genuine
            // incompatible mode has residual comparable to its reference scale
            // and is still rejected.
            if (residual.norm() > 1e-4 * scale)
                require(false, 10, "PHYSICAL_CONSTRAINT_VIOLATION",
                        "propagated algebraic residual exceeds budget");
            // Preserve the homogeneous coordinate.  Project only the n state
            // coordinates; setting the last coordinate back to one after a
            // full-row projection would leave the residual no longer zero when
            // a residual row has a nonzero constant/coefficient column.
            const int n = int(out.size()) - 1;
            Matrix R0 = R.leftCols(n);
            Eigen::JacobiSVD<Matrix> svd(R0, Eigen::ComputeThinU | Eigen::ComputeThinV);
            const auto &sv = svd.singularValues();
            Vector coeff = svd.matrixU().transpose() * residual;
            const double stol =
                std::numeric_limits<double>::epsilon() * R0.rows() * std::max(1., sv.size() ? sv[0] : 0.);
            for (int i = 0; i < coeff.size(); ++i)
                coeff[i] = sv[i] > stol ? coeff[i] / sv[i] : 0.;
            Vector correction = svd.matrixV() * coeff;
            out.head(n) -= correction;
            out[out.size() - 1] = 1;
            ++stats.projections;
            stats.max_projection_correction = std::max(stats.max_projection_correction, correction.norm());
            residual = R * out;
            stats.max_projected_residual = std::max(stats.max_projected_residual, residual.norm());
            if (mode.constraints.rows()) {
                const double cs =
                    mode.constraints.lpNorm<Eigen::Infinity>() * out.lpNorm<Eigen::Infinity>() + 1.;
                require((mode.constraints * out).norm() <= 1e-9 * cs, 10, "PHYSICAL_CONSTRAINT_VIOLATION",
                        "projection broke descriptor constraint");
            }
            require(residual.norm() <= 1e-8 * std::max(1., (mode.residual_reference * out).norm()), 10,
                    "PHYSICAL_CONSTRAINT_VIOLATION", "propagated algebraic residual exceeds budget");
        }
    }
    return out;
}
} // namespace pulse
