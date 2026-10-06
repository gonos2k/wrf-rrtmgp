#!/usr/bin/env python3
"""Join saved post-UDM radius packets to later LW/SW raw captures (stdlib only).

This checks a diagnostic state-transfer contract, not a radiation PSD or physics
accuracy contract. --self-test uses manufactured files and runs no WRF code.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest


RADIUS_FIELDS = ("SOURCE_RE_CLOUD", "SOURCE_RE_ICE", "SOURCE_RE_SNOW")
PRODUCER_VECTORS = ("SOURCE_T", "SOURCE_QC", "SOURCE_QI", "SOURCE_QS",
                    "SOURCE_QNC", "SOURCE_RHO", *RADIUS_FIELDS, "UDM_CF_USED")
PRODUCER_SCALARS = ("UDM_CF_STEP", "UDM_CF_TOP", "QMIN", "T0C",
                    "RHO_WATER", "RHO_SNOW", "SOURCE_TIME_PRESENT")
CONSUMER_VECTORS = ("SOURCE_T", "SOURCE_QC", "SOURCE_QI", "SOURCE_QS",
                    "SOURCE_QNC", "RHO", *RADIUS_FIELDS)
PRODUCER_NAME = re.compile(r"udm_radius_d(\d+)_i(\d+)_j(\d+)_step(\d+)\.raw\Z")
CONSUMER_NAME = re.compile(r"(lw|sw)(?:_\d+)?\.raw\Z", re.IGNORECASE)
FIELD_NAME = re.compile(r"[A-Z][A-Z0-9_]*\Z")
INTEGER = re.compile(r"[0-9]+\Z")


@dataclass
class Packet:
    path: Path
    header: tuple
    fields: dict[str, tuple[float, ...]]
    sha256: str
    size: int

    def pin(self) -> dict:
        return {"path": str(self.path.resolve()), "sha256": self.sha256,
                "size_bytes": self.size}


def fail(message: str) -> None:
    raise ValueError(message)


def integer(token: str, label: str, minimum: int = 0) -> int:
    if not INTEGER.fullmatch(token) or int(token) < minimum:
        fail(f"{label}: invalid integer {token!r}")
    return int(token)


def read_records(lines: list[str], label: str) -> dict[str, tuple[float, ...]]:
    fields = {}
    cursor = 0
    while cursor < len(lines):
        words = lines[cursor].split()
        cursor += 1
        if len(words) != 2 or not FIELD_NAME.fullmatch(words[0]):
            fail(f"{label}: malformed record header")
        name = words[0]
        if name in fields:
            fail(f"{label}: duplicate field {name}")
        count = integer(words[1], f"{label}/{name} size", 1)
        if count > 1_000_000:
            fail(f"{label}/{name}: excessive size")
        values = []
        while len(values) < count:
            if cursor >= len(lines):
                fail(f"{label}/{name}: truncated values")
            tokens = lines[cursor].split()
            cursor += 1
            if not tokens:
                fail(f"{label}/{name}: blank numeric record")
            try:
                values.extend(float(x.replace("D", "E").replace("d", "e")) for x in tokens)
            except ValueError:
                fail(f"{label}/{name}: malformed numeric values")
            if len(values) > count or not all(math.isfinite(x) for x in values):
                fail(f"{label}/{name}: excess or nonfinite values")
        fields[name] = tuple(values)
    return fields


def scalar(p: Packet, name: str, integral: bool = False) -> float | int:
    if name not in p.fields or len(p.fields[name]) != 1:
        fail(f"{p.path.name}: missing/non-scalar {name}")
    x = p.fields[name][0]
    if integral and not x.is_integer():
        fail(f"{p.path.name}: nonintegral {name}")
    return int(x) if integral else x


def vectors(p: Packet, names: tuple[str, ...], nl: int) -> None:
    for name in names:
        if name not in p.fields or len(p.fields[name]) != nl:
            fail(f"{p.path.name}: missing/wrong-size {name} (expected {nl})")


def parse_packet(path: Path) -> Packet:
    data = path.read_bytes()
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError:
        fail(f"{path.name}: non-ASCII packet")
    if len(lines) < 2:
        fail(f"{path.name}: missing header")
    words = lines[1].split()
    producer = PRODUCER_NAME.fullmatch(path.name)
    consumer = CONSUMER_NAME.fullmatch(path.name)
    if producer:
        if lines[0] != "RRTMGP_UDM_RADIUS_V1" or len(words) != 6:
            fail(f"{path.name}: wrong producer magic/header")
        domain, step, i, j, kts, kte = [integer(x, path.name) for x in words]
        if min(domain, i, j, kts) < 1 or kte < kts:
            fail(f"{path.name}: invalid producer identity/bounds")
        if (domain, i, j, step) != tuple(map(int, producer.groups())):
            fail(f"{path.name}: filename/header identity mismatch")
        header = (domain, step, i, j, kts, kte)
    elif consumer:
        if lines[0] != "RRTMGP_RAW_V1" or len(words) != 4:
            fail(f"{path.name}: wrong radiation magic/header")
        phase = words[0]
        if phase not in ("LW", "SW") or phase != consumer.group(1).upper():
            fail(f"{path.name}: filename/header phase mismatch")
        i, j, nl = [integer(x, path.name, 1) for x in words[1:]]
        header = (phase, i, j, nl)
    else:
        fail(f"{path.name}: unrecognized raw packet name")
    p = Packet(path, header, read_records(lines[2:], path.name),
               hashlib.sha256(data).hexdigest(), len(data))
    if producer:
        nl = kte - kts + 1
        vectors(p, PRODUCER_VECTORS, nl)
        for name in PRODUCER_SCALARS:
            scalar(p, name)
        permitted = set(PRODUCER_VECTORS + PRODUCER_SCALARS + ("SOURCE_TIME_SECONDS",))
        if set(p.fields) - permitted:
            fail(f"{path.name}: unknown V1 producer fields")
        cf_step, cf_top = scalar(p, "UDM_CF_STEP", True), scalar(p, "UDM_CF_TOP", True)
        # CF top is a native layer tag, not necessarily a vector offset.
        # Keep the source's unavailable (-1) sentinel distinct from identity.
        if cf_step < -1 or not -1 <= cf_top <= kte:
            fail(f"{path.name}: invalid CF step/top metadata")
        present = scalar(p, "SOURCE_TIME_PRESENT", True)
        if present not in (0, 1) or ("SOURCE_TIME_SECONDS" in p.fields) != bool(present):
            fail(f"{path.name}: inconsistent time-present metadata")
        if present and scalar(p, "SOURCE_TIME_SECONDS") < 0:
            fail(f"{path.name}: negative source time")
    else:
        vectors(p, CONSUMER_VECTORS, nl)
        if scalar(p, "MCICA_DOMAIN_ID", True) < 1 or scalar(p, "RADIATION_STEP", True) < 0:
            fail(f"{path.name}: invalid radiation domain/step")
        if scalar(p, "SOURCE_QNC_PRESENT", True) != 1:
            fail(f"{path.name}: native number concentration unavailable")
        if scalar(p, "SOURCE_TIME_SECONDS") < 0:
            fail(f"{path.name}: negative radiation time")
        if "MP_PHYSICS" in p.fields and scalar(p, "MP_PHYSICS", True) != 27:
            fail(f"{path.name}: consumer does not identify UDM27")
    return p


def bits(values: tuple[float, ...]) -> bytes:
    return struct.pack(f">{len(values)}d", *values)


def liquid_formula(p: Packet) -> dict:
    """Conditional ideal formula from saved post-UDM state; no compiled claim."""
    rows = []
    water = scalar(p, "RHO_WATER")
    if water <= 0:
        fail(f"{p.path.name}: liquid formula requires positive RHO_WATER")
    for offset, (qc, nc, rho, radius) in enumerate(zip(
            p.fields["SOURCE_QC"], p.fields["SOURCE_QNC"],
            p.fields["SOURCE_RHO"], p.fields["SOURCE_RE_CLOUD"])):
        active = qc * rho > 1.e-12 and nc * rho > 1.e-6 and nc > 0 and rho > 0
        row = {"native_k": p.header[4] + offset, "guard_active": active,
               "captured_radius_m": radius}
        if active:
            unbounded = 0.5 / (math.pi * water * nc / (6. * qc * rho)) ** (1. / 3.)
            bounded = min(50.e-6, max(2.51e-6, unbounded))
            row.update(ideal_unbounded_radius_m=unbounded, ideal_bounded_radius_m=bounded,
                       captured_minus_ideal_m=radius - bounded,
                       ideal_bound_active=unbounded != bounded)
        rows.append(row)
    return {"status": "CONDITIONAL_REAL64_MATH_ONLY", "rows": rows,
            "formula": "0.5 / (pi*rho_water*nc/(6*qc*rho))**(1/3), bounded 2.51e-6..50e-6 m",
            "limits": "Declared constants/default-real operation rounding may differ. No compiler-bit identity, Nc unit resolution or radiation PSD equivalence is claimed."}


def inspect(capture_dir: Path, require_matched: bool = False,
            include_liquid_formula: bool = False) -> dict:
    if not capture_dir.is_dir():
        fail(f"capture directory missing: {capture_dir}")
    packets = [parse_packet(p) for p in sorted(capture_dir.glob("*.raw"))]
    producers = {}
    consumers = []
    consumer_keys = set()
    for p in packets:
        if len(p.header) == 6:
            domain, step, i, j, _, _ = p.header
            key = (domain, i, j)
            if step in producers.setdefault(key, {}):
                fail(f"duplicate producer identity: {key} step {step}")
            producers[key][step] = p
        else:
            phase, i, j, _ = p.header
            identity = (scalar(p, "MCICA_DOMAIN_ID", True), i, j,
                        scalar(p, "RADIATION_STEP", True), phase)
            if identity in consumer_keys:
                fail(f"duplicate radiation identity: {identity}")
            consumer_keys.add(identity)
            consumers.append(p)
    joins = []
    for p in consumers:
        phase, i, j, nl = p.header
        domain, step = scalar(p, "MCICA_DOMAIN_ID", True), scalar(p, "RADIATION_STEP", True)
        by_step = producers.get((domain, i, j), {})
        steps = sorted(by_step)
        position = bisect_left(steps, step) - 1
        row = {"phase": phase, "domain": domain, "i": i, "j": j,
               "radiation_step": step, "radiation_seconds": scalar(p, "SOURCE_TIME_SECONDS"),
               "consumer": p.pin()}
        if position < 0:
            row.update(status="NOT_RUN_INIT", reason="No earlier producer for this domain/column; initial/restart radii are not independently stage-proven.")
            joins.append(row)
            continue
        prev = by_step[steps[position]]
        if prev.header[5] - prev.header[4] + 1 != nl:
            fail(f"{p.path.name}: producer/consumer native-level count mismatch")
        for name in RADIUS_FIELDS:
            if bits(prev.fields[name]) != bits(p.fields[name]):
                fail(f"{p.path.name}: latest producer radius mismatch {name}")
        producer_time = (scalar(prev, "SOURCE_TIME_SECONDS")
                         if scalar(prev, "SOURCE_TIME_PRESENT", True) else None)
        if producer_time is not None and producer_time > row["radiation_seconds"]:
            fail(f"{p.path.name}: producer physical time is after radiation time")
        if "UDM_CF_SOURCE_STEP" in p.fields:
            if scalar(p, "UDM_CF_SOURCE_STEP", True) != scalar(prev, "UDM_CF_STEP", True):
                fail(f"{p.path.name}: consumer CF tag differs from latest producer CF tag")
        row.update(status="MATCHED_RADIUS_TRANSFER", producer=prev.pin(),
                   producer_step=prev.header[1], step_lag=step-prev.header[1],
                   producer_seconds=producer_time,
                   time_lag_seconds=(row["radiation_seconds"]-producer_time
                                     if producer_time is not None else None),
                   latest_earlier_producer=True, all_three_radius_arrays_binary64_exact=True,
                   native_k_bounds=list(prev.header[4:6]),
                   current_state_changes_vs_producer={
                       name: sum(bits((a,)) != bits((b,)) for a, b in zip(prev.fields[name], p.fields[name]))
                       for name in ("SOURCE_QC", "SOURCE_QI", "SOURCE_QS", "SOURCE_QNC", "SOURCE_T")},
                   current_rho_changed_layers=sum(bits((a,)) != bits((b,)) for a, b in
                                                 zip(prev.fields["SOURCE_RHO"], p.fields["RHO"])))
        joins.append(row)
    matched = sum(x["status"] == "MATCHED_RADIUS_TRANSFER" for x in joins)
    if require_matched and matched < 1:
        fail("--require-matched: no actual matched producer/consumer pair")
    # Bind the records consumed by this check; reject concurrent capture edits.
    for p in packets:
        if hashlib.sha256(p.path.read_bytes()).hexdigest() != p.sha256:
            fail(f"{p.path.name}: changed during inspection")
    if sorted(p.name for p in capture_dir.glob("*.raw")) != sorted(p.path.name for p in packets):
        fail("raw packet roster changed during inspection")
    report = {"schema": "UDM_RADIUS_STAGE_JOIN_V1", "status": "SAVED_STAGE_CONTRACT_CHECKED",
              "scope": "Saved diagnostic transfer only; manufactured fixtures do not establish physics accuracy.",
              "producer_packets": sum(len(x) for x in producers.values()),
              "radiation_packets": len(consumers), "matched_consumers": matched,
              "bootstrap_consumers": len(consumers)-matched, "joins": joins,
              "producer_pins": [p.pin() for p in packets if len(p.header) == 6],
              "physical_gates_closed": [], "model_or_solver_invocations": 0}
    if include_liquid_formula:
        report["conditional_liquid_formula"] = [
            {"producer": p.pin(), **liquid_formula(p)} for p in packets if len(p.header) == 6]
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture-dir", type=Path)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--require-matched", action="store_true")
    ap.add_argument("--liquid-formula", action="store_true")
    ap.add_argument("--self-test", action="store_true", help="manufactured-file controls only")
    args = ap.parse_args()
    if args.self_test:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(StageControls))
        return 0 if result.wasSuccessful() else 1
    if args.capture_dir is None or args.output is None:
        ap.error("--capture-dir and --output are required outside --self-test")
    try:
        report = inspect(args.capture_dir, args.require_matched, args.liquid_formula)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        print(json.dumps({"status": report["status"], "matched_consumers": report["matched_consumers"],
                          "bootstrap_consumers": report["bootstrap_consumers"], "output": str(args.output)}))
        return 0
    except (OSError, ValueError, OverflowError) as exc:
        print(f"UDM_RADIUS_STAGE_ERROR: {exc}", file=sys.stderr)
        return 1


class StageControls(unittest.TestCase):
    """Manufactured packets, independent of post-WRF callback execution."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="udm-radius-stage-")
        self.directory = Path(self.temp.name)
        self.fields = {n: [0., 0.] for n in PRODUCER_VECTORS}
        self.fields.update(SOURCE_T=[250., 251.], SOURCE_RHO=[1., 1.], SOURCE_QC=[1.e-3, 2.e-3],
                           SOURCE_QNC=[1.e8, 2.e8], SOURCE_RE_CLOUD=[8.e-6, 9.e-6],
                           SOURCE_RE_ICE=[2.e-5, 3.e-5], SOURCE_RE_SNOW=[4.e-5, 5.e-5],
                           UDM_CF_USED=[1., 1.])
        self.fields.update({n: [v] for n, v in {
            "UDM_CF_STEP": 10, "UDM_CF_TOP": 2, "QMIN": 1.e-12, "T0C": 273.15,
            "RHO_WATER": 1000., "RHO_SNOW": 100., "SOURCE_TIME_PRESENT": 1,
            "SOURCE_TIME_SECONDS": 600.}.items()})

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, magic, header, fields):
        p = self.directory/name
        text = [magic, header]
        for key, values in fields.items():
            text.append(f"{key} {len(values)}")
            text.extend(f"{x:.16E}" for x in values)
        p.write_text("\n".join(text)+"\n", encoding="ascii")
        return p

    def producer(self, step=10):
        fields = {k: list(v) for k, v in self.fields.items()}
        fields["UDM_CF_STEP"] = [step]
        fields["SOURCE_TIME_SECONDS"] = [step*60.]
        return self.write(f"udm_radius_d1_i2_j3_step{step}.raw", "RRTMGP_UDM_RADIUS_V1",
                          f"1 {step} 2 3 1 2", fields)

    def consumer(self, phase="LW", step=11):
        fields = {n: list(self.fields[n]) for n in CONSUMER_VECTORS if n != "RHO"}
        fields["RHO"] = list(self.fields["SOURCE_RHO"])
        fields.update(MCICA_DOMAIN_ID=[1.], RADIATION_STEP=[float(step)],
                      SOURCE_QNC_PRESENT=[1.], SOURCE_TIME_SECONDS=[step*60.], MP_PHYSICS=[27.])
        return self.write(f"{phase.lower()}_000001.raw", "RRTMGP_RAW_V1", f"{phase} 2 3 2", fields)

    def test_latest_producer_and_both_phases(self):
        self.producer(8); self.producer(10); self.consumer("LW"); self.consumer("SW")
        report = inspect(self.directory, True, True)
        self.assertEqual(report["matched_consumers"], 2)
        self.assertTrue(all(j["producer_step"] == 10 for j in report["joins"]))
        self.assertEqual(report["conditional_liquid_formula"][0]["status"], "CONDITIONAL_REAL64_MATH_ONLY")

    def test_bootstrap_not_promoted(self):
        self.producer(11); self.consumer(step=11)
        report = inspect(self.directory)
        self.assertEqual(report["joins"][0]["status"], "NOT_RUN_INIT")
        with self.assertRaisesRegex(ValueError, "no actual matched"):
            inspect(self.directory, True)

    def test_lagged_qc_number_and_temperature_may_change(self):
        self.producer()
        self.fields["SOURCE_QC"][0] = 3.e-3
        self.fields["SOURCE_QNC"][0] = 4.e8
        self.fields["SOURCE_T"][0] = 253.
        self.consumer()
        changes = inspect(self.directory, True)["joins"][0]["current_state_changes_vs_producer"]
        self.assertEqual([changes[k] for k in ("SOURCE_QC", "SOURCE_QNC", "SOURCE_T")], [1, 1, 1])

    def test_radius_mutation_rejected(self):
        self.producer()
        self.fields["SOURCE_RE_CLOUD"][0] = 7.e-6
        self.consumer()
        with self.assertRaisesRegex(ValueError, "radius mismatch"):
            inspect(self.directory, True)

    def test_signed_zero_radius_mutation_rejected(self):
        self.fields["SOURCE_RE_CLOUD"][0] = 0.
        self.producer(); p = self.consumer()
        p.write_text(p.read_text().replace("SOURCE_RE_CLOUD 2\n0.0000000000000000E+00", "SOURCE_RE_CLOUD 2\n-0.0000000000000000E+00"))
        with self.assertRaisesRegex(ValueError, "radius mismatch"):
            inspect(self.directory)

    def test_duplicate_field_rejected(self):
        p = self.producer(); p.write_text(p.read_text()+"QMIN 1\n1E-12\n")
        with self.assertRaisesRegex(ValueError, "duplicate field"):
            inspect(self.directory)

    def test_duplicate_radiation_identity_rejected(self):
        self.producer(); p = self.consumer()
        (self.directory/"lw_000002.raw").write_bytes(p.read_bytes())
        with self.assertRaisesRegex(ValueError, "duplicate radiation identity"):
            inspect(self.directory)

    def test_wrong_filename_identity_rejected(self):
        p = self.producer(); p.write_text(p.read_text().replace("1 10 2 3 1 2", "1 10 4 3 1 2"))
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            inspect(self.directory)

    def test_wrong_phase_rejected(self):
        p = self.consumer(); p.write_text(p.read_text().replace("LW 2 3 2", "SW 2 3 2"))
        with self.assertRaisesRegex(ValueError, "phase mismatch"):
            inspect(self.directory)

    def test_missing_number_rejected_even_bootstrap(self):
        p = self.consumer(); p.write_text(p.read_text().replace("SOURCE_QNC 2", "OTHER_QNC 2"))
        with self.assertRaisesRegex(ValueError, "SOURCE_QNC"):
            inspect(self.directory)

    def test_native_dimension_mismatch_rejected(self):
        self.producer(); p = self.consumer(); p.write_text(p.read_text().replace("LW 2 3 2", "LW 2 3 3"))
        with self.assertRaisesRegex(ValueError, "wrong-size"):
            inspect(self.directory)

    def test_nonfinite_rejected(self):
        p = self.producer(); p.write_text(p.read_text().replace("2.5000000000000000E+02", "NaN"))
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            inspect(self.directory)

    def test_truncated_record_rejected(self):
        p = self.producer(); p.write_text("\n".join(p.read_text().splitlines()[:-1])+"\n")
        with self.assertRaisesRegex(ValueError, "truncated"):
            inspect(self.directory)

    def test_future_clock_rejected(self):
        p = self.producer(); self.consumer()
        p.write_text(p.read_text().replace("SOURCE_TIME_SECONDS 1\n6.0000000000000000E+02", "SOURCE_TIME_SECONDS 1\n9.0000000000000000E+02"))
        with self.assertRaisesRegex(ValueError, "physical time is after"):
            inspect(self.directory)

    def test_cf_tag_mismatch_rejected(self):
        self.producer(); p = self.consumer(); p.write_text(p.read_text()+"UDM_CF_SOURCE_STEP 1\n9\n")
        with self.assertRaisesRegex(ValueError, "CF tag differs"):
            inspect(self.directory)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
