# Independent BON LW gas-opacity reconstruction: design v3

This is a source-faithful design for independently reconstructing the LW gas-optics absorption total for one retained nighttime BON diagnostic column. It contains no pfrac or opacity calculation and records no replay, compilation, solver, or WRF run. It is not an accuracy test.

The held V10 column contains 45 solver diagnostic layers: 32 native WRF levels plus 13 upper extensions. The supplied mass carrier has 45 rows; this does not make 45 layers native. Production uses 11 ordered LW gas names, including four CFC profiles from the input and a fixed N2 VMR of 0.7808 from the saved command line.

The reconstruction must preserve coefficient-gas-name reduction, key-species remapping, the single source-specific `(0,0)->(2,2)` flavor rewrite, and distinct lower/upper minor tables. Minor table interval names are identifiers: map `minor_gases_*` through `identifier_minor` to `gas_minor`, filter against available gas names, then compact coefficient contributors and subtract removed preceding g-point counts from retained starts. The companion `minor-metadata-inventory-v1.json` records the exact interval map, g-point windows, density/complement/scaling-gas flags, and adjusted coefficient starts for this host gas set.

The pinned LW table has no Rayleigh variables or Rayleigh-named dimensions. Its coefficient loader leaves Rayleigh arrays unallocated; the frontend then takes the no-Rayleigh branch and writes absorption directly into `optical_props%tau`. Thus the pinned saved `GAS_TAU_RAW` can be compared directly with the ordered sum of reconstructed major and minor absorption. This is specific to this LW file and call. The saved output still lacks a separate major/minor/species split, so only the final ordered sum has a stored numeric target.

Do not transfer the legacy band-12 zero-fraction pattern to the GP table. The prior GP pfrac artifact has nonzero upper-layer fractions while the saved GP gas tau is zero there; the legacy fraction record has its own zero-fraction behavior. The opacity reconstruction must follow the GP coefficients and inputs without normalizing fractions or borrowing legacy masks.

See `design-v3.json` for exact source/input/coefficient/result pins, dimensions, loading and interpolation rules, source lines, and comparison limits. V1 and v2 are preserved as historical records; v3 supersedes their Rayleigh and band-12 interpretations.
