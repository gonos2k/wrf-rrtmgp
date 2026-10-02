#!/usr/bin/env python3
"""Link the optical-only counterfactual against a completed serial WRF build."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wrf-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--netcdf-prefix", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--compiler", default="gfortran")
    args = parser.parse_args()
    wrf, out = args.wrf_root.resolve(), args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source = wrf / "test/rrtmgp/rrtmg_sw_optics_bridge.f90"
    libraries = [wrf / name for name in (
        "main/libwrflib.a", "external/fftpack/fftpack5/libfftpack.a",
        "external/io_grib1/libio_grib1.a", "external/io_grib_share/libio_grib_share.a",
        "external/io_int/libwrfio_int.a", "external/esmf_time_f90/libesmf_time.a",
        "frame/module_internal_header_util.o", "frame/pack_utils.o",
        "external/io_netcdf/libwrfio_nf.a")]
    missing = [str(path) for path in libraries if not path.is_file()]
    if missing:
        raise RuntimeError(f"build serial em_scm_xy first; missing: {missing}")
    executable = out / "rrtmg_sw_optics_bridge"
    command = [args.compiler, "-ffree-line-length-none", "-fcheck=bounds"]
    for directory in ("phys", "frame", "share"):
        command += ["-I", str(wrf / directory)]
    command += [str(source), "-o", str(executable), "-Wl,--start-group"]
    command += [str(path) for path in libraries]
    command += ["-Wl,--end-group", f"-L{args.netcdf_prefix.resolve() / 'lib'}", "-lnetcdff", "-lnetcdf"]
    result = subprocess.run(command, text=True, capture_output=True)
    (out / "build.log").write_text(result.stdout + result.stderr)
    result.check_returncode()
    inventory = [source, wrf / "phys/module_ra_rrtmg_sw.F", wrf / "phys/module_ra_rrtmg_lw.F",
                 *libraries, executable]
    manifest = {"scope": "optical-only diagnostic; linked actual built WRF archive; serial GNU ABI",
                "command": command,
                "sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in inventory}}
    (out / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(executable)


if __name__ == "__main__":
    main()
