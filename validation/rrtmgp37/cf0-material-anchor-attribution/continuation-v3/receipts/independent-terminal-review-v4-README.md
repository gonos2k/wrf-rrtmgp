# Independent terminal checks for captured CF0 material anchors

`analyze_terminal.py` is an offline checker for the two captured column states and four rain/snow × LW/SW increments. It makes no solver, build, or WRF calls. It is intentionally separate from the execution runner's `positive_validate` routine. `independent-terminal-review-v4.json` is the final receipt; v1–v3 are retained earlier checker iterations. The original v1 campaign receipt remains a parser `FAILED_STOPPED` even though both first subprocesses returned zero; its outputs are re-parsed here and six later calls have their own passing continuation receipt.

It derives LW/SW audit optics from the serialized occurrence-one sidecar paths and captured native snow radius, reproduces the source default-real coefficient conversion for SW, checks band-to-g-point mapping and combined optical moments, checks the pre-delta direct profile against exact Beer-Lambert attenuation from the independently recomputed gray raw audit tau, checks flux-divergence heating using captured gravity, heat capacity, and pressure interfaces, and requires common held components/clear outputs to remain byte-identical. Each fresh baseline is also checked bitwise against its saved same-anchor reference.

The reference-column file is checked against the build receipt's actual `source_files` record. The precipitation helper copy in the actual source tree is checked against the linked-source manifest hash. This is a source and replay consistency check, not independent external optical truth. The occurrence-one sidecars remain experimental counterfactuals on two single-column captures. No domain-wide, production-policy, or forecast-accuracy conclusion follows. The independent checker itself makes no new reference invocation.

Run only after the continuation receipt is terminal:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 build/udm37-cf0-material-anchor-independent-terminal-v1/analyze_terminal.py
```

The script writes `independent-terminal-review-v4.json` once and refuses to overwrite it.
