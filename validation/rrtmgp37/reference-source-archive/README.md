# Historical `reference_column` source archive

`reference_column.f90` is the exact SHA-256 `6e82effd7d25242656858a8242c7e6941fced6aec0ec4d906762ef3ccb1b4ff0` source recorded by the retained BON-night replay, dry-column attribution, and LW-transport verifier packages. It is a historical V10-era reader snapshot; it is not the current reader after the N2 trace/schema work.

The retained LW-transport package also pins the historical adapter `WRF/phys/module_ra_rrtmgp.F` at SHA-256 `b3932fa4e88202d5fe0fb660764bec9a07d031c03b501c20ee6ef259828ffa69`. That exact adapter source is archived in the adjacent SHA-addressed directory so the historical package can still be checked after the live N2 branch changes the adapter. The archived snapshots are only supplied for dependency identities explicitly recorded in the old package manifests.

Run the additive, offline checker with:

```sh
python3 validation/rrtmgp37/reference-source-archive/test_verify_historical_packages.py
python3 validation/rrtmgp37/reference-source-archive/verify_historical_packages.py
```

The checker verifies both SHA-addressed source archives, hash-checks each package's recorded repository dependencies, creates a temporary repo-shaped mapping with historical snapshots substituted where the recorded source identity requires it, and calls the three existing `verify.py` entry points unchanged. It does not edit their package payloads, receipts, manifests, source trees, or builds. It invokes no compiler or solver. The old one-use replay runner remains a historical artifact and is not reset or reused.

For future source versions, add a separate SHA-addressed snapshot and an explicit mapping entry. Never silently resolve a historical reader dependency to whatever happens to occupy the current source path.
