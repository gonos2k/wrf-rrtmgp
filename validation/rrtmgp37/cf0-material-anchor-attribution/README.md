# CF-zero material-precipitation replay audit

This package records eight standalone reference-column solver calls in two attempts. The first attempt launched two children, both returned zero, then stopped because its older output parser rejected `AUDIT_EXTRA_PRECIP_TAU`; the six unstarted calls were run once in a separate continuation. The original `FAILED_STOPPED` receipt is retained under `partial-run-v1/`; the continuation receipt and independent terminal review v4 are under `continuation-v3/receipts/`. Together the receipts account for eight distinct solver PIDs, all with return code zero. There were no WRF forecasts or builds in this experiment. The earlier v3 review is retained only as superseded provenance; v4 is authoritative and verifies the actual compiled `reference_column.f90` source record (SHA256 `6e82effd7d25242656858a8242c7e6941fced6aec0ec4d906762ef3ccb1b4ff0`) separately from the staged/copied source pins.

The experiment pairs each anchor only with itself: winter native-CU rain and low-cloud material snow, each in LW and SW. For a given pair, baseline and increment use the same captured input and raw state. The increment is an occurrence-one, single-species sidecar that restores positive precipitation paths omitted at CF=0. The sidecars preserve the original small positive values without a path cutoff. This is a diagnostic counterfactual, not a proposed production policy. The winter rain and low-cloud snow anchors are different states and are not compared as a controlled intervention.

| Anchor / phase | Surface down flux change (W m⁻²) | TOA up flux change (W m⁻²) | Native/engine heating L∞ change (K day⁻¹) |
|---|---:|---:|---:|
| Winter CU rain / LW | +0.0040442 | +0.0001643 | 0.0010806 |
| Winter CU rain / SW | −0.0341414 | −0.0029548 | 0.0062743 |
| Low-cloud snow / LW | +0.1700621 | −0.0344317 | 0.0774937 |
| Low-cloud snow / SW | −0.0136810 | +0.0077043 | 0.0010024 |

The response profiles and exact call/output pins are in `results/` and `eight-call-ledger-v2.json`; the compact independently checked metrics and optical assembly receipts are in `continuation-v3/receipts/`. The analyzer recomputes paired output differences from the preserved result files without launching a solver. The independent v4 review separately checks all four baseline/increment pairs, held components, flux/heating consistency, and precip optical assembly. Its LW total-optics check is a separate receipt. In SW, the sidecar helper applies the documented delta scaling, optical-depth and SSA floors, and SSA cap; therefore very small snow tails are retained as inputs but do not imply unfloored output optics.

The selected snow anchor has a small total path, including 12 positive native levels; its changes above are measured for this one low-cloud state and do not establish a general snow effect. The winter case retains its captured CU treatment. The sidecar insertion is downstream of cloud sampling and uses occurrence one for CF-zero layers; no result here establishes the physical correctness of that choice, domain-scale impact, or forecast skill. These are single-column reference replays using a test helper, not a production-model validation.

All four captures use the original frozen table, SHA256 `8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583` (58,629 bytes). The expanded table used in a separate executable build is not the runtime table for these captures. Source, table, input, raw capture, sidecar, command, process, and result identities are retained in the package receipts and `preparation/` provenance files.

Run `python3 -B analyze_eight_calls.py` from this directory to reproduce the paired JSON/CSV profiles. Run `python3 -B verify_package.py` to check the closed package manifest and compressed result identities. The `partial-run-v1/verify_partial.py` command verifies the historical two-call failure bundle only.
