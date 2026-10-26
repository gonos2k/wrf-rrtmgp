"""Independent arithmetic checks for the technical report; never a model/physics approval.

Uses existing JSON/CSV and manufactured rational examples. No WRF, NetCDF,
RTE, Mie, compiler, coefficient replacement, or empirical tuning is invoked.
"""

from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal
import argparse
import csv
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "validation/rrtmgp37"


def load(name):
    return json.loads((BASE / name / "result.json").read_text())


def check_native_mass_and_cloud_footprint():
    """manufactured rational identity."""
    md = F(1, 50) * 90000 / F("9.81")
    grid = md * F("0.0002") * 1000
    cloud_fraction = F("0.4")
    inside = grid / cloud_fraction
    assert cloud_fraction * inside == grid
    return {
        "name": "native_mass_and_cloud_footprint",
        "kind": "manufactured rational identity",
        "dry_mass_kg_m2": float(md),
        "grid_path_g_m2": float(grid),
        "incloud_path_g_m2": float(inside),
    }


def check_dry_gas_column_and_number_units():
    """manufactured rational conversion."""
    avogadro = F("6.02214076e23")
    molar_dry = F("0.028964")
    molecules_cm2 = avogadro / molar_dry / 10000
    number = F(100000000)
    density = F("1.2")
    eta = number / density
    assert density * eta == number
    changed_density = F("1.44")
    assert changed_density * eta == F(120000000)
    return {
        "name": "dry_gas_column_and_number_units",
        "kind": "manufactured rational conversion",
        "one_kg_dry_molecules_cm2": float(molecules_cm2),
        "number_per_kg_dry": float(eta),
        "new_density_volume_number_m3": float(changed_density * eta),
    }


def check_source_positivity_condition():
    """manufactured rational source update."""
    a0, a1, q0, dt, requested = F(90000), F(90000), F("1e-7"), F(60), F("-2e-4")
    bound = -(a0 * q0) / dt
    unlimited = (a0 * q0 + dt * requested) / a1
    limited = (a0 * q0 + dt * bound) / a1
    assert unlimited < 0 and limited == 0
    return {
        "name": "source_positivity_condition",
        "kind": "manufactured rational source update",
        "unlimited_qv": float(unlimited),
        "threshold_tendency": float(bound),
        "threshold_result_qv": float(limited),
    }


def check_finite_volume_flux_sign_and_telescope():
    """manufactured rational two-layer energy identity."""
    net_up = [F(50), F(30), F(40)]
    capacity = [F(100) * F("1004.5"), F(200) * F("1004.5")]
    exner = [F("0.9"), F("0.8")]
    temperature_tendency = [(net_up[k] - net_up[k + 1]) / capacity[k] for k in range(2)]
    theta_tendency = [temperature_tendency[k] / exner[k] for k in range(2)]
    reconstructed = sum(capacity[k] * exner[k] * theta_tendency[k] for k in range(2))
    assert reconstructed == net_up[0] - net_up[-1] == 10
    return {
        "name": "finite_volume_flux_sign_and_telescope",
        "kind": "manufactured rational two-layer energy identity",
        "column_convergence_W_m2": float(reconstructed),
        "temperature_tendency_K_s": list(map(float, temperature_tendency)),
    }


def check_coupled_moist_to_dry_finite_change():
    """manufactured exact rational identity."""
    a0, a1, perturb0, perturb1 = F(90000), F(89900), F(-8), F(-7)
    q0, q1, ratio = F("0.008"), F("0.007"), F("461.6") / 287
    delta_b = a1 * perturb1 - a0 * perturb0
    delta_moist = (delta_b - perturb0 * (a1 - a0)) / a1
    dry0 = (perturb0 + 300) / (1 + ratio * q0)
    dry1 = (perturb1 + 300) / (1 + ratio * q1)
    allocated = delta_moist / (1 + ratio * q1) - ratio * dry0 * (q1 - q0) / (1 + ratio * q1)
    assert delta_moist == perturb1 - perturb0 and allocated == dry1 - dry0
    return {
        "name": "coupled_moist_to_dry_finite_change",
        "kind": "manufactured exact rational identity",
        "dry_theta_change_K": float(allocated),
    }


def check_diameter_PSD_normalization_and_hail_tau_units():
    """analytic artificial Qabs plus saved coefficients; no Mie rerun."""
    frozen = load("frozen-important-state-reference")
    state = frozen["actual_state"]
    water_path = state["layer_hail_path_g_m2"] * 0.001
    tau_a = [
        water_path * band["A_current_kappa_m2_kg"] for band in frozen["coefficient_comparisons"]
    ]
    tau_c = [
        water_path * band["C_independent_kappa_m2_kg"] for band in frozen["coefficient_comparisons"]
    ]
    assert len(tau_a) == len(tau_c) == 16 and min(tau_a + tau_c) > 0
    # Analytic diameter-PSD moments for artificial size-independent Qabs=1.
    lam, bulk_density = F(400), F(912)
    diameter_moment2, diameter_moment3 = (
        F(math.factorial(2), 1) / lam**3,
        F(math.factorial(3), 1) / lam**4,
    )
    coefficient = F(1, 4) * diameter_moment2 / (bulk_density / 6 * diameter_moment3)
    assert coefficient == lam / (2 * bulk_density)
    return {
        "name": "diameter_PSD_normalization_and_hail_tau_units",
        "kind": "analytic artificial Qabs plus saved coefficients; no Mie rerun",
        "tau_current_min_max": [min(tau_a), max(tau_a)],
        "tau_reference_min_max": [min(tau_c), max(tau_c)],
        "maximum_tau_difference": max(abs(c - a) for a, c in zip(tau_a, tau_c)),
    }


def check_stored_hourly_transport_identity():
    """independent Decimal recombination of saved terms, not face solver."""
    transport = load("sterling-transport-state")
    hour15 = next(x for x in transport["hourly"] if x["start_hour_UTC"] == 15)["layers"][1]["sums"]
    names = [
        "qv_center_relative_face_g_kg",
        "qv_center_mass_convergence_g_kg",
        "qv_native_divergence_roundoff_g_kg",
    ]
    residual = sum(Decimal(str(hour15[n])) for n in names) - Decimal(
        str(hour15["qv_vertical_g_kg"])
    )
    assert abs(residual) < Decimal("1e-15")
    totals = [
        {
            "hour": x["start_hour_UTC"],
            "H_plus_V_g_kg": x["layers"][1]["sums"]["qv_horizontal_g_kg"]
            + x["layers"][1]["sums"]["qv_vertical_g_kg"],
        }
        for x in transport["hourly"]
    ]
    assert all(x["H_plus_V_g_kg"] < 0 for x in totals)
    return {
        "name": "stored_hourly_transport_identity",
        "kind": "independent Decimal recombination of saved terms, not face solver",
        "sum_residual_g_kg": str(residual),
        "hourly_horizontal_plus_vertical": totals,
    }


def check_fixed_station_daily_statistics():
    """independent saved CSV recalculation; no new forecast."""
    with (BASE / "sterling-interior-day-evaluation/hourly-comparison.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    model = [float(row["model_W_m2"]) for row in rows]
    observed = [float(row["primary_W_m2"]) for row in rows]
    differences = [a - b for a, b in zip(model, observed)]
    squared = math.fsum(d * d for d in differences)
    rmse = math.sqrt(squared / len(rows))
    bias = math.fsum(differences) / len(rows)
    concentration = (
        math.fsum(
            d * d for row, d in zip(rows, differences) if 17 <= int(row["start_utc"][11:13]) < 20
        )
        / squared
    )
    published = load("sterling-interior-day-evaluation")["statistics"]["primary"]["all"]
    assert len(rows) == 24 and math.isclose(rmse, published["RMSE_W_m2"], abs_tol=1e-12)
    assert math.isclose(bias, published["bias_W_m2"], abs_tol=1e-12)
    return {
        "name": "fixed_station_daily_statistics",
        "kind": "independent saved CSV recalculation; no new forecast",
        "RMSE_W_m2": rmse,
        "bias_W_m2": bias,
        "squared_error_share_17_20UTC": concentration,
        "model_energy_MJ_m2": math.fsum(model) * 3600 / 1e6,
        "observed_energy_MJ_m2": math.fsum(observed) * 3600 / 1e6,
    }


def check_precipitation_one_step_delivery_ledger():
    """manufactured rational time-location identity."""
    initial_pending = F(15)
    intervals = list(map(F, [15, 15, 30, 0, 0]))
    rain_accumulation = sum(intervals)
    surface_delivery = initial_pending + sum(intervals[:-1])
    assert rain_accumulation - surface_delivery == intervals[-1] - initial_pending
    return {
        "name": "precipitation_one_step_delivery_ledger",
        "kind": "manufactured rational time-location identity",
        "rain_total_with_initial10": float(10 + rain_accumulation),
        "surface_delivery": float(surface_delivery),
        "pending_endpoint_difference": float(intervals[-1] - initial_pending),
    }


def run_checks():
    checks = [
        check_native_mass_and_cloud_footprint(),
        check_dry_gas_column_and_number_units(),
        check_source_positivity_condition(),
        check_finite_volume_flux_sign_and_telescope(),
        check_coupled_moist_to_dry_finite_change(),
        check_diameter_PSD_normalization_and_hail_tau_units(),
        check_stored_hourly_transport_identity(),
        check_fixed_station_daily_statistics(),
        check_precipitation_one_step_delivery_ledger(),
    ]
    inputs = [
        BASE / name / "result.json"
        for name in [
            "frozen-important-state-reference",
            "sterling-transport-state",
            "sterling-interior-day-evaluation",
        ]
    ]
    inputs.append(BASE / "sterling-interior-day-evaluation/hourly-comparison.csv")
    return {
        "scope": "report arithmetic and existing evidence only",
        "check_count": len(checks),
        "checks": checks,
        "inputs": {
            str(path.relative_to(ROOT)): {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            }
            for path in inputs
        },
        "new_model_solver_compiler_NetCDF_calls": 0,
        "physical_accuracy_approved": False,
        "new_scientific_closure_conditions": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("review-math.json"))
    args = parser.parse_args()
    result = run_checks()
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(
        f"REPORT_ARITHMETIC_CHECKS_PASS={result['check_count']}; new model/solver/compiler calls=0; physical accuracy remains unapproved"
    )


if __name__ == "__main__":
    main()
