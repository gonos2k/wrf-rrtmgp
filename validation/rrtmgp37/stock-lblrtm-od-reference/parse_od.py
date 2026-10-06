#!/usr/bin/env python3
"""Read stock LBLRTM GNU-dbl layer optical-depth files (no dependencies)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
from pathlib import Path

WORD = 8
MARKER = 4
FILHDR_WORDS = 177
PNLHDR_WORDS = 4
END_WORDS = 6


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def records(path: Path):
    raw = path.read_bytes()
    pos = 0
    while pos < len(raw):
        if pos + MARKER > len(raw):
            raise ValueError(f"{path}: truncated leading record marker at {pos}")
        n = struct.unpack_from("<i", raw, pos)[0]
        pos += MARKER
        if n < 0 or pos + n + MARKER > len(raw):
            raise ValueError(f"{path}: invalid record length {n} at {pos-MARKER}")
        payload = raw[pos : pos + n]
        pos += n
        end = struct.unpack_from("<i", raw, pos)[0]
        pos += MARKER
        if end != n:
            raise ValueError(f"{path}: trailing marker {end} != leading {n}")
        yield payload
    if pos != len(raw):
        raise ValueError(f"{path}: trailing bytes")


def doubles(payload: bytes, expected: int, label: str) -> list[float]:
    if len(payload) != expected * WORD:
        raise ValueError(f"{label}: got {len(payload)} bytes; expected {expected*WORD}")
    return list(struct.unpack("<" + "d" * expected, payload))


def ints(payload: bytes, expected: int, label: str) -> list[int]:
    if len(payload) != expected * WORD:
        raise ValueError(f"{label}: got {len(payload)} bytes; expected {expected*WORD}")
    return list(struct.unpack("<" + "q" * expected, payload))


def deck_layer_state(deck: Path) -> list[tuple[float, float, float, float]]:
    lines = deck.read_text().splitlines()
    if len(lines) < 4:
        raise ValueError("TAPE5 is too short to contain layer records")
    out = []
    # The first two fields of each layer's first record are PAVE and TAVE;
    # retain their printed decimal values as the comparison reference.
    for index, line in enumerate(lines[4:], start=4):
        if (index - 4) % 4 != 0:
            continue
        toks = line.split()
        if len(toks) >= 2 and re.fullmatch(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[EeDd][+-]?\d+)?", toks[0]):
            try:
                p = float(toks[0].replace("D", "E").replace("d", "e"))
                t = float(toks[1].replace("D", "E").replace("d", "e"))
            except ValueError:
                continue
            if p > 0 and 100 < t < 400:
                out.append((p, t, decimals_half_unit(toks[0]), decimals_half_unit(toks[1])))
    return out


def decimals_half_unit(token: str) -> float:
    """Half a unit of the last printed decimal, including exponent."""
    s = token.lower().replace("d", "e")
    mantissa, _, exp = s.partition("e")
    exponent = int(exp) if exp else 0
    decimals = len(mantissa.partition(".")[2])
    return 0.5 * 10.0 ** (exponent - decimals)


def parse_layer(path: Path, expected_layer: int, deck_pt: tuple[float, float, float, float] | None):
    it = iter(records(path))
    try:
        head = next(it)
    except StopIteration:
        raise ValueError(f"{path}: empty output")
    hdr = doubles(head, FILHDR_WORDS, "FILHDR")
    raw = head
    # FILHDR layout is the COMMON /FILHDR/ sequence in oprop.f90.
    layer = ints(raw[165 * WORD : 166 * WORD], 1, "LAYER")[0]
    pave, tave = hdr[11], hdr[12]
    # Zero-based offsets from the declared /FILHDR/ sequence.
    pzl, pzu, tzl, tzu, wbroad, dvh, v1h, v2h = hdr[137:145]
    if layer != expected_layer:
        raise ValueError(f"{path}: header layer={layer}, expected {expected_layer}")
    real_indices = [10, 11, 12, *range(73, 77), *range(77, 147), 166]
    if not all(math.isfinite(hdr[i]) for i in real_indices):
        raise ValueError(f"{path}: nonfinite REAL field in FILHDR")
    panels = []
    data_values = []
    terminated = False
    while True:
        try:
            rec = next(it)
        except StopIteration:
            break
        if len(rec) == END_WORDS * WORD and ints(rec, END_WORDS, "ENDFIL") == [-99] * END_WORDS:
            terminated = True
            break
        if len(rec) != PNLHDR_WORDS * WORD:
            raise ValueError(f"{path}: unexpected record length {len(rec)} where PNLHDR expected")
        # PNLHDR is V1P,V2P,DVP,NLIM; the fourth word is INTEGER*8.
        v1p, v2p, dvp = struct.unpack_from("<3d", rec, 0)
        nlim = struct.unpack_from("<q", rec, 3 * WORD)[0]
        if nlim <= 0:
            raise ValueError(f"{path}: invalid panel NLIM={nlim}")
        try:
            drec = next(it)
        except StopIteration:
            raise ValueError(f"{path}: panel header lacks its data record")
        if len(drec) != nlim * WORD:
            raise ValueError(f"{path}: panel data bytes={len(drec)}, NLIM implies {nlim*WORD}")
        npts = nlim
        vals = list(struct.unpack("<" + "d" * npts, drec))
        if not all(math.isfinite(v) for v in vals):
            raise ValueError(f"{path}: nonfinite optical-depth data")
        panels.append({"v1": v1p, "v2": v2p, "dv": dvp, "n": npts})
        data_values.extend(vals)
    if not terminated:
        raise ValueError(f"{path}: missing six-integer ENDFIL record")
    try:
        extra = next(it)
        raise ValueError(f"{path}: records follow ENDFIL (first extra length {len(extra)})")
    except StopIteration:
        pass
    if deck_pt:
        # Input fields are decimal text, while output header values are full
        # binary REAL*8. The tolerance is one half-unit of each printed field.
        p_tol, t_tol = deck_pt[2], deck_pt[3]
        if abs(pave - deck_pt[0]) > p_tol or abs(tave - deck_pt[1]) > t_tol:
            raise ValueError(f"{path}: PAVE/TAVE outside input text rounding interval")
    if not panels:
        raise ValueError(f"{path}: no optical-depth panels")
    for left, right in zip(panels, panels[1:]):
        if not math.isclose(left["v2"] + left["dv"], right["v1"], rel_tol=0.0, abs_tol=max(1e-9, abs(left["dv"]) * 1e-7)):
            raise ValueError(f"{path}: noncontiguous panels {left} then {right}")
    negative = sum(v < 0.0 for v in data_values)
    return {
        "file": path.name,
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
        "layer": layer,
        "PAVE": pave,
        "TAVE": tave,
        "PZL_PZU_TZL_TZU_WBROAD_DV_V1_V2": [pzl, pzu, tzl, tzu, wbroad, dvh, v1h, v2h],
        "panels": panels,
        "sample_count": len(data_values),
        "value_min": min(data_values),
        "value_max": max(data_values),
        "negative_count": negative,
        "negative_min": min((x for x in data_values if x < 0.0), default=None),
        "finite": True,
        "all_nonnegative": negative == 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--deck", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--layers", type=int, default=45)
    args = ap.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")
    deck_layers = deck_layer_state(args.deck)
    if len(deck_layers) != args.layers:
        raise ValueError(f"deck layer-state rows={len(deck_layers)}, expected {args.layers}")
    rows = []
    for k in range(1, args.layers + 1):
        path = args.run_dir / f"ODdeflt_{k:03d}"
        if not path.is_file():
            raise FileNotFoundError(path)
        rows.append(parse_layer(path, k, deck_layers[k - 1]))
    extra = sorted(p.name for p in args.run_dir.glob("ODdeflt_*") if p.name not in {r["file"] for r in rows})
    if extra:
        raise ValueError(f"unexpected ODdeflt files: {extra}")
    result = {
        "status": "PARSED_DIAGNOSTIC",
        "scope": "Stock LBLRTM per-layer monochromatic optical-depth products only; no flux/accuracy inference.",
        "record_layout": {"byte_order": "little", "record_marker_bytes": 4, "numeric_word_bytes": 8, "FILHDR_words": FILHDR_WORDS, "PNLHDR_words": PNLHDR_WORDS, "data": "REAL*8 vector, length from panel header NLIM", "ENDFIL": "six INTEGER*8 values -99"},
        "deck": {"path": str(args.deck), "sha256": sha256(args.deck), "layer_records": len(deck_layers)},
        "run_dir": str(args.run_dir),
        "layer_file_count": len(rows),
        "layers": rows,
        "sign_check": "negative values are counted and reported; they are not silently clipped or assigned a tolerance.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "layers": len(rows), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
