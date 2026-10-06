#!/usr/bin/env python3
"""Generate isolated adapter source copies with one anchored nonfinite fault."""
import argparse
import hashlib
import json
from pathlib import Path


def replace_occurrence(source: str, anchor: str, replacement: str, occurrence: int) -> str:
    count = source.count(anchor)
    if count < occurrence:
        raise ValueError(f"expected at least {occurrence} copies of source anchor, found {count}: {anchor!r}")
    start = 0
    position = -1
    for _ in range(occurrence):
        position = source.find(anchor, start)
        start = position + len(anchor)
    return source[:position] + replacement + source[position + len(anchor):]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    source = args.source.read_text()
    if "ONLY: ieee_is_finite" not in source:
        raise SystemExit("adapter ieee_arithmetic import anchor changed")
    base = source.replace("ONLY: ieee_is_finite", "ONLY: ieee_is_finite, ieee_value, ieee_quiet_nan", 1)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    lw_rte = "CALL require(rte_lw(atmos,.FALSE.,source,emissivity,flux))"
    sw_rte = "CALL require(rte_sw(atmos,.FALSE.,REAL(mu0,wp),toa,albdir,albdif,flux))"
    heating = "CALL require(compute_heating_rate(fu,fd,REAL(plev,wp)*100._wp,heat))"
    if base.count(lw_rte) != 2 or base.count(sw_rte) != 2 or base.count(heating) != 4:
        raise SystemExit("adapter RTE/heating anchor counts changed; refusing to inject at an ambiguous source location")

    cases = {
        "lw_clear_flux_nan": (replace_occurrence(
            base, lw_rte,
            lw_rte + "\n    fu(2,1)=ieee_value(0._wp,ieee_quiet_nan)", 1),
            lw_rte, 1, "inject_wp_quiet_nan fu(2,1) after clear LW RTE"),
        "sw_allsky_heat_nan": (replace_occurrence(
            base, heating,
            heating + "\n    heat(2,2)=ieee_value(0._wp,ieee_quiet_nan)", 4),
            heating, 4, "inject_wp_quiet_nan heat(2,2) after all-sky SW heating"),
        "lw_allsky_default_overflow": (replace_occurrence(
            base, lw_rte,
            lw_rte + "\n    fu(2,1)=REAL(HUGE(1.),wp)*2._wp", 2),
            lw_rte, 2, "inject finite wp fu(2,1)=2*HUGE(default REAL) after all-sky LW RTE"),
    }
    outputs = {}
    for name, (text, anchor, occurrence, injection) in cases.items():
        path = args.output_dir / f"module_ra_rrtmgp_{name}.F"
        path.write_text(text)
        print(f"{name} {path}")
        outputs[name] = {
            "generated_source": path.name,
            "generated_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "anchor": anchor,
            "anchor_occurrence_1based": occurrence,
            "anchor_count_in_base": base.count(anchor),
            "injection": injection,
        }
    manifest = {
        "schema": "RRTMGP_OUTPUT_FINITE_FAULT_SOURCES_V1",
        "original_source": args.source.name,
        "original_source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "generated_sources": outputs,
    }
    manifest_path = args.output_dir / "output-finite-fault-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"manifest {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
