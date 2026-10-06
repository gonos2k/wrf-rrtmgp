#!/usr/bin/env python3
"""Exercise FindnetCDF-Fortran path discovery with inert CMake fixtures.

This checks configure-time path selection only. The empty library placeholders
are never linked, and this is not a compiler or netCDF installation test.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

from test_cmake_installed_consumers import atomic, stage


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


save_json = atomic

def fake_nf_config(path, prefix, include_dir, flibs):
    script = """#!/bin/sh
printf '%s\\n' "$1" >> "$NF_CONFIG_LOG"
case "$1" in
  --includedir) printf '%s\\n' {include_dir} ;;
  --prefix) printf '%s\\n' {prefix} ;;
  --flibs) printf '%s\\n' {flibs} ;;
  --version) printf '%s\\n' 'netCDF-Fortran 4.6.1' ;;
  --has-*) printf '%s\\n' yes ;;
  *) exit 2 ;;
esac
""".format(
        include_dir=shlex.quote(str(include_dir)),
        prefix=shlex.quote(str(prefix)),
        flibs=shlex.quote(flibs),
    )
    path.write_text(script)
    path.chmod(0o755)


def make_case(root, name, arch, lib_relative, flibs_builder):
    case = root / name
    prefix = case / "prefix"
    include_dir = prefix / "include"
    include_dir.mkdir(parents=True)
    (include_dir / "netcdf.inc").write_text("! nf_format_64bit_data fixture\n")
    nf_bin = case / "bin"
    nf_bin.mkdir()
    nf_log = case / "nf-config.args"
    expected = (case / lib_relative).resolve()
    expected.parent.mkdir(parents=True, exist_ok=True)
    expected.write_bytes(b"")  # existence-only placeholder, never linked
    flibs = flibs_builder(prefix, case, expected)
    fake_nf_config(nf_bin / "nf-config", prefix, include_dir, flibs)
    cmake_source = case / "src"
    cmake_source.mkdir()
    (cmake_source / "CMakeLists.txt").write_text(
        """cmake_minimum_required(VERSION 3.16)
project(netcdf_fortran_discovery_fixture LANGUAGES NONE)
set(CMAKE_MODULE_PATH "${FIXTURE_MODULE_DIR}")
set(CMAKE_LIBRARY_ARCHITECTURE "${FIXTURE_ARCH}")
add_library(netCDF::netcdf INTERFACE IMPORTED)
set(netCDF_FOUND TRUE)
find_package(netCDF-Fortran REQUIRED MODULE)
if(NOT "${netCDF-Fortran_LIBRARY}" STREQUAL "${FIXTURE_EXPECTED_LIBRARY}")
  message(FATAL_ERROR "wrong library: '${netCDF-Fortran_LIBRARY}'")
endif()
message(STATUS "EXPECTED_LIBRARY_FOUND=${netCDF-Fortran_LIBRARY}")
"""
    )
    return {
        "name": name,
        "case_dir": str(case),
        "prefix": str(prefix),
        "expected_library": str(expected),
        "nf_config_log": str(nf_log),
        "nf_bin": str(nf_bin),
        "source_dir": str(cmake_source),
    }


def run_case(case, module_dir, arch, receipt_path, state):
    build = Path(case["case_dir"]) / "build"
    log = Path(case["case_dir"]) / "configure.log"
    command = [shutil.which("cmake") or "cmake", "-S", case["source_dir"],
               "-B", str(build), "-DFIXTURE_MODULE_DIR=" + str(module_dir),
               "-DFIXTURE_ARCH=" + arch,
               "-DFIXTURE_EXPECTED_LIBRARY=" + case["expected_library"]]
    env = os.environ.copy()
    env["PATH"] = case["nf_bin"] + os.pathsep + env.get("PATH", "")
    env["NF_CONFIG_LOG"] = case["nf_config_log"]
    stage(state, receipt_path, case["name"] + "-configure", command,
          Path(case["case_dir"]), env, log, 60)
    row = dict(state["stages"][-1])
    row["nf_config_arguments"] = Path(case["nf_config_log"]).read_text().splitlines()
    output = log.read_text(errors="replace")
    if "EXPECTED_LIBRARY_FOUND=" + case["expected_library"] not in output:
        state.update(status="FAIL_EXPECTED_PATH_NOT_REPORTED")
        save_json(receipt_path, state)
        raise RuntimeError(f"{case['name']}: expected path not reported")
    row["status"] = "PASS_PATH_SELECTED"
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path,
                        default=Path(__file__).resolve().parents[3])
    args = parser.parse_args()
    args.output_dir = args.output_dir.resolve()
    if args.output_dir.exists():
        parser.error(f"output directory already exists: {args.output_dir}")
    cmake = shutil.which("cmake")
    if not cmake:
        parser.error("cmake was not found on PATH")
    module_dir = (args.repo_root / "WRF" / "cmake" / "modules").resolve()
    finder = module_dir / "FindnetCDF-Fortran.cmake"
    if not finder.is_file():
        parser.error(f"finder not found: {finder}")
    arch = "fixture-multiarch"
    args.output_dir.mkdir(parents=True)
    receipt = args.output_dir / "execution.json"
    base = {"schema": "NETCDF_FORTRAN_DISCOVERY_FIXTURE_V1",
            "scope": "CMake configure-time path selection; no linking",
            "finder": str(finder), "finder_sha256": sha256(finder),
            "finder_size_bytes": finder.stat().st_size,
            "cmake": cmake, "cases": [], "stages": [],
            "process_helper_sha256": sha256(Path(__file__).with_name("test_cmake_installed_consumers.py"))}
    save_json(receipt, base)
    cases = [
        make_case(args.output_dir, "prefix-lib", arch, Path("prefix/lib/libnetcdff.a"),
                  lambda p, c, e: f"-L{p / 'lib'} -lnetcdff"),
        make_case(args.output_dir, "prefix-multiarch", arch,
                  Path(f"prefix/lib/{arch}/libnetcdff.a"),
                  lambda p, c, e: f"-Wl,--as-needed -L{p / 'lib'} -lnetcdff"),
        make_case(args.output_dir, "explicit-l-after-flags", arch,
                  Path("external/lib/libnetcdff.a"),
                  lambda p, c, e: f"-Wl,--as-needed -pthread -L{e.parent} -lnetcdff"),
    ]
    # Verify each case and persist its result before the next child.
    rows = []
    for case in cases:
        rows.append(run_case(case, module_dir, arch, receipt, base))
        base.update(status="IN_PROGRESS", cases=rows)
        save_json(receipt, base)
    base.update(status="PASS_ALL_3_CONFIGURE_CASES", cases=rows)
    save_json(receipt, base)
    print(f"PASS: 3 CMake path-discovery fixtures; receipt={receipt}")


if __name__ == "__main__": main()
