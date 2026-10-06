# First-step MPI decomposition comparison

The PNG and PDF compare existing PR21 MPI1 (one rank) and MPI4 (2×2 ranks) histories at `2010-06-11_12:01:00`. Each panel includes all 189×289 mass-grid cells, with dashed lines between columns 145/146 and rows 95/96. Inputs have matching namelists, grid coordinates, and 20 km spacing; exact paths and SHA-256 hashes are in `receipt.json`.

SWDOWN is plotted as signed MPI4−MPI1 in W m⁻². T is the maximum absolute perturbation difference over all 39 native mass levels in K. QNCLOUD and QNCCN are shown as maximum absolute differences of the stored history fields over 39 native levels, in their Registry-declared `# kg(-1)` units. No density conversion is applied. The Registry metadata says number per kg, while the UDM input/output path may use a number-concentration convention; that convention has not been independently resolved, so these are stored-field differences only and should not be interpreted as validated number-density differences.

The magnitude panels use a full-grid maximum and a power color normalization (gamma 0.18); zero and boundary cells remain present. The maps identify spatial association with decomposition seams only. They do not establish a cause, represent an observational bias, or imply forecast accuracy. MPI4 and MPI1 are separate trajectories, so differences can include evolving coupled-state effects.

Reproduce with:

```sh
python3 build/udm-mpix-diagnosis/plots/plot_mpi_decomposition_diff.py
```

The earlier density-converted rendering is retained outside this curated bundle at `build/udm-mpix-diagnosis/plots/superseded-density-converted/` for audit history only; its QN panels should not be used as validated number densities.
