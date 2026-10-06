# UDM activation and density contracts

The native number equations and the density passed by the host must agree before
a difference between RRTMG4 and RRTMGP37 can be attributed to radiation physics.
This package tests two local UDM contracts using extracted default-REAL source.
It changes no production microphysics, dynamics, radius, or radiation policy.

## Active density path

The source audit and independent review follow the actual split-microphysics
call order. `moist_physics_prep_em` overwrites `grid%rho` with
`1/(al+alb)` immediately before `microphysics_driver` passes it to UDM as `DEN`.
Both moist-potential-temperature branches of the WRF equation of state identify
`al+alb` as dry-air specific volume. Earlier unsplit physics instead uses
`(1+qv)/ALT`; that is a different event and cannot be substituted for the density
at the UDM call.

UDM computes

```text
DEND = (p/T - DEN*Rv)/(Rd-Rv)
```

and uses `DEND` in precipitation mass and number sedimentation. For a simultaneous
ideal dry-air/vapour mixture, this recovers dry density if `DEN` is the total
dry-air plus vapour gas density. Supplying dry density instead gives

```text
DEND/rho_d = 1 + qv*Rv/(Rd-Rv) = 1 - 2.643757159221*qv
```

for the binary64 interpretation of the pinned `Rd=287`, `Rv=461.6` constants.
The density fixture uses three dry densities, five vapour mixing ratios and two
temperatures: 30 manufactured states at each optimization. It checks the dry
limit, the active host reciprocal-alpha assignment, and both conditional `DEN`
interpretations against an independent analytic oracle. The fresh runner
extracts the actual pinned statements and checks the constants before compiling.

This is a source compatibility finding. It is not a measured model density error
or forecast error. Existing radius producer packets omit simultaneous pressure
and vapour and are captured after microphysics; later radiative fields cannot
fill that missing entry checkpoint. The next runtime check must record
`p,T,qv,DEN,DEND` at the same UDM entry event. Changing `DEN` globally is not a
supported repair: other equations already use dry-mass mixing ratio times `DEN`
to form mass per volume.

## Activation process

The second fixture inserts the pinned native 13-line CCN-activation IF block
without changing its statements. Its local water source is embryo mass times
the activation number increment divided by `DEN`. Three densities distinguish
the conditional volume-number relation `dm=m_emb*dN/rho` from the conditional
mass-specific relation `dm=m_emb*dN`; at unit density these coincide.

At each density it tests inactive saturation, uncapped activation, a vapour cap,
and the cloud/CCN number floors. The low-CCN floor case is synthetic branch
isolation, outside the ordinary initialized reservoir range. The water-cap and
floor outcomes are kept separate from number-unit closure. The process increment
and stored state are distinct: subtracting two default-REAL states can lose
precision, so the oracle explicitly accounts for state-rounding bounds.

These checks determine the algebra of this block, not the units of every initial,
boundary or restart number field. They do not establish a radiation PSD or
authorize a density multiplier. Saturation construction, cloud-top selection,
later condensation and whole-step microphysics are outside the extracted block.

## Reproduce

Authenticate the saved evidence without invoking a compiler, model or RTE:

```sh
python3 -I -S validation/rrtmgp37/activation-density-contract/verify.py
```

Compile and execute each fixture in a new output directory:

```sh
python3 -I -S validation/rrtmgp37/activation-density-contract/activation.py \
  --source-root "$PWD" --output-dir build/activation-contract-fresh
python3 -I -S validation/rrtmgp37/activation-density-contract/density.py \
  --source-root "$PWD" --output-dir build/density-contract-fresh
```

Each runner uses GNU default REAL at O0 and O2, records subprocess return codes
before parsing, refuses to overwrite an output directory, and preserves failed
gates. Earlier local fixture/oracle development failures are archived separately;
they are not native model failures. CI authenticates the archive and executes
both fresh source fixtures. No WRF forecast or RTE solve is performed by this
package. Production constants, strict reference failures and RRTMG4 are unchanged.
