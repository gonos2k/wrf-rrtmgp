#!/usr/bin/env python3
"""Independently verify domain/calendar-aware MCICA seeds in SCM captures.

The oracle below is a Python implementation of the published int64 recurrence,
not a call to WRF's Fortran helper. The date is supplied from the run's first
history timestamp because the raw capture contains year/day metadata but no
timestamp string.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


MODULUS = 2_147_483_647
MULTIPLIER = 48_271
DEFAULT_INTEGER_MAX = 2_147_483_647
PHASE_ID = {"LW": 1, "SW": 2}
META_FIELDS = ("MCICA_DOMAIN_ID", "MCICA_YEAR", "MCICA_DAY",
               "MCICA_POLICY_ID", "MCICA_SEED_OVERRIDE")


class ValidationError(RuntimeError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValidationError(message)


def column_seed(domain_id: int, i: int, j: int, year: int, day: int, phase: int) -> int:
    """Pure-Python oracle for the documented 31-bit rolling hash."""
    values = (domain_id, i, j, year, day, phase)
    if any(not isinstance(x, int) or x <= 0 or x > DEFAULT_INTEGER_MAX for x in values[:4]):
        return -1
    if not 1 <= day <= 366 or phase not in (1, 2):
        return -1
    state = 1
    for field in values:
        state = 1 + ((state * MULTIPLIER + field) % (MODULUS - 1))
    return state


def parse_time(value: str) -> tuple[int, int]:
    try:
        dt = datetime.strptime(value, "%Y-%m-%d_%H:%M:%S")
    except ValueError as exc:
        raise ValidationError(f"expected time must be YYYY-MM-DD_hh:mm:ss: {value!r}") from exc
    return dt.year, int(dt.strftime("%j"))


def read_raw(path: Path) -> tuple[str, int, int, int, dict[str, np.ndarray]]:
    lines = path.read_text(encoding="ascii").splitlines()
    require(len(lines) >= 2 and lines[0].strip() == "RRTMGP_RAW_V1",
            f"{path}: expected RRTMGP_RAW_V1")
    header = lines[1].split()
    require(len(header) == 4, f"{path}: malformed phase/index/layer header")
    phase = header[0].upper()
    try:
        i, j, nl = (int(v) for v in header[1:])
    except ValueError as exc:
        raise ValidationError(f"{path}: invalid raw header integers") from exc
    require(phase in PHASE_ID and i > 0 and j > 0 and nl > 0, f"{path}: invalid raw header")
    records: dict[str, np.ndarray] = {}
    pos = 2
    while pos < len(lines):
        if not lines[pos].strip():
            pos += 1
            continue
        line_no = pos + 1
        fields = lines[pos].split()
        pos += 1
        require(len(fields) == 2, f"{path}:{line_no}: malformed record header")
        name = fields[0].upper()
        require(name not in records, f"{path}:{line_no}: duplicate record {name}")
        try:
            count = int(fields[1])
        except ValueError as exc:
            raise ValidationError(f"{path}:{line_no}: invalid record length") from exc
        require(count > 0, f"{path}:{line_no}: nonpositive record length")
        values: list[float] = []
        while len(values) < count and pos < len(lines):
            row = pos + 1
            for token in lines[pos].split():
                try:
                    number = float(token.replace("D", "E").replace("d", "e"))
                except ValueError as exc:
                    raise ValidationError(f"{path}:{row}: invalid {name} number") from exc
                require(np.isfinite(number), f"{path}:{row}: nonfinite {name}")
                values.append(number)
            pos += 1
        require(len(values) == count, f"{path}: truncated {name}")
        records[name] = np.asarray(values, dtype=np.float64)
    return phase, i, j, nl, records


def read_input_header(path: Path) -> tuple[str, int, int]:
    lines = path.read_text(encoding="ascii").splitlines()
    require(len(lines) >= 2 and lines[0].strip().startswith("RRTMGP_REPLAY_V"),
            f"{path}: missing RRTMGP replay header")
    fields = lines[1].split()
    require(len(fields) == 6, f"{path}: malformed replay header")
    phase = fields[0].upper()
    try:
        ncol, nl, seed = int(fields[1]), int(fields[2]), int(fields[4])
    except ValueError as exc:
        raise ValidationError(f"{path}: invalid replay header integer") from exc
    require(phase in PHASE_ID and ncol == 1 and nl > 0, f"{path}: invalid replay phase/dimensions")
    require(0 <= seed <= DEFAULT_INTEGER_MAX, f"{path}: seed outside default INTEGER range")
    return phase, nl, seed


def scalar_integer(records: dict[str, np.ndarray], name: str, path: Path) -> int:
    value = records.get(name)
    require(value is not None and value.shape == (1,), f"{path}: missing/non-scalar {name}")
    f = float(value[0])
    require(f.is_integer(), f"{path}: {name} must be integer-valued, got {f}")
    n = int(f)
    require(0 <= n <= DEFAULT_INTEGER_MAX, f"{path}: {name} outside default INTEGER range")
    return n


def validate_raw(path: Path, input_path: Path, expected_domain: int,
                 expected_time: str) -> dict[str, Any]:
    phase, i, j, nl, rec = read_raw(path)
    in_phase, input_nl, header_seed = read_input_header(input_path)
    require(in_phase == phase, f"{path}: raw/input phase mismatch")
    require(input_nl >= nl, f"{input_path}: input has fewer layers than raw")
    for field in META_FIELDS:
        require(field in rec, f"{path}: missing {field}")
    domain = scalar_integer(rec, "MCICA_DOMAIN_ID", path)
    year = scalar_integer(rec, "MCICA_YEAR", path)
    day = scalar_integer(rec, "MCICA_DAY", path)
    policy = scalar_integer(rec, "MCICA_POLICY_ID", path)
    override = scalar_integer(rec, "MCICA_SEED_OVERRIDE", path)
    exp_year, exp_day = parse_time(expected_time)
    require(domain == expected_domain, f"{path}: domain {domain} != expected {expected_domain}")
    require(year == exp_year, f"{path}: calendar year {year} != expected {exp_year}")
    require(day == exp_day, f"{path}: day-of-year {day} != expected {exp_day}")
    require(1 <= day <= (366 if _is_leap(year) else 365),
            f"{path}: day {day} invalid for Gregorian year {year}")
    require(policy == 1, f"{path}: unsupported MCICA policy id {policy}; expected fixed-day policy 1")
    require(override in (0, 1), f"{path}: seed override flag must be 0 or 1")
    seed_record = rec.get("MCICA_SEED")
    if seed_record is not None:
        require(seed_record.shape == (1,) and seed_record[0].is_integer(),
                f"{path}: MCICA_SEED must be a scalar integer")
        require(int(seed_record[0]) == header_seed,
                f"{path}: MCICA_SEED does not equal sibling input header seed")

    if override == 0:
        require(header_seed > 0, f"{input_path}: computed MCICA seed must be positive")
        expected_seed = column_seed(domain, i, j, year, day, PHASE_ID[phase])
        require(expected_seed > 0, f"{path}: invalid production seed key")
        require(header_seed == expected_seed,
                f"{path}: header seed {header_seed} != independent domain/calendar hash {expected_seed}")
        seed_kind = "computed-domain-calendar-phase-hash"
    else:
        # A custom override intentionally bypasses the standard hash oracle.
        # Zero is valid: the RRTMGP cloud-mask adapter normalizes it to a
        # positive internal stream state while retaining the requested value.
        expected_seed = None
        seed_kind = "custom-override; header seed recorded, not asserted against hash"

    return {
        "phase": phase, "i": i, "j": j, "native_layers": nl, "input_layers": input_nl,
        "metadata": {"domain_id": domain, "year": year, "day_of_year": day,
                     "policy_id": policy, "seed_override": override},
        "expected_time": expected_time,
        "seed_kind": seed_kind, "header_seed": header_seed,
        "independent_expected_seed": expected_seed,
    }


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def self_tests() -> dict[str, bool]:
    vectors = [((1, 1, 1, 2026, 1, 1), 1300300312),
               ((7, 123, 456, 2024, 366, 2), 1388878755),
               ((DEFAULT_INTEGER_MAX,) * 4 + (366, 2), 908371465),
               ((4, 9, 3, 2026, 278, 1), 2041640358)]
    for key, expected in vectors:
        require(column_seed(*key) == expected, f"oracle fixed vector mismatch: {key}")
    invalid = [(0, 1, 1, 2026, 1, 1), (1, 0, 1, 2026, 1, 1),
               (1, 1, -1, 2026, 1, 1), (1, 1, 1, 0, 1, 1),
               (1, 1, 1, 2026, 0, 1), (1, 1, 1, 2026, 367, 1),
               (1, 1, 1, 2026, 1, 0), (1, 1, 1, 2026, 1, 3)]
    require(all(column_seed(*key) == -1 for key in invalid), "invalid oracle key accepted")
    require(parse_time("2024-12-31_23:59:59") == (2024, 366), "leap-year day calculation failed")
    require(parse_time("2023-12-31_00:00:00") == (2023, 365), "common-year day calculation failed")
    require(column_seed(4, 9, 3, 2026, 278, 1) != column_seed(4, 9, 3, 2026, 278, 2),
            "selected LW/SW seed vector collided")
    return {"fixed_vectors_pass": True, "invalid_keys_rejected": True,
            "gregorian_day_vectors_pass": True, "selected_phase_seeds_distinct": True}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--expected-domain-id", type=int, required=True)
    parser.add_argument("--expected-time", required=True,
                        help="actual run's first history timestamp YYYY-MM-DD_hh:mm:ss")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        tests = self_tests()
        require(args.expected_domain_id > 0, "expected domain id must be positive")
        parse_time(args.expected_time)
        results = []
        for phase in ("lw", "sw"):
            raw = args.capture_dir / f"{phase}.raw"
            inp = args.capture_dir / f"{phase}.input"
            if not raw.exists() and not inp.exists():
                continue
            require(raw.is_file() and inp.is_file(), f"{phase}: expected paired .raw and .input")
            check = validate_raw(raw, inp, args.expected_domain_id, args.expected_time)
            check.update({"raw_path": str(raw), "raw_sha256": sha256(raw),
                          "input_path": str(inp), "input_sha256": sha256(inp)})
            results.append(check)
        require(len(results) == 2, "expected exactly one paired LW and SW capture")
        by_phase = {entry["phase"]: entry for entry in results}
        require(set(by_phase) == {"LW", "SW"}, "capture directory must contain LW and SW")
        lw, sw = by_phase["LW"], by_phase["SW"]
        require((lw["i"], lw["j"]) == (sw["i"], sw["j"]),
                "LW and SW raw captures are not the same physical column")
        for name in ("domain_id", "year", "day_of_year", "policy_id", "seed_override"):
            require(lw["metadata"][name] == sw["metadata"][name],
                    f"LW/SW {name} metadata mismatch")
        if lw["metadata"]["seed_override"] == 0:
            require(lw["header_seed"] != sw["header_seed"],
                    "phase-keyed production LW/SW seeds unexpectedly collide for this column")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        receipt = {
            "status": "PASS", "validator": "test_domain_seed_capture.py",
            "expected_domain_id": args.expected_domain_id,
            "expected_time": args.expected_time,
            "calendar_policy": "year plus fixed day-of-year; hour/minute do not alter seed",
            "oracle": "state=1; for [domain,i,j,year,day,phase], state=1+((state*48271+field)%2147483646); phase LW=1, SW=2",
            "monte_carlo_scope": "deterministic engineering hash / repeatability contract only; no stochastic independence or accuracy claim",
            "self_tests": tests, "captures": results,
        }
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "PASS", "output": str(args.output),
                          "seeds": {entry["phase"]: entry["header_seed"] for entry in results},
                          "self_tests": tests}, indent=2))
        return 0
    except (OSError, ValidationError, ValueError, KeyError) as exc:
        print(f"domain seed capture validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
