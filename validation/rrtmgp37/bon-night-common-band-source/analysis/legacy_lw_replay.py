#!/usr/bin/env python3
"""Offline reproduction of the clear-column legacy RRTMG LW rtrnmc path.

This module consumes an RRTMG4_SELECTED_COLUMN_EXPORT_V1 text packet. It does
not call RRTMG, RRTMGP, WRF, or any compiled code. The actual BON packet is not
available yet; synthetic inputs are for parser/arithmetic regression only.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Iterable

import numpy as np

MAGIC = "RRTMG4_SELECTED_COLUMN_EXPORT_V1"
STAGES = ("INPUT", "CLOUD", "GAS", "RESULT")


@dataclass(frozen=True)
class Field:
    stage: str
    name: str
    units: str
    shape: tuple[int, ...]
    values: tuple[float, ...]

    def array(self, dtype=np.float64) -> np.ndarray:
        # The exporter serializes Fortran order: first index varies fastest.
        return np.asarray(self.values, dtype=dtype).reshape(self.shape, order="F")


def read_packet(path: Path) -> dict:
    lines = path.read_text(encoding="ascii").splitlines()
    if not lines or lines[0].strip() != MAGIC:
        raise ValueError("unsupported legacy LW packet magic")
    pos = 1
    meta = {}
    for key in ("phase", "domain", "step", "source_seconds", "i", "j"):
        if pos >= len(lines):
            raise ValueError(f"missing metadata {key}")
        row = lines[pos].split(); pos += 1
        if len(row) != 2 or row[0] != key:
            raise ValueError(f"malformed metadata {key}")
        if key == "phase":
            meta[key] = row[1].upper()
        else:
            value = float(row[1].replace("D", "E").replace("d", "e"))
            if not math.isfinite(value):
                raise ValueError(f"nonfinite metadata {key}")
            meta[key] = value if key == "source_seconds" else int(value)
    if meta["phase"] != "LW":
        raise ValueError("legacy LW replay requires an LW packet")
    if pos >= len(lines) or not lines[pos].startswith("layout ") or "fortran_order_first_index_fastest" not in lines[pos]:
        raise ValueError("unsupported packet array layout")
    pos += 1
    fields: dict[tuple[str, str], Field] = {}
    stages = []
    stage = None
    while pos < len(lines):
        words = lines[pos].split(); pos += 1
        if not words:
            continue
        if words[0] == "stage":
            if len(words) != 2 or words[1] not in STAGES or words[1] in stages:
                raise ValueError("invalid or duplicate stage")
            stage = words[1]; stages.append(stage)
            continue
        if stage is None or len(words) not in (3, 4):
            raise ValueError("malformed field header or field outside stage")
        name, units = words[:2]
        shape = tuple(int(x) for x in words[2:])
        if len(shape) not in (1, 2) or min(shape) <= 0 or math.prod(shape) > 2_000_000:
            raise ValueError(f"invalid field shape for {name}")
        key = (stage, name)
        if key in fields:
            raise ValueError(f"duplicate field {stage}/{name}")
        vals = []
        while len(vals) < math.prod(shape):
            if pos >= len(lines):
                raise ValueError(f"truncated field {stage}/{name}")
            row = lines[pos].split(); pos += 1
            try:
                parsed = [float(x.replace("D", "E").replace("d", "e")) for x in row]
            except ValueError as exc:
                raise ValueError(f"nonnumeric field {stage}/{name}") from exc
            if not parsed or not all(math.isfinite(x) for x in parsed):
                raise ValueError(f"empty or nonfinite field {stage}/{name}")
            vals.extend(parsed)
            if len(vals) > math.prod(shape):
                raise ValueError(f"excess values in {stage}/{name}")
        fields[key] = Field(stage, name, units, shape, tuple(vals))
    if tuple(stages) != STAGES:
        raise ValueError(f"required stage order is {STAGES}, got {stages}")
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "metadata": meta, "fields": fields}


def _get(packet: dict, stage: str, name: str) -> Field:
    try:
        return packet["fields"][(stage, name)]
    except KeyError as exc:
        raise ValueError(f"required packet field missing: {stage}/{name}") from exc


def _f(x) -> np.float32:
    return np.float32(x)


def _add(a, b): return _f(_f(a) + _f(b))
def _sub(a, b): return _f(_f(a) - _f(b))
def _mul(a, b): return _f(_f(a) * _f(b))
def _div(a, b): return _f(_f(a) / _f(b))


def _exact_field(packet, stage: str, name: str, shape: tuple[int, ...], units: str | None = None):
    field = _get(packet, stage, name)
    if field.shape != shape:
        raise ValueError(f"{stage}/{name}: shape {field.shape}, expected {shape}")
    if units is not None and field.units != units:
        raise ValueError(f"{stage}/{name}: units {field.units!r}, expected {units!r}")
    return field.array(np.float32)


def replay_clear(packet: dict) -> dict:
    """Recompute the captured clear-sky rtrnmc recurrence in float32 order."""
    required_cloud = ["MCICA_MASK", "RRTMG_INPUT_CLOUD_MASK"]
    for name in required_cloud:
        f = _get(packet, "CLOUD", name)
        mask = f.array(np.float32)
        if not np.all(mask == _f(0)):
            raise ValueError(f"clear-only replay refuses nonzero cloud mask {name}")

    band_record = _get(packet, "CLOUD", "GPOINT_TO_BAND").array(np.float64).reshape(-1)
    if not np.all(np.isfinite(band_record)) or not np.all(band_record == np.floor(band_record)):
        raise ValueError("invalid GPOINT_TO_BAND values")
    bands = band_record.astype(np.int64)
    if np.any(bands < 1):
        raise ValueError("invalid GPOINT_TO_BAND values")
    nband = _get(packet, "INPUT", "SOLVER_SEMISS").shape[0]
    nlay = _get(packet, "INPUT", "SOLVER_PZ").shape[0] - 1
    ngpt = bands.size
    if nband <= 0 or nlay <= 0 or ngpt <= 0 or np.any(bands > nband):
        raise ValueError("invalid band/g-point/layer dimensions")
    if not np.array_equal(np.unique(bands), np.arange(1, nband + 1)):
        raise ValueError("g-point mapping must cover each band in contiguous band order")
    if np.any(np.diff(bands) < 0):
        raise ValueError("g-point mapping is not in source band order")

    # rtrnmc emits these before the caller writes the RESULT stage marker, so
    # they belong to the packet's GAS section despite describing solver state.
    planck_layer = _exact_field(packet, "GAS", "RTE_PLANCK_LAYER_NATIVE", (nband, nlay))
    planck_level = _exact_field(packet, "GAS", "RTE_PLANCK_LEVEL_NATIVE", (nband, nlay + 1))
    planck_surface = _exact_field(packet, "GAS", "RTE_PLANCK_SURFACE_NATIVE", (nband,))
    fractions = _exact_field(packet, "GAS", "RTE_PLANCK_FRACTIONS", (ngpt, nlay))
    taut = _exact_field(packet, "GAS", "TAUTOTAL_GAS_PLUS_AEROSOL_CLOUD_EXCLUDED", (ngpt, nlay))
    secdiff = _exact_field(packet, "GAS", "RTE_SECDIFF", (nband,))
    delwave = _exact_field(packet, "GAS", "RTE_DELWAVE", (nband,))
    scalars = {}
    for name in ("RTE_WTDIFF", "RTE_REC_6", "RTE_FLUXFAC", "RTE_HEATFAC", "RTE_TBLINT", "RTE_BPADE"):
        f = _get(packet, "GAS", name)
        if f.shape != (1,):
            raise ValueError(f"INPUT/{name}: expected scalar vector")
        scalars[name] = _f(f.values[0])
    bounds_record = _get(packet, "GAS", "RTE_TABLE_BOUNDS").array(np.float64).reshape(-1)
    if bounds_record.size != 2 or not np.all(bounds_record == np.floor(bounds_record)):
        raise ValueError("invalid Fortran lookup-table bounds")
    bounds = bounds_record.astype(np.int64)
    if bounds[1] < bounds[0]:
        raise ValueError("invalid Fortran lookup-table bounds")
    lo, hi = int(bounds[0]), int(bounds[1])
    tau_table = _get(packet, "GAS", "RTE_TAU_TABLE").array(np.float32).reshape(-1)
    exp_table = _get(packet, "GAS", "RTE_EXP_TABLE").array(np.float32).reshape(-1)
    tfn_table = _get(packet, "GAS", "RTE_TFN_TABLE").array(np.float32).reshape(-1)
    if any(len(t) != hi - lo + 1 for t in (tau_table, exp_table, tfn_table)):
        raise ValueError("lookup table lengths disagree with recorded bounds")
    pz = _exact_field(packet, "INPUT", "SOLVER_PZ", (nlay + 1,))
    semiss = _exact_field(packet, "INPUT", "SOLVER_SEMISS", (nband,))
    band_control = _get(packet, "GAS", "RTE_BAND_START_END_IOUT").array(np.float64).reshape(-1)
    if band_control.size != 3 or not np.all(band_control == np.floor(band_control)):
        raise ValueError("invalid RTE_BAND_START_END_IOUT")
    if int(band_control[0]) != 1 or int(band_control[1]) != nband:
        raise ValueError("source reproduction currently requires a complete 1..nband sweep")

    # rtrnmc uses each g-point in increasing order, within each increasing band.
    raw_up = np.zeros((nband, nlay + 1), dtype=np.float32)
    raw_dn = np.zeros_like(raw_up)
    raw_up_clear = np.zeros_like(raw_up)
    raw_dn_clear = np.zeros_like(raw_up)
    broadband_up = np.zeros(nlay + 1, dtype=np.float32)
    broadband_dn = np.zeros(nlay + 1, dtype=np.float32)
    wt = scalars["RTE_WTDIFF"]
    rec6 = scalars["RTE_REC_6"]
    tblint = scalars["RTE_TBLINT"]
    bpade = scalars["RTE_BPADE"]

    for b in range(1, nband + 1):
        gp_indices = np.flatnonzero(bands == b)
        urad = np.zeros(nlay + 1, dtype=np.float32)
        drad = np.zeros(nlay + 1, dtype=np.float32)
        for gi in gp_indices:
            atrans = np.zeros(nlay, dtype=np.float32)
            bbugas = np.zeros(nlay, dtype=np.float32)
            radld = _f(0)
            for lev in range(nlay, 0, -1):
                li = lev - 1
                frac = fractions[gi, li]
                blay = planck_layer[b - 1, li]
                dplankup = _sub(planck_level[b - 1, lev], blay)
                dplankdn = _sub(planck_level[b - 1, lev - 1], blay)
                odepth = _mul(secdiff[b - 1], taut[gi, li])
                if odepth < _f(0):
                    odepth = _f(0)
                if odepth <= _f(0.06):
                    atrans[li] = _sub(odepth, _mul(_mul(_f(0.5), odepth), odepth))
                    source_factor = _mul(rec6, odepth)
                else:
                    denominator = _add(bpade, odepth)
                    tblind = _div(odepth, denominator)
                    index_value = _add(_mul(tblint, tblind), _f(0.5))
                    itr = int(index_value)  # Fortran INT truncates toward zero.
                    if not lo <= itr <= hi:
                        raise ValueError(f"lookup index {itr} outside recorded bounds [{lo},{hi}]")
                    ix = itr - lo
                    transc = exp_table[ix]
                    atrans[li] = _sub(_f(1), transc)
                    source_factor = tfn_table[ix]
                bbd = _mul(frac, _add(blay, _mul(dplankdn, source_factor)))
                bbugas[li] = _mul(frac, _add(blay, _mul(dplankup, source_factor)))
                radld = _add(radld, _mul(_sub(bbd, radld), atrans[li]))
                drad[lev - 1] = _add(drad[lev - 1], radld)

            # Clear path only: surface source already includes emissivity treatment.
            rad0 = _mul(fractions[gi, 0], planck_surface[b - 1])
            reflect = _sub(_f(1), semiss[b - 1])
            radlu = _add(rad0, _mul(reflect, radld))
            urad[0] = _add(urad[0], radlu)
            for lev in range(1, nlay + 1):
                radlu = _add(radlu, _mul(_sub(bbugas[lev - 1], radlu), atrans[lev - 1]))
                urad[lev] = _add(urad[lev], radlu)
        raw_up[b - 1, :] = np.asarray([_mul(x, wt) for x in urad], dtype=np.float32)
        raw_dn[b - 1, :] = np.asarray([_mul(x, wt) for x in drad], dtype=np.float32)
        raw_up_clear[b - 1, :] = raw_up[b - 1, :]
        raw_dn_clear[b - 1, :] = raw_dn[b - 1, :]
        for lev in range(nlay + 1):
            broadband_up[lev] = _add(broadband_up[lev], _mul(raw_up[b - 1, lev], delwave[b - 1]))
            broadband_dn[lev] = _add(broadband_dn[lev], _mul(raw_dn[b - 1, lev], delwave[b - 1]))

    fluxfac = scalars["RTE_FLUXFAC"]
    up = np.asarray([_mul(x, fluxfac) for x in broadband_up], dtype=np.float32)
    dn = np.asarray([_mul(x, fluxfac) for x in broadband_dn], dtype=np.float32)
    net = np.asarray([_sub(u, d) for u, d in zip(up, dn)], dtype=np.float32)
    heatfac = scalars["RTE_HEATFAC"]
    heating = np.zeros(nlay + 1, dtype=np.float32)
    for lev in range(1, nlay + 1):
        dp = _sub(pz[lev - 1], pz[lev])
        if dp == _f(0):
            raise ValueError("zero pressure thickness in SOLVER_PZ")
        # Keep the source expression's left-to-right real32 rounding:
        # heatfac * (net(l)-net(l+1)) / (pz(l)-pz(l+1)).
        heating[lev - 1] = _div(_mul(heatfac, _sub(net[lev - 1], net[lev])), dp)

    return {"band_up": raw_up, "band_dn": raw_dn,
            "band_up_clear": raw_up_clear, "band_dn_clear": raw_dn_clear,
            "up": up, "down": dn, "net": net, "heating": heating,
            "up_clear": up.copy(), "down_clear": dn.copy(), "net_clear": net.copy(),
            "heating_clear": heating.copy()}


def compare_packet(packet: dict, replay: dict) -> dict:
    names = {"band_up": ("RTE_BAND_UP_NATIVE", "GAS"),
             "band_dn": ("RTE_BAND_DN_NATIVE", "GAS"),
             "band_up_clear": ("RTE_BAND_UP_CLEAR_NATIVE", "GAS"),
             "band_dn_clear": ("RTE_BAND_DN_CLEAR_NATIVE", "GAS"),
             "up": ("UP_FLUX", "RESULT"), "down": ("DOWN_FLUX", "RESULT"),
             "net": ("NET_FLUX", "RESULT"), "heating": ("HEATING", "RESULT")}
    names.update({"up_clear": ("UP_CLEAR_FLUX", "RESULT"),
                  "down_clear": ("DOWN_CLEAR_FLUX", "RESULT"),
                  "net_clear": ("NET_CLEAR_FLUX", "RESULT"),
                  "heating_clear": ("HEATING_CLEAR", "RESULT")})
    rows = []
    for key, (field_name, stage) in names.items():
        expected = _get(packet, stage, field_name).array(np.float32)
        actual = replay[key]
        if expected.shape != actual.shape:
            raise ValueError(f"{stage}/{field_name}: replay shape mismatch")
        delta = np.abs(actual.astype(np.float64) - expected.astype(np.float64))
        rows.append({"quantity": key, "field": field_name,
                     "bitwise_equal_float32": bool(np.array_equal(actual.view(np.uint32), expected.view(np.uint32))),
                     "max_abs_difference_native_units": float(delta.max(initial=0.0)),
                     "mismatch_count": int(np.count_nonzero(actual.view(np.uint32) != expected.view(np.uint32)))})
    return {"comparisons": rows,
            "scope": "clear-only recurrence reproduction; exact equality is reported, not relaxed",
            "physical_accuracy_claim": False}


def run(packet_path: Path) -> dict:
    packet = read_packet(packet_path)
    replay = replay_clear(packet)
    comparison = compare_packet(packet, replay)
    mismatch_count = sum(row["mismatch_count"] for row in comparison["comparisons"])
    return {"status": "REPLAY_MATCH" if mismatch_count == 0 else "REPLAY_MISMATCH",
            "mismatch_count": mismatch_count,
            "packet": {"path": packet["path"], "sha256": packet["sha256"], "metadata": packet["metadata"]},
            **comparison}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--packet", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    result = run(args.packet)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(json.dumps({"status": result["status"], "mismatch_count": result["mismatch_count"],
                      "packet_sha256": result["packet"]["sha256"],
                      "output": str(args.output)}))
    if result["status"] != "REPLAY_MATCH":
        sys.exit(1)


if __name__ == "__main__":
    main()
