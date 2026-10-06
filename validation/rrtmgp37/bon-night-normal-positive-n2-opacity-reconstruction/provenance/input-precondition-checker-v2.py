#!/usr/bin/env python3
"""Validate only pinned positive-N2 V13 input and adapter preconditions.

No result packet, opacity array, coefficient table, or solver API is read.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile

SCHEMA = "udm37-normal-positive-n2-preconditions-v2"
INPUT_REL = Path("build/udm37-legacy-lw-source-export-bon-audit-v2/cases/SOURCE_OFF/trace/lw_000001.input")
ADAPTER_REL = Path("build/udm37-legacy-lw-source-export-serial-build-v1/source/WRF/phys/module_ra_rrtmgp.F")
INPUT_SHA = "9c477295b7a01de8b5e38b612052f1e61e711402a5a839bd1cb9c58b6eed2168"
ADAPTER_SHA = "1852452555fbe667a0a95d59242bcd9c3833f2877fc51f882d5d3d929a058f58"
CFC = ("VMR_CFC11", "VMR_CFC12", "VMR_CFC22", "VMR_CCL4")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_packet(path: Path):
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 3 or lines[0].strip() != "RRTMGP_REPLAY_V13":
        raise ValueError("input is not V13")
    dims = lines[1].split()
    if len(dims) < 3 or dims[0] != "LW" or tuple(map(int, dims[1:3])) != (1, 45):
        raise ValueError("expected LW input with one column and 45 engine layers")
    out = {}
    i = 2
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        h = lines[i].split()
        if len(h) < 2:
            raise ValueError(f"bad section header at line {i+1}")
        name = h[0]
        shape = tuple(int(x) for x in h[1:])
        if name in out or not shape or any(x <= 0 for x in shape):
            raise ValueError(f"duplicate/invalid section {name}")
        count, vals = math.prod(shape), []
        i += 1
        while i < len(lines) and len(vals) < count:
            if lines[i].strip():
                vals.extend(float(x.replace("D", "E").replace("d", "e")) for x in lines[i].split())
            i += 1
        if len(vals) != count:
            raise ValueError(f"truncated section {name}")
        out[name] = {"shape": shape, "values": vals}
    return out


def normalize_fortran(text: str) -> str:
    return re.sub(r"\s+", "", "\n".join(line.split("!", 1)[0] for line in text.lower().splitlines()))


def atomic_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmpname = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmpname, path)
        dfd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        if os.path.exists(tmpname):
            os.unlink(tmpname)


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} WORKSPACE_ROOT RECEIPT_JSON", file=sys.stderr)
        return 2
    root, receipt = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    if receipt.exists():
        print(f"refusing to overwrite receipt: {receipt}", file=sys.stderr)
        return 2
    result = {"schema": SCHEMA, "status": "FAIL", "process_rc": 1,
              "scope": "V13 input/source preconditions only; no result/tau/coefficient/solver reads."}
    rc = 1
    try:
        inp, src = root / INPUT_REL, root / ADAPTER_REL
        for p, want, label in ((inp, INPUT_SHA, "input"), (src, ADAPTER_SHA, "adapter")):
            if not p.is_file() or p.is_symlink():
                raise ValueError(f"{label} is not a regular file")
            got = sha(p)
            if got != want:
                raise ValueError(f"{label} hash mismatch: {got}")
        text = src.read_text(encoding="ascii")
        norm = normalize_fortran(text)
        m = re.search(r"dry_background_n2_vmr=([0-9.]+)_wp", norm)
        if not m:
            raise ValueError("pinned source N2 default literal not found")
        source_n2 = float(m.group(1))
        if source_n2 != 0.7808:
            raise ValueError(f"source N2 literal changed: {source_n2!r}")
        # Check actual source structure: all four optionals determine the trace marker;
        # a partial set is rejected; set_gases_lw independently enforces all-or-none.
        for exact in (
            "trace_gases=present(cfc11vmr).and.present(cfc12vmr).and.present(cfc22vmr).and.present(ccl4vmr)",
            "if((present(cfc11vmr).or.present(cfc12vmr).or.present(cfc22vmr).or.present(ccl4vmr)).and..not.trace_gases)then",
            "callrequire('rrtmgp_lw_trace_gas_partial_inputs')",
            "any_cfc=present(cfc11).or.present(cfc12).or.present(cfc22).or.present(ccl4)",
            "all_cfc=present(cfc11).and.present(cfc12).and.present(cfc22).and.present(ccl4)",
            "if(any_cfc.and..not.all_cfc)then",
            "callrequire('rrtmgp_lw_trace_gas_partial_inputs')",
            "callrequire(gases%set_vmr('n2',n2_background))",
        ):
            if exact not in norm:
                raise ValueError(f"adapter source contract missing: {exact}")
        sections = read_packet(inp)
        marker = sections.get("TRACE_GASES_PRESENT")
        if marker is None or marker["shape"] != (1, 1) or marker["values"] != [1.0]:
            raise ValueError("V13 trace marker must be scalar 1 for all-present CFC profiles")
        n2 = sections.get("VMR_N2")
        if n2 is None or n2["shape"] != (1, 45):
            raise ValueError("V13 VMR_N2 must have shape (1,45)")
        if not all(math.isfinite(x) and x == source_n2 for x in n2["values"]):
            raise ValueError("captured N2 vector is not finite and exactly equal to source constant")
        cfc_records = {}
        cfc_presence = {name: name in sections for name in CFC}
        for name in CFC:
            rec = sections.get(name)
            if rec is None or rec["shape"] != (1, 45):
                raise ValueError(f"all-present marker requires {name} shape (1,45)")
            if not all(math.isfinite(x) and x >= 0.0 for x in rec["values"]):
                raise ValueError(f"{name} must be finite and nonnegative")
            cfc_records[name] = {"shape": list(rec["shape"]), "finite": True,
                                 "nonnegative": True, "count": len(rec["values"])}
        if not all(cfc_presence.values()):
            raise ValueError("marker says trace gases present but CFC group is partial")
        rc = 0
        result.update({
            "status": "PASS_SCOPED_INPUT_SOURCE_PRECONDITIONS",
            "input": {"path": str(inp), "sha256": INPUT_SHA, "size_bytes": inp.stat().st_size,
                      "version": "V13", "phase": "LW", "columns": 1, "layers": 45},
            "adapter": {"path": str(src), "sha256": ADAPTER_SHA, "size_bytes": src.stat().st_size,
                        "source_n2_literal": source_n2},
            "n2": {"section": "VMR_N2", "shape": list(n2["shape"]),
                   "count": 45, "all_exactly_equal_to_source_literal": True,
                   "value": source_n2},
            "trace_gases_present_marker": {"shape": list(marker["shape"]), "value": 1,
                                           "matches_all_present_source_semantics": True},
            "cfc_group": {"presence": cfc_presence, "profiles": cfc_records,
                          "source_semantics": "All four present is accepted; any partial presence is rejected; all absent uses zero profiles."},
            "source_contract_checks": [
                "LW trace_gases is PRESENT of all four CFC arguments.",
                "The public LW wrapper rejects any partial optional CFC group.",
                "set_gases_lw independently rejects any partial optional CFC group.",
                "The all-present path checks CFC shapes, finiteness, nonnegativity and sets all four gases.",
                "Background N2 is always set_vmr('n2', n2_background), independently of the CFC trace flag."
            ],
            "forbidden_inputs_opened": [],
            "non_actions": {"result_or_tau_read": False, "coefficient_table_read": False,
                            "reconstruction_invoked": False, "solver_or_model_invoked": False}
        })
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
    result["process_rc"] = rc
    atomic_json(receipt, result)
    return rc

if __name__ == "__main__":
    raise SystemExit(main())
