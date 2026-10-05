# UDM liquid-radius moment contract

This package records a bounded source audit and analytic calculation. It distinguishes the native UDM liquid-radius formula from the effective radius of a gamma-shaped particle distribution; it does not establish which convention the pinned radiation ice/liquid lookup tables prescribe.

The source routine computes, before guards and clipping,

\[
r_{\mathrm{native}}=\frac12\left(\frac{L}{(\pi\rho_w/6)N_c}\right)^{1/3}.
\]

If `L` is condensate mass per volume and `Nc` is number per volume, this equals the spherical volume-mean radius `(M3/M0)^(1/3)`. That interpretation is conditional: Registry labels QNCLOUD as `# kg(-1)`, while UDM's equations and constants use it as a volumetric number concentration. The producer/consumer unit conversion and live value scale remain unresolved; do not infer a unit defect from the Registry label alone.

For the gamma distribution `n(r)=n0*r^nu*exp(-lambda*r)`, the conventional spherical effective radius is `M3/M2=(nu+3)/lambda`, while the volume-mean radius is `(M3/M0)^(1/3)`. Their ratio is `((nu+3)^2/((nu+1)(nu+2)))^(1/3)`. Across the autoconversion closure's `nu=2..15`, this analytic ratio ranges from 1.0600476039461897 to 1.2771823873225885. A 64-node Gauss-Laguerre quadrature independently closes the tested moments to at most `7.95e-14` relative error.

The gamma PSD appears in the autoconversion closure. This audit does not show that it is the PSD prescribed for radiation, so the ratio is a mathematical distinction, not a recommended correction. The core divides condensate by cloud fraction for in-cloud microphysics without a corresponding number-field division in that block; the post-step radius uses restored grid condensate and number state. No same-occurrence moment identity is claimed. Radius bounds/placeholders are excluded from the analytic identity. The 15 tabulated pairs are illustrative ideal calculations under explicit assumptions, not model samples or compiled UDM evaluations; finite-product gamma approximations, default-real constants, and runtime guards are not reproduced by those examples.

The pinned ice-LUT lineage evidence identifies the current table bytes and the historical diameter-coordinate rename. Its header metadata has 18 size levels and 3 roughness entries but no PSD or habit weights. Public documentation describes Yang et al. (2013) source data and a 14-to-18-size interpolation workflow; it does not identify the exact habit mixture or population-size equation for the pinned files. The PDF is not redistributed here. No radius multiplier or production-default change follows.

The available project report describes liquid Mie properties at 1-µm particle-size intervals mapped to 16 LW and 14 SW bands. It reports coefficients over radii 2.5–59.5 µm and a model LUT retaining 2.5–21.5 µm, while explicitly not treating liquid refractive-index temperature dependence. The cited paragraph does not specify a PSD or shape parameter that would make an API label such as “effective radius” a complete caller contract. These project-level statements are not an exact generator recipe or proof that the pinned LUT is monodisperse; the pinned-table population mapping remains unresolved.

## Primary records

- [Current archived source commit](https://github.com/gonos2k/wrf-rrtmgp/tree/85c1c0a19e64fa190c18fe32d2a11c5f9b3ea1e1/WRF/phys/module_mp_udm.F) and [the unchanged effective-radius routine at PR7](https://github.com/gonos2k/wrf-rrtmgp/blob/1a2cd8d11993a5fb829a5103c0775ff69f820244/WRF/phys/module_mp_udm.F); the local routine bytes match, which establishes source continuity only.
- [DOE/AER final report record](https://www.osti.gov/biblio/1663146), [official report PDF](https://www.osti.gov/servlets/purl/1663146), [pinned RRTMGP data commit](https://github.com/earth-system-radiation/rrtmgp-data/commit/ea788bb39876948fa8d2c235665ccff19b4686b5), and [table-format PR #10](https://github.com/earth-system-radiation/rrtmgp-data/pull/10). These records concern table lineage and reported processing, not proof of a native-radius contract.
- The source-review and independent-review JSON files in `evidence/` document the bounded source interpretation, corrected derivation, and review limits. `stage-identity.json` is a conditional algebraic identity, not a measured trajectory result.

## Reproduction and verification

The archived `derive_moments.py` and `moment-result.json` are byte-preserved from the original audit. The archived script uses the original audit-directory layout. For a portable fresh calculation, from the repository root run:

```sh
python3 validation/rrtmgp37/radius-moment-contract/reproduce.py \
  --wrf-worktree . --output /tmp/udm-radius-moments.json
```

This optional calculation requires NumPy. It reads the selected checkout's source files only to bind their hashes; it does not execute WRF or interpret runtime units. `--wrf-worktree` can point to another checkout, but its source hashes must match the frozen source review. The output path must not already exist.

The frozen source pins correspond to commit `85c1c0a19e64fa190c18fe32d2a11c5f9b3ea1e1`.
CI checks out that commit into `.radius-moment-historical-source`, separately from
the current checkout. All four file hashes are still checked; no frozen evidence
or numerical result is relabeled as current evidence.

```sh
python3 -I -S validation/rrtmgp37/radius-moment-contract/verify.py \
  --source-root /absolute/path/to/historical-checkout
python3 -I -S validation/rrtmgp37/radius-moment-contract/test_verify.py \
  --historical-source-root /absolute/path/to/historical-checkout
python3 validation/rrtmgp37/radius-moment-contract/reproduce.py \
  --wrf-worktree /absolute/path/to/historical-checkout --output /tmp/new-moments.json
```

Without `--source-root`, the verifier strictly compares the current checkout to
the historical pins and rejects a mismatch. An incorrect historical root also
fails. The optional numerical reproduction has the same historical source gate;
use the historical checkout for `--wrf-worktree` and a new output filename.

Independently, `current-source-contract.json` pins the four current files reviewed
at PR99 head `d3d8fa7dcc9246ebd739f96a21daa8739c955c54`. Only the microphysics driver
has an approved difference from the archive: the radius instrumentation. The
verifier requires those current pins and reports each current/archive match or
difference, both roots, and both commit references. This is source identity,
not proof of number units, a PSD contract, physical correctness or a live model
trajectory. Future source changes fail this current gate until explicitly reviewed
and recorded in the separate current contract; historical evidence stays unchanged.
`--current-source-root` selects that independently checked root (default: current
checkout); it does not relax either source gate.

Both pull-request and main-push workflow filters cover all four source paths.
The regression controls verify both filters, the historical checkout ref, correct
root selection, source/payload mutations and the approved current-source difference.

The byte-preserved frozen result reports a maximum quadrature relative error of
`7.949196856316121e-14`; the archive verifier checks that frozen value against
`8e-14`. A separate fresh calculation on the Mac Studio with NumPy 2.4.4 produced
`2.639645977691072e-13` (14 shape rows and 15 illustrative samples), within the
reproduction script's `5e-12` tolerance. These are different executions; the
fresh result is not tested against, and does not pass, the frozen `8e-14` bound.
Neither calculation establishes physical accuracy.

The CI verifier uses only Python's standard library and checks the package's closed file roster, hashes, source-review-to-checkout identity, and the frozen result's row counts and numeric bounds. It does not run the optional calculation, a model, or a radiation solver.

## Scope limits

- This is source interpretation plus a mathematical moment calculation, not a radiative accuracy test.
- It does not prove the autoconversion gamma distribution is the radiation PSD.
- It does not resolve QNCLOUD's unit convention, cloud-fraction convention across producer and consumer, or the prescribed liquid/ice effective-radius definition.
- It evaluates no optical tables, atmosphere, flux, tendency, forecast, or observation.
- It makes no production change and supports no physical correction by itself.
