#!/usr/bin/env python3
"""Independent raw-record localization of negative values in ODdeflt files."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from collections import defaultdict
from pathlib import Path


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_record(f):
    m = f.read(4)
    if not m:
        return None
    if len(m) != 4:
        raise ValueError("truncated record marker")
    n = struct.unpack("<i", m)[0]
    if n < 0:
        raise ValueError(f"negative record size {n}")
    payload = f.read(n)
    trail = f.read(4)
    if len(payload) != n or len(trail) != 4 or struct.unpack("<i", trail)[0] != n:
        raise ValueError("record marker/payload mismatch")
    return payload


def analyze_file(path: Path, expected: dict, width: float, bins: dict):
    nall = nneg = 0
    vmin = math.inf
    negmin = 0.0
    negmin_nu = None
    negmin_panel = None
    negmin_raw = None
    negmax = -math.inf
    panels = 0
    with path.open("rb") as f:
        h = read_record(f)
        if h is None or len(h) != 177 * 8:
            raise ValueError(f"{path}: unexpected file header")
        layer = struct.unpack_from("<q", h, 165 * 8)[0]
        if layer != expected["layer"]:
            raise ValueError(f"{path}: header layer {layer} != parse receipt {expected['layer']}")
        flags = [struct.unpack_from("<q", h, (147 + i) * 8)[0] for i in range(17)]
        pave, tave = struct.unpack_from("<2d", h, 11 * 8)
        if flags[4] != 0 or flags[8] != 0 or flags[10] != 1:
            raise ValueError(f"{path}: expected IEMIT=0, JRAD=0, IMRG=1; got {flags[4]}, {flags[8]}, {flags[10]}")
        while True:
            ph = read_record(f)
            if ph is None:
                raise ValueError(f"{path}: missing ENDFIL")
            if len(ph) == 48 and struct.unpack("<6q", ph) == (-99,) * 6:
                break
            if len(ph) != 32:
                raise ValueError(f"{path}: unexpected panel header size {len(ph)}")
            v1, v2, dv = struct.unpack_from("<3d", ph)
            n = struct.unpack_from("<q", ph, 24)[0]
            data = read_record(f)
            if n <= 0 or data is None or len(data) != n * 8:
                raise ValueError(f"{path}: invalid panel data size")
            vals = struct.unpack("<" + "d" * n, data)
            if not all(math.isfinite(x) for x in vals):
                raise ValueError(f"{path}: nonfinite output in panel {panels}")
            for i, value in enumerate(vals):
                nu = v1 + i * dv
                nall += 1
                vmin = min(vmin, value)
                if value < 0.0:
                    nneg += 1
                    negmax = max(negmax, value)
                    b = int(math.floor(nu / width))
                    a = bins[b]
                    a["count"] += 1
                    a["min"] = min(a["min"], value)
                    a["layers"].add(layer)
                    if value < negmin:
                        negmin, negmin_nu, negmin_panel = value, nu, panels
                        # Keep the IEEE bytes as emitted, useful for independent spot checks.
                        negmin_raw = data[i * 8 : (i + 1) * 8].hex()
            panels += 1
        if read_record(f) is not None:
            raise ValueError(f"{path}: data after ENDFIL")
    if nall != expected["sample_count"] or nneg != expected["negative_count"]:
        raise ValueError(f"{path}: raw counts {nall}/{nneg} disagree with prior parser {expected['sample_count']}/{expected['negative_count']}")
    if nneg == 0:
        if expected["negative_min"] is not None:
            raise ValueError(f"{path}: expected negative minimum despite zero negatives")
    elif expected["negative_min"] is None or negmin != expected["negative_min"]:
        raise ValueError(f"{path}: raw minimum {negmin} differs from prior parser {expected['negative_min']}")
    return {
        "file": path.name,
        "sha256": sha(path),
        "layer": layer,
        "PAVE_mbar": pave,
        "TAVE_K": tave,
        "IEMIT": flags[4],
        "JRAD": flags[8],
        "IMRG": flags[10],
        "panel_count": panels,
        "sample_count": nall,
        "negative_count": nneg,
        "negative_fraction": nneg / nall,
        "minimum_value": vmin,
        "most_negative_value": negmin if nneg else None,
        "most_negative_wavenumber_cm-1": negmin_nu,
        "most_negative_panel_index_zero_based": negmin_panel,
        "most_negative_ieee754_le_hex": negmin_raw,
        "largest_negative_value": negmax if nneg else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--parse-receipt", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--bin-width", type=float, default=25.0)
    a = ap.parse_args()
    if a.output.exists():
        raise SystemExit(f"refusing to overwrite {a.output}")
    prior = json.loads(a.parse_receipt.read_text())
    bins = defaultdict(lambda: {"count": 0, "min": math.inf, "layers": set()})
    rows = []
    for expected in prior["layers"]:
        path = a.run_dir / expected["file"]
        rows.append(analyze_file(path, expected, a.bin_width, bins))
    if len(rows) != 45:
        raise ValueError(f"expected 45 output layers, got {len(rows)}")
    binned = []
    for ibin, x in sorted(bins.items()):
        if x["count"]:
            binned.append({"wavenumber_min_cm-1": ibin * a.bin_width,
                           "wavenumber_max_cm-1": (ibin + 1) * a.bin_width,
                           "negative_count": x["count"], "most_negative_value": x["min"],
                           "layers_with_negatives": sorted(x["layers"])})
    total = sum(r["sample_count"] for r in rows)
    negatives = sum(r["negative_count"] for r in rows)
    global_min = min((r for r in rows if r["negative_count"]), key=lambda r: r["most_negative_value"], default=None)
    result = {
        "status": "RAW_RECORDS_RECONCILED",
        "scope": "Read-only record-level localization only; no values clipped and no solver/build rerun.",
        "run_dir": str(a.run_dir),
        "prior_parser_receipt": {"path": str(a.parse_receipt), "sha256": sha(a.parse_receipt)},
        "binary_contract": "Independent little-endian 4-byte sequential record-marker reader; REAL*8 panel samples; IEMIT/JRAD/IMRG read from the raw FILHDR word sequence.",
        "layer_count": len(rows),
        "sample_count": total,
        "negative_count": negatives,
        "negative_fraction": negatives / total,
        "global_most_negative": global_min,
        "spectral_bin_width_cm-1": a.bin_width,
        "negative_wavenumber_bins": binned,
        "layers": rows,
        "interpretation_limit": "Observed signs are file values. This diagnostic does not decide whether each negative monochromatic contribution is physically admissible or identify a defect.",
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "samples": total, "negative": negatives,
                      "minimum": None if global_min is None else global_min["most_negative_value"],
                      "at_cm-1": None if global_min is None else global_min["most_negative_wavenumber_cm-1"],
                      "layer": None if global_min is None else global_min["layer"]}))


if __name__ == "__main__":
    main()
