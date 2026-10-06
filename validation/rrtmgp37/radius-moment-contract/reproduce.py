#!/usr/bin/env python3
"""Portable NumPy reproduction of the bounded spherical Gamma-moment audit."""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


SOURCE_PATHS = (
    "WRF/phys/module_mp_udm.F",
    "WRF/phys/module_microphysics_driver.F",
    "WRF/Registry/Registry.EM_COMMON",
    "WRF/dyn_em/module_initialize_real.F",
)


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wrf-worktree", required=True, type=Path,
                        help="WRF repository checkout whose source identity is checked")
    parser.add_argument("--output", required=True, type=Path,
                        help="new JSON output path; existing files are never replaced")
    args = parser.parse_args()
    tree = args.wrf_worktree.resolve()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to replace {output}")
    sources = {}
    review = json.loads((Path(__file__).resolve().parent / "evidence/source-review.json").read_text())
    expected = {row["path"]: row["sha256"] for row in review["source"]["files"]}
    for rel in SOURCE_PATHS:
        p = tree / rel
        if not p.is_file():
            raise FileNotFoundError(p)
        digest = sha256(p)
        if rel not in expected or digest != expected[rel]:
            raise ValueError(f"source identity differs from frozen review: {rel}")
        sources[rel] = {"bytes": p.stat().st_size, "sha256": digest}

    # x=lambda*r; Laguerre weights integrate exp(-x) on [0,infinity).
    x, w = np.polynomial.laguerre.laggauss(64)
    rows = []
    for nu in range(2, 16):
        moments = [float(np.dot(w, x ** (nu + k))) for k in range(4)]
        exact = [math.gamma(nu + k + 1) for k in range(4)]
        relerr = max(abs(a - b) / b for a, b in zip(moments, exact))
        ratio = (nu + 3) / ((nu + 1) * (nu + 2) * (nu + 3)) ** (1 / 3)
        quad_ratio = (moments[3] / moments[2]) / (moments[3] / moments[0]) ** (1 / 3)
        if relerr > 5e-12 or abs(quad_ratio - ratio) > 5e-12:
            raise ArithmeticError(f"Gamma quadrature failed closure for nu={nu}")
        rows.append({"nu": nu, "gamma_moments_x_k0_to_k3": moments,
                     "max_relative_quadrature_error": relerr,
                     "re_M3_M2_over_volume_mean_radius": ratio,
                     "independent_quadrature_radius_ratio": quad_ratio})

    rho_w = 1000.0
    pi_udm = float(np.float32(3.141592653589793))
    samples = []
    for nc in (5e7, 1e8, 3e8, 1e9, 2.1e9):
        nc_autoconv = min(max(nc, 2.0), 1e12)
        nu = min(math.floor(1e9 / nc_autoconv + 0.5) + 2, 15)
        for lwc in (1e-5, 1e-4, 1e-3):
            native = 0.5 / (pi_udm * rho_w / 6 * nc / lwc) ** (1 / 3)
            volume = (3 * lwc / (4 * pi_udm * rho_w * nc)) ** (1 / 3)
            lam = (nc * (pi_udm * rho_w / 6) * 8 * math.gamma(nu + 4)
                   / math.gamma(nu + 1) / lwc) ** (1 / 3)
            re = (nu + 3) / lam
            if abs(native - volume) > 1e-18:
                raise ArithmeticError("native expression did not close to volume mean")
            samples.append({"number_concentration_m_minus3": nc,
                            "L_kg_m_minus3": lwc,
                            "nu_from_autoconversion_rule": nu,
                            "native_unclipped_formula_m": native,
                            "native_after_stated_radius_bounds_m": min(max(native, 2.51e-6), 50e-6),
                            "Gamma_effective_M3_M2_radius_m": re,
                            "unclipped_re_gamma_over_native": re / native,
                            "native_would_clip": not 2.51e-6 <= native <= 50e-6})
    result = {
        "schema": "udm37-liquid-radius-moment-reproduction-v1",
        "scope": "analytic moments and illustrative inputs only; no model or radiation solver",
        "wrf_worktree": str(tree),
        "source_files": sources,
        "quadrature": {"method": "64-node Gauss-Laguerre; x=lambda*r", "shape_rows": rows},
        "samples": samples,
        "radius_ratio_range": [min(r["re_M3_M2_over_volume_mean_radius"] for r in rows),
                               max(r["re_M3_M2_over_volume_mean_radius"] for r in rows)],
        "max_relative_quadrature_error": max(r["max_relative_quadrature_error"] for r in rows),
        "assumptions": ["Nc is interpreted as volumetric only for this conditional derivation",
                        "the autoconversion gamma PSD is not proven to be the radiation PSD",
                        "no physical accuracy or production-policy conclusion is made"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"status": "CALCULATION_WRITTEN", "shape_rows": len(rows),
                      "sample_rows": len(samples), "output": str(output)}, sort_keys=True))


if __name__ == "__main__":
    main()
