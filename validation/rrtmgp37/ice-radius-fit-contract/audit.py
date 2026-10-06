#!/usr/bin/env python3
"""Reproduce a bounded Wyser-recipe radius integration with stdlib quadrature.

This is a mathematical recipe audit, not a reproduction of unavailable literal
Eq. (35) coefficients and not a radiative-accuracy test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re


EXPECTED_SOURCE_SHA256 = "9b7b878b263f6b0111edba4cfb1c6c30e53b3f7534035cda2c0411a573b81c2c"
EXPECTED_PROVENANCE_SHA256 = "eb1c1158b8a52b1f511577d499c3d6d43ce367031c775380b244e8d49df2ac09"
NATIVE_COEFFICIENTS_UM = [377.4, 203.3, 37.91, 2.3696]
NATIVE_BOUNDS_UM = [5.01, 125.0]
B_SWEEP = [-6.0, -5.5, -5.0, -4.5, -4.0, -3.5, -3.0, -2.5, -2.0]
B_OUTSIDE = [-6.873515884666935, -6.5]
BREAKS_UM = [10.0, 20.0, 30.0, 1000.0]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def legendre_rule(n: int) -> tuple[list[float], list[float]]:
    """Positive Gauss-Legendre nodes and weights on [-1,1], Newton solved."""
    nodes = [0.0] * n
    weights = [0.0] * n
    half = (n + 1) // 2
    for i in range(1, half + 1):
        z = math.cos(math.pi * (i - 0.25) / (n + 0.5))
        for _ in range(100):
            p0, p1 = 1.0, z
            for k in range(2, n + 1):
                p0, p1 = p1, ((2*k - 1)*z*p1 - (k - 1)*p0) / k
            pn = p1 if n > 1 else z
            pnm1 = p0 if n > 1 else 1.0
            derivative = n * (z*pn - pnm1) / (z*z - 1.0)
            delta = pn / derivative
            z -= delta
            if abs(delta) < 2e-16:
                break
        else:
            raise ArithmeticError(f"Legendre root did not converge n={n}, i={i}")
        weight = 2.0 / ((1.0 - z*z) * derivative*derivative)
        nodes[i - 1] = -z
        nodes[n - i] = z
        weights[i - 1] = weight
        weights[n - i] = weight
    if any(weight <= 0.0 for weight in weights) or abs(sum(weights)-2.0) > 2e-13:
        raise ArithmeticError(f"Legendre rule positivity/normalization failed for n={n}")
    return nodes, weights


def distribution(L: float, B: float) -> float:
    if L <= 20.0:
        return L**3 * math.exp(-0.3 * L)
    return 20.0**3 * math.exp(-6.0) * (L / 20.0)**B


def diameter(L: float) -> float:
    # The recovered aspect-ratio rule is x=L/D, so invert x above 30 um.
    return L if L <= 30.0 else L / (1.0 + 0.003 * (L - 30.0))


def integrate_piecewise(fn, n: int) -> float:
    nodes, weights = legendre_rule(n)
    total = 0.0
    for left, right in zip(BREAKS_UM[:-1], BREAKS_UM[1:]):
        midpoint = 0.5 * (left + right)
        halfwidth = 0.5 * (right - left)
        total += halfwidth * sum(
            w * fn(midpoint + halfwidth*x) for x, w in zip(nodes, weights)
        )
    return total


def analytic_moment(B: float, power: int) -> float:
    """Exact-piece integral of L**power*n(L), including the logarithmic tail."""
    # For integer m, repeated integration by parts gives this finite expression
    # for the small-particle incomplete-gamma interval.
    m = power + 3
    lam = 0.3
    def finite_exp_sum(x: float) -> float:
        term = 1.0
        total = term
        for k in range(1, m + 1):
            term *= lam*x/k
            total += term
        return total
    small = math.factorial(m) / lam**(m + 1) * (
        math.exp(-lam*10.0)*finite_exp_sum(10.0)
        - math.exp(-lam*20.0)*finite_exp_sum(20.0))

    coefficient = 20.0**3 * math.exp(-6.0) / 20.0**B
    exponent = B + power
    if abs(exponent + 1.0) < 1e-14:
        tail = coefficient * math.log(1000.0 / 20.0)
    else:
        q = exponent + 1.0
        tail = coefficient * (1000.0**q - 20.0**q) / q
    return small + tail


def radii(B: float, n: int) -> dict[str, float]:
    numerator = integrate_piecewise(lambda L: diameter(L)**2 * L * distribution(L, B), n)
    denominator_w = integrate_piecewise(
        lambda L: (diameter(L)**2 * L)**(2.0/3.0) * distribution(L, B), n)
    denominator_va = integrate_piecewise(
        lambda L: (math.sqrt(3.0)/4.0 * diameter(L)**2 + diameter(L)*L)
                  * distribution(L, B), n)
    return {"Wyser_rW_um": 0.5*numerator/denominator_w,
            "Wyser_rVA_um": (3.0*math.sqrt(3.0)/8.0)*numerator/denominator_va}


def source_check(source: Path) -> dict[str, object]:
    digest = sha256(source)
    if digest != EXPECTED_SOURCE_SHA256:
        raise ValueError(f"native UDM source hash mismatch: {digest}")
    text = source.read_text()
    coefficient_rows = re.findall(
        r"(?m)^\s*temp\s*=\s*(377\.4)\s*\+\s*(203\.3)\*bfactor\s*\+\s*(37\.91)\*bfactor2\s*\+\s*(2\.3696)\*bfactor3", text)
    if len(coefficient_rows) != 1 or [float(v) for v in coefficient_rows[0]] != NATIVE_COEFFICIENTS_UM:
        raise ValueError("expected the native radius polynomial exactly once")
    bounds = {}
    for name, pattern in (("reimin", r"5\.01e-6"), ("reimax", r"125\.e-6")):
        matches = re.findall(rf"(?m)^\s*{name}\s*=\s*({pattern})\b", text)
        if len(matches) != 1:
            raise ValueError(f"expected source radius bound {name} exactly once")
        bounds[name] = float(matches[0])
    return {"path": "WRF/phys/module_mp_udm.F", "sha256": digest,
            "native_radius_polynomial_coefficients_um": NATIVE_COEFFICIENTS_UM,
            "native_radius_bounds_m": bounds,
            "source_anchor": "udm_mp_effective_radius; temp=377.4+203.3*bfactor+37.91*bfactor2+2.3696*bfactor3",
            "literal_wyser_eq35_coefficients": "NOT_AUTHENTICATED_OR_NOT_CLAIMED"}


def build_result(source: Path, provenance: Path) -> dict[str, object]:
    if sha256(provenance) != EXPECTED_PROVENANCE_SHA256:
        raise ValueError("Wyser provenance note hash mismatch")
    source_record = source_check(source)
    low, high = 128, 256
    rows = []
    for B in B_SWEEP + B_OUTSIDE:
        r128 = radii(B, low)
        r256 = radii(B, high)
        relative = {name: abs(r256[name] - r128[name]) / abs(r256[name])
                    for name in r256}
        if max(relative.values()) > 2e-11:
            raise ArithmeticError(f"128/256 quadrature did not converge at B={B}: {relative}")
        rows.append({"B": B, "in_reported_fit_domain": -6.0 <= B <= -2.0,
                     "quadrature_128": r128, "quadrature_256": r256,
                     "relative_128_to_256": relative})

    # Independent analytic oracle for D=L: both radii reduce to a constant
    # multiple of M3/M2 for the same continuous mixed spectrum.
    oracles = []
    for b_oracle in (-4.0, -3.0):
        moments, analytic_moments = {}, {}
        for power in (2, 3):
            moments[f"M{power}"] = integrate_piecewise(
                lambda L: L**power * distribution(L, b_oracle), 256)
            analytic_moments[f"M{power}"] = analytic_moment(b_oracle, power)
        analytic_relerr = max(abs(moments[k]-analytic_moments[k])/abs(analytic_moments[k])
                              for k in moments)
        if analytic_relerr > 2e-12:
            raise ArithmeticError(f"analytic power-tail oracle failed at B={b_oracle}: {analytic_relerr}")
        ratio = analytic_moments["M3"] / analytic_moments["M2"]
        analytic_rw = 0.5 * ratio
        analytic_rva = 3.0*math.sqrt(3.0)/(2.0*(math.sqrt(3.0)+4.0)) * ratio
        direct_rva = (3.0*math.sqrt(3.0)/8.0) * analytic_moments["M3"] / (
            (math.sqrt(3.0)/4.0+1.0)*analytic_moments["M2"])
        if abs(direct_rva-analytic_rva) > 1e-12:
            raise ArithmeticError("D=L analytic radius-ratio identity failed")
        oracles.append({
            "B": b_oracle, "quadrature_moments_M2_M3": moments,
            "analytic_moments_M2_M3": analytic_moments,
            "relative_difference_vs_256_GL": analytic_relerr,
            "M3_tail_power_exponent": b_oracle+3.0,
            "M3_tail_uses_log_integral": abs(b_oracle+3.0+1.0) < 1e-14,
            "M2_tail_power_exponent": b_oracle+2.0,
            "M2_tail_uses_log_integral": abs(b_oracle+2.0+1.0) < 1e-14,
            "M3_over_M2_um": ratio, "rW_um": analytic_rw,
            "rVA_um": analytic_rva, "rVA_over_rW": analytic_rva/analytic_rw,
            "rW_over_rVA": analytic_rw/analytic_rva,
            "closed_form_rW_over_rVA": (math.sqrt(3.0)+4.0)/(3.0*math.sqrt(3.0)),
        })

    # Compare the implemented ideal-binary64 cubic separately on the same
    # numeric coordinates as the Wyser sweep; B is not the native bfactor.
    for row in rows:
        B = row["B"]
        value = (NATIVE_COEFFICIENTS_UM[0] + NATIVE_COEFFICIENTS_UM[1]*B
                 + NATIVE_COEFFICIENTS_UM[2]*B*B + NATIVE_COEFFICIENTS_UM[3]*B*B*B)
        bounded = min(max(value, NATIVE_BOUNDS_UM[0]), NATIVE_BOUNDS_UM[1])
        row["native_ideal64_cubic_numeric_coordinate_only"] = {
            "same_numeric_argument_as_B_not_a_shared_physical_variable": B,
            "unbounded_um": value, "bounded_um": bounded,
            "bounded_minus_Wyser_rW_um": bounded-row["quadrature_256"]["Wyser_rW_um"],
        }

    return {
        "schema": "udm37-ice-radius-fit-recipe-audit-v1",
        "status": "PASS_NUMERICAL_RECIPE_AUDIT",
        "scope": "Stdlib double-precision quadrature of the recovered mixed-PSD recipe; no solver, WRF execution, or production change.",
        "source": source_record,
        "provenance": {"path": "validation/rrtmgp37/ice-radius-fit-contract/provenance.json",
                       "sha256": EXPECTED_PROVENANCE_SHA256,
                       "citation": "Wyser (1998), The Effective Radius in Ice Clouds, J. Climate 11(7), 1793–1802",
                       "literal_eq35_coefficients": "NOT_RECOVERED in retained primary record; this calculation does not claim them"},
        "recipe": {
            "L_bounds_um": [10.0, 1000.0], "breaks_um": BREAKS_UM,
            "n_small": "L^3 exp(-0.3 L), 10<=L<=20",
            "n_tail": "20^3 exp(-6) (L/20)^B, 20<L<=1000; continuous at 20",
            "L_over_D": "1 for L<=30; 1+0.003(L-30) for L>30 (therefore D=L/x)",
            "B_fit_sweep": B_SWEEP, "outside_domain_examples": B_OUTSIDE,
            "quadrature": "positive Gauss-Legendre on each [10,20], [20,30], [30,1000] interval",
            "orders_compared": [128, 256], "max_allowed_relative_difference": 2e-11,
        },
        "rows": rows,
        "D_equals_L_analytic_oracles": oracles,
        "native_udm_polynomial_diagnostic": "Each sweep row includes ideal binary64 native cubic on the same numeric argument for a bounded curve comparison only; the Wyser B and native bfactor are not physically identified.",
        "result_comparator_control": comparator_control(),
        "limits": [
            "The article-supported recipe and integration domain are used, but literal Eq. (35) coefficients were not recovered from the retained primary HTML/PDF attempt.",
            "This does not establish that the native UDM coefficients were generated from this recipe or that the two input coordinates are equivalent.",
            "No density multiplier, B clamp, optical correction, LUT contract, or physical-accuracy conclusion is justified by this calculation.",
        ],
        "execution_counts": {"quadrature_orders_per_B": 2, "B_values": len(rows),
                             "WRF_builds": 0, "WRF_models": 0, "radiation_solver_calls": 0},
    }


def compare_saved(saved: object, computed: object, path: str = "$") -> list[str]:
    """Portable full-structure check: metadata exact, finite floats tolerant."""
    if type(saved) is not type(computed):
        return [f"{path}: type mismatch"]
    if isinstance(computed, dict):
        if saved.keys() != computed.keys():
            return [f"{path}: key mismatch"]
        return [err for key in computed for err in compare_saved(saved[key], computed[key], f"{path}.{key}")]
    if isinstance(computed, list):
        if len(saved) != len(computed):
            return [f"{path}: length mismatch"]
        return [err for i, (a, b) in enumerate(zip(saved, computed))
                for err in compare_saved(a, b, f"{path}[{i}]")]
    if isinstance(computed, float):
        if not math.isfinite(saved) or not math.isfinite(computed):
            return [f"{path}: non-finite float"]
        return [] if math.isclose(saved, computed, rel_tol=2e-12, abs_tol=1e-12) else [f"{path}: numeric mismatch"]
    return [] if saved == computed else [f"{path}: value mismatch"]


def comparator_control() -> dict[str, str]:
    original = {"values": [10.0], "flag": True}
    changed = {"values": [10.00001], "flag": True}
    near = {"values": [10.0 + 1e-13], "flag": True}
    if not compare_saved(original, changed):
        raise ArithmeticError("result verifier accepted altered numeric result")
    if compare_saved(original, near):
        raise ArithmeticError("result verifier rejected within-tolerance roundoff")
    return {"altered_numeric": "rejected", "roundoff_within_tolerance": "accepted",
            "float_tolerance": "rel_tol=2e-12, abs_tol=1e-12; nonnumeric fields exact"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[3]
    parser.add_argument("--source", type=Path, default=root / "WRF/phys/module_mp_udm.F")
    parser.add_argument("--provenance", type=Path,
        default=Path(__file__).resolve().with_name("provenance.json"))
    parser.add_argument("--result", type=Path,
                        default=Path(__file__).resolve().with_name("result.json"),
                        help="stored deterministic result to verify or generate")
    parser.add_argument("--generate", action="store_true",
                        help="create --result, refusing to replace an existing file")
    args = parser.parse_args()
    result = build_result(args.source.resolve(), args.provenance.resolve())
    serialized = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    out = args.result.resolve()
    if args.generate:
        if out.exists():
            raise FileExistsError(f"refusing to overwrite {out}")
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x") as f:
            f.write(serialized)
        print(json.dumps({"status": "GENERATED", "result": str(out),
                          "sha256": sha256(out)}, sort_keys=True))
    else:
        if not out.is_file():
            raise FileNotFoundError(f"result missing; use --generate to create it: {out}")
        saved = json.loads(out.read_text())
        differences = compare_saved(saved, result)
        if differences:
            raise ValueError(f"stored result differs from reproducible calculation: {differences[:8]}")
        print(json.dumps({"status": "VERIFIED", "result": str(out),
                          "sha256": sha256(out), "B_rows": len(result["rows"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
