# UDM27 native dry-air gas columns: scoped validation

Option 37 now obtains native-layer dry molecular columns from the WRF dry-layer mass already used for hydrometeor paths. The preceding pressure/VMR reconstruction is retained above the WRF model top and for historical callers without a native matrix. This removes inconsistent mass denominators; it does not alter pressure/temperature interpolation or the pressure-divergence heating denominator.

The tested sources were uncommitted changes on parent `babe0afbe77c2dd28050e60acdbafefd56221151`. `provenance.json` binds the source and binary hashes; `publication-manifest.json` binds published artifacts. Failed intermediate executions remain in the local build workspace and are superseded by the final receipts here. The final serial WRF executable SHA256 is `88193f03e431fc8c7f8e8f565d9f66240d66c882c6bbb403dd70560d9a501d55`; independent reference SHA256 is `e72d5cfb60438f7d4d0e5ab675f2050584ab599371f4c5b23edf905ae4723480`.

## Final checks

| Check | Result and scope |
| --- | --- |
| GNU checked standalone suite | 68/68 PASS, including actual two-column LW/SW adapter and V6 reference replay with unequal VIS/NIR albedos |
| Native matrix failure cases | 21 adapter cases: shape/empty/too-wide/zero/negative/NaN/Inf, each LW/day SW/night SW; 7 malformed reference inputs rejected; wrong result shape rejected |
| Actual WRF source mapping | Control/mixed first-call raw native masses independently reconstructed from same-run MU/MUB/DNW/C1H/C2H; native matrix exactly matches raw; molecular-column formula relative error ≤2.13e-16 |
| Model-top extension | 59 native layers, LW 44 extension layers, SW 1; helper pressure/VMR formula preserved |
| Serial UDM SCM | One-minute control/mixed, initial and second-call V6 replay; two capture choices give identical 210-array history |
| Existing option 4 | Each case's 208 arrays bitwise equal to saved parent-PR16 option-4 histories; this is not a fresh pristine-WRF comparison |
| Same-live-state physics audit | 8 seeds, control/mixed, all-call independent replay; audit enabled/disabled histories agree over 210 arrays per case; observational accuracy is not measured |
| Serial restart | Control, mixed and retimed year/day boundary, 120 s integration, 60 s checkpoint; 13 times ×210 common variables agree bitwise in each case |

The final runtime receipt independently checks history attributes `MP_PHYSICS=27`, `RA_LW_PHYSICS=37`, `RA_SW_PHYSICS=37` and executable hashes. The calendar case checks restart behavior at a retimed boundary, not meteorological validity of that date. These new results are serial and short; they do not extend prior MPI/OpenMP evidence to this patch.

The strict NaN tests exposed Fortran's lack of guaranteed short-circuit evaluation. Native mass finite checks now precede positivity comparisons in both adapters, the UDM builder and the reference. V6 also follows the existing V3–V5 SW transition-band convention in both surface albedo and diagnostics. The unequal-albedo replay fixture verifies that convention.

## Isolated change in gas amount

`run_counterfactual.py` replays the same four first-call control/mixed LW/SW captures twice. It removes only the V6 native matrix and changes the magic to V5, preserving every other input byte, host constant and McICA seed. Both standalone calculations return full precision. Their difference isolates the new mass denominator; the separate actual-WRF-minus-fallback comparison also includes REAL32 return rounding.

| Native minus fallback, W m⁻² | Surface downward | TOA upward |
| --- | ---: | ---: |
| Control LW | +7.43e-6 | +2.15e-6 |
| Control SW | +4.46e-6 | −1.57e-6 |
| Mixed LW | +1.03e-5 | +2.47e-5 |
| Mixed SW | +4.24e-5 | −2.41e-5 |

Full-profile pure-reference maximum absolute flux difference is 1.823e-4 W m⁻² and heating difference is 4.691e-5 K day⁻¹. Gas columns and gas optical depths above the native prefix are bitwise unchanged in all four cases. These small case-specific effects cannot explain the earlier tens-of-W m⁻² cloud differences; they are not a bound for other atmospheric states.

## Reproduction

From repository root with GNU, NetCDF, Python NumPy/netCDF4 and a configured serial WRF build:

```bash
cd WRF
csh -f ./compile -j 12 em_scm_xy
cd ..
cmake -S WRF/test/rrtmgp -B build/native-gas-test -DRRTMGP_DATA_DIR="$PWD/WRF/run"
cmake --build build/native-gas-test --parallel 4
ctest --test-dir build/native-gas-test --output-on-failure
python3 WRF/test/rrtmgp/test_udm_scm.py build/native-gas-scm \
  --reference-executable build/native-gas-test/reference_column
python3 WRF/test/rrtmgp/test_native_gas_columns.py \
  --capture-dir build/native-gas-scm/mixed/ra37-call1/capture \
  --output build/native-gas-scm/mixed-gas-columns.json
python3 validation/rrtmgp37/native-gas-columns/run_counterfactual.py \
  --reference build/native-gas-test/reference_column --data WRF/run \
  --control-capture build/native-gas-scm/control/ra37-call1/capture \
  --mixed-capture build/native-gas-scm/mixed/ra37-call1/capture \
  --out-dir build/native-gas-counterfactual
python3 validation/rrtmgp37/domain-calendar-seeds/run_restart_determinism.py \
  --repo . --baseline-root build/native-gas-scm \
  --output-root build/native-gas-restart --calendar-boundary
```

For strict standalone traps add `-DCMAKE_Fortran_FLAGS='-O0 -g -fcheck=all -ffpe-trap=invalid,zero,overflow -ffree-line-length-none'`; use a sufficient stack limit (the final run used `ulimit -s 65536`). To reproduce historical option-4 preservation, pass the saved parent control/mixed `--baseline-control`/`--baseline-mixed` directories to the SCM runner. A fresh checkout without those histories does not reproduce that assertion. Paths inside JSON receipts describe the original local run; the commands above use new output directories.

## Still open

Graupel optical treatment, positive hail support, UDM size metrics/PSD coupling, cloud-fraction and temporal McICA policies, true unscattered direct flux, complete native thermodynamic tendency mapping, and completed long real-data UDM forecasts remain separate work. Positive hail still fails explicitly; graupel remains diagnosed and omitted. This PR does not declare those physical differences normal or operationally validated.
