#!/usr/bin/env python3
"""Independently read the exact serial O0/O2 NetCDF fixture output roster.

No backend compilation or WRF model run. Never write into the input directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys


EXPECTED_FILES = {"zz.nc", "scalar-1.nc", "scalar-2.nc"} | {
    f"preflight-{bad}-{follow}.nc" for bad in range(1, 7) for follow in (1, 2)
} | {f"bad-order-attribute-{case}.nc" for case in range(1, 4)}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(input_root):
    import numpy as np
    import scipy
    from scipy.io import netcdf_file

    input_root = Path(input_root).resolve(strict=True)
    # Validate every name before reading any arrays. A duplicate valid fixture
    # must not compensate for a missing scalar or recovery case.
    for optimization in ("O0", "O2"):
        case = input_root / optimization / "ranks-1"
        actual = {p.name for p in case.glob("*.nc")}
        require(actual == EXPECTED_FILES,
                f"{optimization}: output roster mismatch; "
                f"missing={sorted(EXPECTED_FILES - actual)}, "
                f"unexpected={sorted(actual - EXPECTED_FILES)}")
        require(all((case / name).is_file() for name in EXPECTED_FILES),
                f"{optimization}: output is not a regular file")

    expected = np.array([[1000 * j + 17 * i for i in range(1, 4)]
                         for j in range(1, 6)], dtype=np.int32)
    dates = ["2026-10-06_00:00:00", "2026-10-06_01:00:00"]
    rows = []
    for optimization in ("O0", "O2"):
        for name in sorted(EXPECTED_FILES):
            path = input_root / optimization / "ranks-1" / name
            before = digest(path)
            with netcdf_file(path, "r", mmap=False) as ds:
                def check(condition, message):
                    require(condition, f"{optimization}/{name}: {message}")

                def times():
                    return [b"".join(row).decode("ascii")
                            for row in ds.variables["Times"].data]

                if name.startswith("scalar-"):
                    check(times() == dates, "scalar times")
                    v = ds.variables["SCALAR"]
                    check(v.dimensions == ("Time",), "scalar dimensions")
                    check(v.MemoryOrder == b"0  ", "scalar memory-order bytes")
                    check(v.data.dtype.kind == "i" and v.data.dtype.itemsize == 4,
                          "scalar INTEGER32 storage")
                    check(np.array_equal(v.data, np.array([-17, 2033], dtype=np.int32)),
                          "scalar values")
                    kind = "scalar_order_zero"
                elif name.startswith("preflight-"):
                    follow = int(path.stem.split("-")[-1])
                    check(times() == [dates[0], f"2026-10-06_0{follow}:00:00"],
                          "recovery times")
                    v = ds.variables["FIELD"]
                    check(v.data.shape == (2, 5, 3), "recovery shape")
                    check(np.array_equal(v.data[0], expected) and
                          np.array_equal(v.data[1], expected), "recovery values")
                    kind = "rejected_write_recovery"
                elif name == "zz.nc":
                    check(times() == dates, "ZZ times")
                    for field, offset in (("INT_UPPER", 0), ("INT_LOWER", 0),
                                          ("FLOAT_REAL", .25), ("FLOAT_LOWER", .5)):
                        v = ds.variables[field]
                        check(v.dimensions == ("Time", "independent_n", "vertical_k"),
                              f"{field} dimensions")
                        check(v.MemoryOrder == b"ZZ ", f"{field} memory order")
                        check(v.data.shape == (2, 5, 3), f"{field} shape")
                        for record in range(2):
                            check(np.array_equal(v.data[record],
                                                 expected + 100000 * record + offset),
                                  f"{field} values at record {record}")
                    kind = "ordered_ZZ"
                else:
                    case = int(path.stem.split("-")[-1])
                    check(ds.variables["FIELD"].MemoryOrder ==
                          {1: b"xyzq", 2: b"qq", 3: b""}[case], "malformed attribute")
                    kind = "malformed_attribute_fixture"
            require(digest(path) == before, f"input changed while reading: {path}")
            rows.append({"path": str(path), "sha256": before,
                         "size_bytes": path.stat().st_size,
                         "optimization": optimization, "kind": kind})
    return {"status": "PASS_SCOPED_NETCDF_OUTPUT_ROSTER", "results": rows,
            "file_counts": {kind: sum(row["kind"] == kind for row in rows)
                            for kind in ("scalar_order_zero", "rejected_write_recovery",
                                         "ordered_ZZ", "malformed_attribute_fixture")},
            "numpy_version": np.__version__, "scipy_version": scipy.__version__,
            "scope": "serial fixture files only; no WRF, MPI or physical acceptance",
            "production_accepted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_root", type=Path)
    parser.add_argument("--output", type=Path, required=True,
                        help="new receipt path outside the input directory")
    args = parser.parse_args()
    input_root = args.input_root.resolve()
    output = args.output.absolute()
    if output.exists() or output.is_symlink() or output.resolve().is_relative_to(input_root):
        parser.error("--output must be new and outside the input directory")
    try:
        result = verify(input_root)
        rc = 0
    except Exception as error:
        result = {"status": "FAIL_SCOPED_NETCDF_OUTPUT_ROSTER", "error": str(error),
                  "production_accepted": False}
        rc = 1
    result.update(exit_code=rc, verifier_sha256=digest(Path(__file__)))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(result["status"])
    return rc


if __name__ == "__main__":
    sys.exit(main())
