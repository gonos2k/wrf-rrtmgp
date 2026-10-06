# LBLRTM selected-layer CO2 coupling ablation

This package preserves one bounded ON-only diagnostic run against the same held LBLRTM case. The saved R3 event trace records omission of the selected CO2 coupling updates, and the selected `ODdeflt_021` output records the resulting raw layer-21 change. The full-file OFF comparison remains a failure because its six timestamp bytes differ; this ON result does not waive that gate.

The run used one solver invocation and returned RC 0. The trace parser independently reproduces the selected event counts from the compressed OFF and ON traces. The selected-layer decoder independently reads the two compressed layer-21 records. It finds 464,329 samples in each, 654 negative OD samples in OFF (minimum −4.884429085432753) and 430 in ON (minimum −0.030110255894620557); 1,331 samples changed, corresponding to 9,233 raw sample bytes. The three declared probe values are exact grid samples. These measurements describe this one held case only.

The captured payload comparison reports all 44 nonselected layer payloads byte-identical outside the source-defined HTIME field. Their raw files are not included here, so the portable verifier checks that claim against the frozen comparison receipt rather than recomputing it. The original OFF full-file gate also remains a preserved failure. Negative optical depth remains present in the ON result, and the overall negative-OD reference gate remains **NOT PASS**.

The archive includes only the two selected-layer OD files, the paired R3 traces, and the small paired panel traces. It omits the other 44 OD files, the full TAPE3 input, the executable, and runtime libraries. The manifest lists external pins for those artifacts. Verification is standard-library-only and does not run LBLRTM, compile code, or fetch external files.

The LBLRTM source file, focused patch, source review, and the source license are included. Build and runtime receipts identify the captured source/executable/library closure; the large executable and libraries themselves remain external. The result is a diagnostic about this selected coupling intervention, not a spectroscopy accuracy result, general line-mixing conclusion, or physical acceptance.

Run the saved-evidence verifier from any working directory:

```sh
python3 -I -S validation/rrtmgp37/lblrtm-coupling-ablation-on-only/verify_saved.py \
  --expected-manifest-sha256 MANIFEST_SHA256 \
  --report /tmp/lblrtm-coupling-ablation-verification.json
```

The GitHub workflow invokes the same verifier with the frozen manifest digest. Its report is written outside the evidence directory, so it does not alter the closed package roster.
