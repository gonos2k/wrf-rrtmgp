#!/usr/bin/env python3
"""Exercise the local RRTMGP Makefile's compiler/configuration invalidation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
RRTMGP_SOURCE = REPO_ROOT / "WRF" / "external" / "rte_rrtmgp"
BASE_FLAGS = "-cpp -O0 -ffree-line-length-none"
CHANGED_FLAGS = BASE_FLAGS + " -DWRF_RRTMGP_REPRO_TEST_FLAG"
LIBRARY_ARCHIVES = (
    "librte.a",
    "librrtmgp.a",
    "librtekernels.a",
    "librtef.a",
    "librrtmgpkernels.a",
    "librrtmgpf.a",
)


def run_make(
    build_dir: Path,
    compiler: str,
    flags: str,
    netcdf_prefix: Path,
    *targets: str,
) -> subprocess.CompletedProcess[str]:
    command = [
        "make",
        "--no-print-directory",
        "-C",
        str(build_dir),
        "-j8",
        f"FC={compiler}",
        f"FCFLAGS={flags}",
        f"NETCDFPATH={netcdf_prefix}",
        *targets,
    ]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def command_counts(result: subprocess.CompletedProcess[str]) -> dict[str, int]:
    lines = (result.stdout + result.stderr).splitlines()
    return {
        "compile_commands": sum(" -c " in line for line in lines),
        "archive_commands": sum(line.startswith("ar -rvs ") for line in lines),
    }


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netcdf-prefix", required=True, type=Path)
    parser.add_argument("--compiler", default="gfortran", metavar="FC")
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    netcdf_prefix = args.netcdf_prefix.resolve()
    output_dir = args.output_dir.resolve()
    if not (netcdf_prefix / "include").is_dir():
        raise RuntimeError(f"NetCDF include directory is missing: {netcdf_prefix / 'include'}")
    if output_dir.exists():
        raise RuntimeError(f"output directory must be fresh: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)

    # The copied tree isolates all object/module/archive and stamp writes from
    # the active source checkout and any shared WRF build directory.
    copied_source = output_dir / "rte_rrtmgp"
    shutil.copytree(
        RRTMGP_SOURCE,
        copied_source,
        ignore=shutil.ignore_patterns(
            "*.o",
            "*.mod",
            "*.a",
            "*.optrpt",
            ".wrf-rrtmgp-config*",
        ),
    )
    build_dir = copied_source / "build"

    clean = run_make(build_dir, args.compiler, BASE_FLAGS, netcdf_prefix, "libs")
    clean_counts = command_counts(clean)
    expected_objects = clean_counts["compile_commands"]
    require(expected_objects > 0, "clean build compiled no objects")
    require(len(LIBRARY_ARCHIVES) == clean_counts["archive_commands"], "clean build did not create six archives")
    build_object = build_dir / "mo_rte_kind.o"
    require(build_object.is_file(), "expected object mo_rte_kind.o was not built")
    mtime_clean = build_object.stat().st_mtime_ns

    unchanged = run_make(build_dir, args.compiler, BASE_FLAGS, netcdf_prefix, "libs")
    unchanged_counts = command_counts(unchanged)
    mtime_unchanged = build_object.stat().st_mtime_ns
    require(unchanged_counts == {"compile_commands": 0, "archive_commands": 0}, "same configuration rebuilt outputs")
    require(mtime_unchanged == mtime_clean, "same configuration changed an object mtime")

    inventory_before = set(build_dir.glob(".wrf-rrtmgp-config-request-*"))
    (build_dir / "dummy.o").write_text("should not be archived\n", encoding="ascii")
    inventory_result = run_make(
        build_dir,
        args.compiler,
        BASE_FLAGS,
        netcdf_prefix,
        "print-wrf-objects",
    )
    inventory = inventory_result.stdout.split()
    inventory_after = set(build_dir.glob(".wrf-rrtmgp-config-request-*"))
    require("dummy.o" not in inventory, "inventory included an unrelated dummy.o")
    require(len(inventory) == expected_objects, "inventory count differs from clean compile count")
    require(all(name.endswith(".o") for name in inventory), "inventory emitted non-object output")
    require(inventory_before == inventory_after, "read-only inventory created a configuration request file")
    inventory_archive = build_dir / "libwrf-inventory-probe.a"
    subprocess.run(
        ["ar", "rcs", str(inventory_archive), *(str(build_dir / name) for name in inventory)],
        check=True,
    )
    archive_members = subprocess.run(
        ["ar", "t", str(inventory_archive)], text=True, capture_output=True, check=True
    ).stdout.splitlines()
    require("dummy.o" not in archive_members, "test archive included the unrelated dummy.o")

    changed = run_make(build_dir, args.compiler, CHANGED_FLAGS, netcdf_prefix, "libs")
    changed_counts = command_counts(changed)
    mtime_changed = build_object.stat().st_mtime_ns
    require(changed_counts == {"compile_commands": expected_objects, "archive_commands": len(LIBRARY_ARCHIVES)}, "flag change did not rebuild every output")
    require(mtime_changed > mtime_unchanged, "flag change did not update an object mtime")

    repeat = run_make(build_dir, args.compiler, CHANGED_FLAGS, netcdf_prefix, "libs")
    repeat_counts = command_counts(repeat)
    require(repeat_counts == {"compile_commands": 0, "archive_commands": 0}, "repeated changed configuration rebuilt outputs")

    # Simulate a source/object being removed from the declared inventory. The
    # old manifest must clean its stale object; the source must not be needed.
    makefile = build_dir / "Makefile"
    makefile_text = makefile.read_text(encoding="utf-8")
    block_start = makefile_text.index("WRF_RRTMGP_EXTENSION_OBJECTS =")
    block_end = makefile_text.index("WRF_RRTMGP_OBJECTS =", block_start)
    object_block = makefile_text[block_start:block_end]
    object_names = object_block.replace("\\\n", " ").replace("\n", " ").split()[2:]
    require("mo_heating_rates.o" in object_names, "expected extension object entry is absent from copied Makefile")
    object_names.remove("mo_heating_rates.o")
    replacement = "WRF_RRTMGP_EXTENSION_OBJECTS = " + " ".join(object_names) + "\n"
    makefile.write_text(
        makefile_text[:block_start] + replacement + makefile_text[block_end:],
        encoding="utf-8",
    )
    (copied_source / "extensions" / "mo_heating_rates.F90").unlink()
    removed = run_make(build_dir, args.compiler, CHANGED_FLAGS, netcdf_prefix, "libs")
    removed_counts = command_counts(removed)
    require(removed_counts["compile_commands"] == expected_objects - 1, "object inventory removal rebuilt the wrong number of objects")
    require(not (build_dir / "mo_heating_rates.o").exists(), "removed object remained in the build directory")
    removed_inventory = run_make(
        build_dir,
        args.compiler,
        CHANGED_FLAGS,
        netcdf_prefix,
        "print-wrf-objects",
    ).stdout.split()
    require("mo_heating_rates.o" not in removed_inventory, "removed object remained in the exported inventory")
    inventory_archive.unlink()
    subprocess.run(
        ["ar", "rcs", str(inventory_archive), *(str(build_dir / name) for name in removed_inventory)],
        check=True,
    )
    archive_members = subprocess.run(
        ["ar", "t", str(inventory_archive)], text=True, capture_output=True, check=True
    ).stdout.splitlines()
    require("mo_heating_rates.o" not in archive_members, "test archive retained the removed inventory member")
    for archive in LIBRARY_ARCHIVES:
        archive_path = build_dir / archive
        if archive_path.exists():
            members = subprocess.run(
                ["ar", "t", str(archive_path)], text=True, capture_output=True, check=True
            ).stdout.splitlines()
            require("mo_heating_rates.o" not in members, f"stale object remains in {archive}")

    report: dict[str, Any] = {
        "status": "PASS",
        "output_directory": str(output_dir),
        "compiler": args.compiler,
        "netcdf_prefix": str(netcdf_prefix),
        "configuration_note": "Concurrent different compiler/configuration builds in one build directory are unsupported; make -j parallelism within one invocation is tested.",
        "clean": clean_counts,
        "unchanged": unchanged_counts,
        "flag_change": changed_counts,
        "repeat_after_flag_change": repeat_counts,
        "inventory_objects": len(inventory),
        "dummy_excluded": True,
        "removed_object": {
            "compile_commands": removed_counts["compile_commands"],
            "stale_object_removed": True,
            "stale_archive_members_removed": True,
        },
        "object_mtime_ns": {
            "clean": mtime_clean,
            "unchanged": mtime_unchanged,
            "flag_change": mtime_changed,
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2), file=sys.stderr)
        raise SystemExit(1)
