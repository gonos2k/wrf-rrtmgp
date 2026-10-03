#!/usr/bin/env python3
"""Contract checks for the V10 LW and V11 SW CU replay extensions."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from compare_column_replay import ReplayFormatError, read_result  # noqa: E402
from test_column_replay import (ReplayError, validate_cu_population_raw,
                                validate_cu_population_records, read_input)  # noqa: E402


def make_records(nc: int = 2, nl: int = 3, sw: bool = False) -> dict[str, np.ndarray]:
    shape = (nc, nl)
    records = {
        name: np.full((1, 1), 1.0)
        for name in ("CU_POPULATION_POLICY", "CU_RADIUS_POLICY", "CU_OCCURRENCE_POLICY")
    }
    records.update({
        "CU_LWP": np.zeros(shape), "CU_IWP": np.zeros(shape),
        "CU_REL": np.full(shape, 10.0), "CU_REI": np.full(shape, 20.0),
        "CU_REL_RAW": np.full(shape, 10.0), "CU_REI_RAW": np.full(shape, 20.0),
        "NATIVE_QC": np.full(shape, 1.e-5), "NATIVE_QI": np.full(shape, 2.e-5),
        "CU_QC": np.array([[1.e-5, -2.e-5, 0.], [0., 3.e-5, -1.e-5]]),
        "CU_QI": np.array([[0., 1.e-5, -1.e-5], [2.e-5, 0., -2.e-5]]),
        "DP_CU": np.full(shape, 0.2), "SH_CU": np.full(shape, 0.1),
        "CF_CU": np.full(shape, 0.3), "CF": np.array([[0.5, 0.5, 0.], [0.5, 0.5, 0.5]]),
        "DRY_MASS_KG_M2": np.full(shape, 1000.0),
    })
    records = {name: value.astype(np.float32).astype(np.float64) for name, value in records.items()}
    records["DP_CU"][0, 2] = 0.0
    records["SH_CU"][0, 2] = 0.0
    records["CF_CU"] = (records["DP_CU"].astype(np.float32) +
                        records["SH_CU"].astype(np.float32)).astype(np.float64)
    for src, native, cu in (("QC", "NATIVE_QC", "CU_QC"), ("QI", "NATIVE_QI", "CU_QI")):
        records[f"SOURCE_{src}"] = (
            records[native].astype(np.float32) +
            records[cu].astype(np.float32) * records["CF_CU"].astype(np.float32)
        ).astype(np.float64)
    for phase, qname in (("LWP", "CU_QC"), ("IWP", "CU_QI")):
        q = records[qname]
        accepted = 1000.0 * records["DRY_MASS_KG_M2"] * records["CF_CU"] * np.maximum(q, 0.0)
        rejected = 1000.0 * records["DRY_MASS_KG_M2"] * records["CF_CU"] * np.maximum(-q, 0.0)
        records[f"CU_ACCEPTED_GRID_{phase}"] = accepted.astype(np.float32).astype(np.float64)
        records[f"CU_REJECTED_GRID_{phase}"] = rejected.astype(np.float32).astype(np.float64)
        records[f"CU_OMITTED_CF0_{phase}"] = np.where(
            records["CF"] == 0.0, accepted, 0.0).astype(np.float32).astype(np.float64)
        incloud = np.zeros(shape)
        wet = records["CF"] > 0.0
        incloud[wet] = accepted[wet] / records["CF"][wet]
        records[f"CU_{phase}"] = incloud.astype(np.float32).astype(np.float64)
    if sw:
        records["RAW_NATIVE_CLOUD_TAU"] = np.full((nc, nl, 14), 1.0 + 2.0**-25)
        records["RAW_CU_CLOUD_TAU"] = np.full((nc, nl, 14), 2.0**-25)
        records["RAW_CLOUD_TAU"] = (records["RAW_NATIVE_CLOUD_TAU"] +
                                     records["RAW_CU_CLOUD_TAU"]).astype(np.float32).astype(np.float64)
    return records


def expect_error(records: dict[str, np.ndarray], phase: str, version: str) -> None:
    try:
        validate_cu_population_records(records, 2, 3, phase, version, Path("synthetic.input"))
    except ReplayError:
        return
    raise AssertionError("corrupt CU records were accepted")


def write_result(path: Path, phase: str, names: tuple[str, ...]) -> None:
    records = {
        "GAS_TAU": np.ones((2, 3, 1)), "CLOUD_TAU": np.ones((2, 3, 1)),
        "PREPARED_TAU": np.ones((2, 3, 1)), "MASK": np.ones((2, 3, 1)),
        "TOTAL_TAU": np.ones((2, 3, 1)),
        "RL_USED": np.full((2, 3, 1), 10.0), "DI_USED": np.full((2, 3, 1), 20.0),
        "DS_USED": np.full((2, 3, 1), 20.0),
        "UP": np.ones((2, 4, 1)), "DN": np.ones((2, 4, 1)), "HR": np.ones((2, 3, 1)),
        "UPC": np.ones((2, 4, 1)), "DNC": np.ones((2, 4, 1)), "HRC": np.ones((2, 3, 1)),
        "NATIVE_CLOUD_TAU": np.ones((2, 3, 1)),
        "CU_CLOUD_TAU": np.full((2, 3, 1), 0.1),
        "NATIVE_CLOUD_SSA": np.full((2, 3, 1), 0.5),
        "NATIVE_CLOUD_G": np.full((2, 3, 1), 0.3),
        "CU_CLOUD_SSA": np.full((2, 3, 1), 0.4),
        "CU_CLOUD_G": np.full((2, 3, 1), 0.2),
        "CU_RL_USED": np.full((2, 3, 1), 10.0),
        "CU_DI_USED": np.full((2, 3, 1), 20.0),
    }
    with path.open("w", encoding="ascii") as stream:
        stream.write(f"RRTMGP_RESULT_V1\n{phase} 2 3\n")
        for name in names:
            values = records[name]
            stream.write(f"{name} {values.shape[0]} {values.shape[1]} {values.shape[2]}\n")
            stream.write(" ".join(f"{x:.8e}" for x in values.ravel(order="F")) + "\n")


def write_input(path: Path, version: str, phase: str) -> None:
    nc, nl, ngpt, nbnd = 2, 3, 112, 14
    records: dict[str, np.ndarray] = {
        "SOLAR": np.array([[1361.0]]), "CF": np.full((nc, nl), 0.5),
        "CU_POPULATION_POLICY": np.array([[1.0]]), "CU_RADIUS_POLICY": np.array([[1.0]]),
        "CU_OCCURRENCE_POLICY": np.array([[1.0]]), "CU_LWP": np.full((nc, nl), 0.01),
        "CU_IWP": np.full((nc, nl), 0.02), "CU_REL": np.full((nc, nl), 10.0),
        "CU_REI": np.full((nc, nl), 20.0), "ICE_ROUGHNESS": np.array([[1.0]]),
        "GRAVITY": np.array([[9.8]]), "CP_DRY": np.array([[1004.0]]),
        "MOL_WEIGHT_DRY": np.array([[28.97]]),
    }
    if version == "RRTMGP_REPLAY_V10":
        for name in ("VMR_CFC11", "VMR_CFC12", "VMR_CFC22", "VMR_CCL4"):
            records[name] = np.zeros((nc, nl))
    else:
        records.update({
            "SW_BAND_PARTITION": np.array([[1.0]]), "SW_DIRECT_PREDELTA_POLICY": np.array([[1.0]]),
            "TOA_GPOINT": np.ones((nc, ngpt)), "RAW_GAS_TAU": np.ones((nc, nl, ngpt)),
            "MCICA_MASK": np.ones((nc, nl, ngpt)),
            "RAW_NATIVE_CLOUD_TAU": np.full((nc, nl, nbnd), 1.0 + 2.0**-25),
            "RAW_CU_CLOUD_TAU": np.full((nc, nl, nbnd), 2.0**-25),
            "RAW_PRECIP_TAU": np.zeros((nc, nl, nbnd)),
            "RAW_GRAUPEL_TAU_EXT": np.zeros((nc, nl, nbnd)),
            "RAW_HAIL_TAU_EXT": np.zeros((nc, nl, nbnd)),
            "BAND_LIMS_GPOINT": np.array([[8 * b + 1 for b in range(nbnd)],
                                           [8 * (b + 1) for b in range(nbnd)]], dtype=float),
            "BAND_LIMS_WAVENUMBER": np.array([[100.0 + 100.0 * b for b in range(nbnd)],
                                               [200.0 + 100.0 * b for b in range(nbnd)]]),
            "VISIBLE_WEIGHT": np.ones((nbnd, 1)),
        })
        records["RAW_CLOUD_TAU"] = (records["RAW_NATIVE_CLOUD_TAU"] +
                                    records["RAW_CU_CLOUD_TAU"]).astype(np.float32).astype(np.float64)
    with path.open("w", encoding="ascii") as stream:
        stream.write(f"{version}\n{phase} {nc} {nl} 1 37 1\n")
        for name, values in records.items():
            stream.write(name + " " + " ".join(str(d) for d in values.shape) + "\n")
            stream.write(" ".join(f"{float(x):.17e}" for x in values.ravel(order="F")) + "\n")


def main() -> int:
    validate_cu_population_records(make_records(), 2, 3, "LW", "RRTMGP_REPLAY_V10", Path("lw.input"))
    validate_cu_population_records(make_records(sw=True), 2, 3, "SW", "RRTMGP_REPLAY_V11", Path("sw.input"))
    fixture = make_records()
    raw = {name: value[0, :].copy() for name, value in fixture.items() if value.ndim == 2}
    raw["QC"] = raw["NATIVE_QC"].copy()
    raw["QI"] = raw["NATIVE_QI"].copy()
    adapter = {"CU_LWP": fixture["CU_LWP"][:1, :], "CU_IWP": fixture["CU_IWP"][:1, :],
               "CU_REL": fixture["CU_REL"][:1, :], "CU_REI": fixture["CU_REI"][:1, :]}
    adapter.update({name: fixture[name] for name in
                    ("CU_POPULATION_POLICY", "CU_RADIUS_POLICY", "CU_OCCURRENCE_POLICY")})
    validate_cu_population_raw(raw, adapter, 3, Path("synthetic.raw"))

    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "input"
        for version, phase in (("RRTMGP_REPLAY_V10", "LW"), ("RRTMGP_REPLAY_V11", "SW")):
            write_input(path, version, phase)
            parsed_phase, nc, nl, *_rest, parsed = read_input(path)
            assert parsed_phase == phase and (nc, nl) == (2, 3)
            if version == "RRTMGP_REPLAY_V11":
                expect = (parsed["RAW_NATIVE_CLOUD_TAU"] + parsed["RAW_CU_CLOUD_TAU"])
                expect = expect.astype(np.float32).astype(np.float64)
                assert np.array_equal(parsed["RAW_CLOUD_TAU"], expect)
        write_input(path, "RRTMGP_REPLAY_V10", "LW")
        lines = path.read_text(encoding="ascii").splitlines()
        path.write_text("RRTMGP_REPLAY_V9\n" + "\n".join(lines[1:]) + "\n", encoding="ascii")
        try:
            read_input(path)
        except ReplayError:
            pass
        else:
            raise AssertionError("legacy V9 accepted V10 CU records")

    broken = make_records()
    del broken["CU_REI"]
    expect_error(broken, "LW", "RRTMGP_REPLAY_V10")
    broken = {name: value.copy() for name, value in raw.items()}
    broken["SOURCE_QC"][0] += 1.e-4
    try:
        validate_cu_population_raw(broken, adapter, 3, Path("corrupt.raw"))
    except ReplayError:
        pass
    else:
        raise AssertionError("corrupt augmented source q was accepted")
    broken = {name: value.copy() for name, value in raw.items()}
    broken["CU_REJECTED_GRID_IWP"][0] += 1.0
    try:
        validate_cu_population_raw(broken, adapter, 3, Path("corrupt.raw"))
    except ReplayError:
        pass
    else:
        raise AssertionError("corrupt rejected CU path was accepted")
    broken = {name: value.copy() for name, value in raw.items()}
    broken["DP_CU"][1] = np.float32(0.375)
    broken["SH_CU"][1] = np.float32(0.375)
    broken["CF_CU"][1] = 0.75
    try:
        validate_cu_population_raw(broken, adapter, 3, Path("cf-overrun.raw"))
    except ReplayError:
        pass
    else:
        raise AssertionError("CU cloud fraction exceeding total cloud fraction was accepted")
    broken = {name: value.copy() for name, value in raw.items() if name != "DRY_MASS_KG_M2"}
    try:
        validate_cu_population_raw(broken, adapter, 3, Path("missing.raw"))
    except ReplayError:
        pass
    else:
        raise AssertionError("missing dry-mass provenance was accepted")
    broken = make_records(sw=True)
    broken["RAW_CU_CLOUD_TAU"][0, 0, 0] += 0.1
    expect_error(broken, "SW", "RRTMGP_REPLAY_V11")
    broken = {name: value.copy() for name, value in raw.items()}
    broken["DRY_MASS_KG_M2"][0] = np.nan
    try:
        validate_cu_population_raw(broken, adapter, 3, Path("nan.raw"))
    except ReplayError:
        pass
    else:
        raise AssertionError("nonfinite dry mass was accepted")

    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "partial.result"
        write_result(path, "LW", ("NATIVE_CLOUD_TAU",))
        try:
            read_result(path)
        except ReplayFormatError:
            pass
        else:
            raise AssertionError("partial LW component result was accepted")
        path = Path(temp) / "complete.result"
        write_result(path, "LW", ("GAS_TAU", "CLOUD_TAU", "PREPARED_TAU", "MASK", "TOTAL_TAU",
                                   "RL_USED", "DI_USED", "DS_USED", "UP", "DN", "HR", "UPC", "DNC", "HRC",
                                   "NATIVE_CLOUD_TAU", "CU_CLOUD_TAU", "CU_RL_USED", "CU_DI_USED"))
        parsed = read_result(path)
        assert "CU_CLOUD_TAU" in parsed["sections"]
    print("CU population replay contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
