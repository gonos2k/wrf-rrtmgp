# CF0 sidecar with retained V10/V11 CU replay inputs

This test-only extension permits the existing CF0 precipitation audit sidecar with RRTMGP replay V10 (LW) and V11 (SW). The replay input is held byte-for-byte; only the separate sidecar file carries the occurrence-one audit path. Existing V10/V11 CU policies, profiles, raw optical decomposition, native mass, masks, frozen records, and (for V11) direct-diagnostic provenance remain mandatory and are still validated by `reference_column`.

The Fortran change only widens the sidecar's format gate to V8–V11 and removes the former blanket CU rejection. The sidecar remains restricted to one column, finite nonnegative paths, one species, occurrence exactly one, and positive paths only where CF is zero. Native prefix and V11 direct-diagnostic checks remain active. Python validation now checks a paired V10/V11 input's phase/depth/native CF against its raw capture and requires the complete CU bundle; for V11 it also requires the direct-diagnostic/raw optical provenance records. It hashes the held CU policy/profile values for the validation receipt and does not rewrite the replay input.

The additional audit precipitation object is injected into the all-sky optical state after the ordinary clear-sky radiation solve. Consequently, clear-sky outputs stay unchanged by construction when the sidecar is active. They cannot be interpreted as evidence that the falling precipitation has no clear-sky effect.

The occurrence-one object is an explicit sensitivity counterfactual. No authoritative precipitation occurrence fraction was found, so this test interface does not define a production occurrence policy or physical accuracy claim. The selected V10/V11 snow sample has an extremely small path; it is a low-signal fixture rather than a representative snow case.

Offline controls (no compiled reader or solver calls):

```sh
cd WRF/test/rrtmgp
PYTHONDONTWRITEBYTECODE=1 python3 -B test_cf0_cu_precip_sidecar.py
PYTHONDONTWRITEBYTECODE=1 python3 -B test_cf0_precip_sidecar.py
```
