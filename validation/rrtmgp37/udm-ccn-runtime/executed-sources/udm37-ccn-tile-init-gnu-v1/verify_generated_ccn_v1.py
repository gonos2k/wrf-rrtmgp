#!/usr/bin/env python3
"""Verify the generated/preprocessed CCN fix and its actual compiled objects."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SPEC_PATH = HERE / "source-freeze-v1.json"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_generated_sources(wrf: Path) -> dict[str, Any]:
    driver = wrf / "phys/module_microphysics_driver.f90"
    udm = wrf / "phys/module_mp_udm.f90"
    for path in (driver, udm):
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"missing/empty CPP-generated production file: {path}")
    d = driver.read_text(errors="strict").lower()
    u = udm.read_text(errors="strict").lower()
    assignment = re.search(r"qnn_curr\s*\(\s*ims\s*:\s*ime\s*,\s*kms\s*:\s*kme\s*,\s*jms\s*:\s*jme\s*\)\s*=\s*ccn_conc", d)
    omp_pos = d.find("!$omp parallel do", assignment.end()) if assignment else -1
    call = re.search(r"call\s+udm\s*\(", d[omp_pos:] if omp_pos >= 0 else "")
    keyword = re.search(r"ccn_preinitialized\s*=\s*\.true\.", d[omp_pos:] if omp_pos >= 0 else "")
    dummy = re.search(r"logical\s*,\s*optional\s*,\s*intent\s*\(\s*in\s*\)\s*::\s*ccn_preinitialized", u)
    default = re.search(r"initialize_ccn\s*=\s*\.true\.", u)
    override = re.search(r"if\s*\(\s*present\s*\(\s*ccn_preinitialized\s*\)\s*\)\s*initialize_ccn\s*=\s*\.not\.\s*ccn_preinitialized", u)
    gate = re.search(r"if\s*\(\s*itimestep\s*==\s*1\s*\.and\.\s*initialize_ccn\s*\)\s*then", u)
    if not all((assignment, omp_pos >= 0, call, keyword, dummy, default, override, gate)):
        raise ValueError("CPP-generated source lost a required CCN initialization construct")
    call_start = omp_pos + call.start()
    keyword_start = omp_pos + keyword.start()
    if not (assignment.start() < omp_pos < call_start and keyword_start > call_start):
        raise ValueError("CCN full-memory initialization is not before the tile loop/option-37 call")
    return {
        "status": "GENERATED_SOURCE_PASS",
        "driver": {"path": str(driver), "size_bytes": driver.stat().st_size, "sha256": digest(driver)},
        "udm": {"path": str(udm), "size_bytes": udm.stat().st_size, "sha256": digest(udm)},
        "assertions": {
            "full_domain_ccn_seed_assignment_precedes_omp_loop": True,
            "option37_udm_call_has_named_preinitialized_arg": True,
            "udm_optional_keyword_and_default_legacy_initialization": True,
        },
    }


def nm_symbols(path: Path) -> str:
    p = subprocess.run(["nm", "-g", str(path)], text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    if p.returncode:
        raise ValueError(f"nm failed for {path}: {p.stdout}")
    return p.stdout


def verify_compiled_objects(wrf: Path) -> dict[str, Any]:
    spec = json.loads(SPEC_PATH.read_text())
    phys = wrf / "phys"
    udm_obj = phys / "module_mp_udm.o"
    driver_obj = phys / "module_microphysics_driver.o"
    for path in (udm_obj, driver_obj):
        if not path.is_file() or path.stat().st_size == 0 or path.read_bytes()[:4] != b"\x7fELF":
            raise ValueError(f"missing/non-ELF generated object: {path}")
    udm_nm = nm_symbols(udm_obj)
    driver_nm = nm_symbols(driver_obj)
    symbol = spec["cpp_build_contract"]["symbol"]
    if not re.search(rf"\bT\s+{re.escape(symbol)}\b", udm_nm):
        raise ValueError(f"UDM object lacks the compiled module procedure symbol {symbol}")
    if not re.search(rf"\bU\s+{re.escape(symbol)}\b", driver_nm):
        raise ValueError(f"microphysics driver object does not call the compiled UDM procedure {symbol}")

    rte_dir = wrf / "external/rte_rrtmgp/build"
    actual = sorted(p.name for p in rte_dir.glob("*.o"))
    expected = sorted(spec["external_rte_object_names"])
    if actual != expected:
        raise ValueError(f"RRTMGP external object roster differs (expected {len(expected)}, found {len(actual)})")
    ext = []
    for name in actual:
        path = rte_dir / name
        if path.stat().st_size == 0 or path.read_bytes()[:4] != b"\x7fELF":
            raise ValueError(f"empty or invalid RRTMGP object: {path}")
        ext.append({"name": name, "size_bytes": path.stat().st_size, "sha256": digest(path)})
    return {
        "status": "COMPILED_OBJECT_PASS",
        "udm_object": {"path": str(udm_obj), "size_bytes": udm_obj.stat().st_size, "sha256": digest(udm_obj)},
        "driver_object": {"path": str(driver_obj), "size_bytes": driver_obj.stat().st_size, "sha256": digest(driver_obj)},
        "udm_symbol": symbol,
        "external_rte_object_count": len(ext),
        "external_rte_objects": ext,
    }


def verify_compile_commands(log: Path) -> dict[str, Any]:
    text = log.read_text(errors="replace")
    lower = text.lower()
    flags = {
        "mpi_macro": "-ddm_parallel" in lower,
        "openmp_flag": "-fopenmp" in lower,
        "gnu_mpi_wrapper": "mpif90" in lower,
    }
    if not all(flags.values()):
        raise ValueError(f"fresh compile log lacks requested GNU dm+sm flags: {flags}")
    targets = {}
    for target in ("module_mp_udm.o", "module_microphysics_driver.o"):
        lines = [line for line in text.splitlines() if target in line]
        if not lines:
            raise ValueError(f"compile log lacks the production target {target}")
        active_compile_lines = [line.lower() for line in lines
                                if "mpif90" in line.lower() and " -c " in line.lower()]
        targets[target] = {
            "command_line_count": len(lines),
            "active_compile_command_count": len(active_compile_lines),
            "dm_parallel": any("-ddm_parallel" in line for line in active_compile_lines),
            "openmp": any("-fopenmp" in line for line in active_compile_lines),
            "mpif90": bool(active_compile_lines),
        }
        if not all(targets[target][k] for k in ("dm_parallel", "openmp", "mpif90")):
            raise ValueError(f"production compile command lacks expected flags: {target}: {targets[target]}")
    return {"status": "COMPILE_COMMAND_PASS", "flags": flags, "production_targets": targets}
