# Independent BON night terminal review

PASS_SCOPED_READONLY_TERMINAL. The retained three-arm execution receipt is unchanged (SHA 00d7abb5b6f92e1dc4a2b07724fbf1fe6a6c2853c4614d4a59e2af0a71ef6240). OFF, ON_native4_0 and ON_native4_1 each launched exactly once and completed RC 0 without timeout. This review launched zero forecasts, REAL, compilers, solvers or replays. Root reports cumulative forecasts 97; three belong to this campaign.

Readback revalidated source/configuration/ELF/48-library and stage pins, actual PID/RC records, serial success markers, nine native NetCDF files and 54 production trace files. Each arm has two 225-variable endpoint histories and a 667-variable final checkpoint, all raw/decoded numeric arrays finite without fills/masks. Both ON arms match OFF for raw bytes, variable sets, dimensions/unlimited flags, dtypes, full variable/global attributes, data_model and whole-file SHA. All six raw/input/result triples per arm are bitwise identical.

The actual six LW calls are steps 721, 731, 741, 751, 761 and 771, with source seconds 43200 through 46200. OFF selected the first observed call for the single LW export at domain 1, i=13, j=46. No SW solver capture or export exists at night; zero SW audit rows are clock-joined bookkeeping. Each ON CSV has 840 rows, 128 samples, zero seed standard deviations, and identical engine37 and engine4 value/mean/SD fields across the two legacy radius modes.

Across six calls, surface downward LW engine37 minus engine4 is +1.2423858643 to +1.2472686768 W/m². TOA upward contrast decreases from +0.1581420898 to +0.0505523682 W/m². Maximum absolute native-layer heating contrast is 0.0788683891 K/day. These are same-state contrasts, not measured accuracy errors.

Native and extended cloud fractions, cloud liquid/ice, sampled cloud masks, native/CU cloud optical depths and rain/snow radiative paths are exactly zero. Frozen graupel/hail optical depths are tiny but nonzero: maximum 5.6602135279e-21. Allsky and clear engine37 DN/UP/HR outputs are bitwise equal. This equality does not prove zero physical frozen effect. The first legacy export likewise has zero cloud masks and cloud optical depths, with allsky/clear downward flux equality.

Sixteen first-call input joins (pressure, temperature, surface temperature/emissivity and gas VMRs) are IEEE64-equal between GP capture and the legacy export. Molecular dry-column amounts differ despite matching molecule/cm² units: legacy/GP is 1.00034308–1.00035063 in 32 native layers and 1.00034701 in 13 extensions. This leaves gas-input construction and engine/spectral effects combined; no dry-mass-only causal experiment was performed.

For these six inactive-cloud calls, radius conversion and stochastic cloud sampling cannot explain the observed same-state contrast: both radius arms agree and seed spread is zero. This does not explain or resolve the common observed BON/PSU LW bias across the full day, other columns, thermodynamic/surface/observation mismatches, or physical accuracy. Frozen optics=1 and roughness=1 remain experimental. CSV is allsky only, and the 128 seed statistics are descriptive, not an IID confidence interval.

The old checkpoint lacks CF3 diagnostics. Three explicit missing-diagnostic warnings per arm are preserved; there is no claim of exact restoration of those historical diagnostic fields. The private prototype's incorrect exactly-zero frozen-opacity assertion was preserved and corrected in analysis only; original models, captures and receipts were untouched.

`review.py` performs only read-only native-file analysis and normalized ldd closure checking. It uses pinned pre-existing parsers/quality helpers. The final report is immutable; rerunning its main routine would refuse to overwrite the existing report.
