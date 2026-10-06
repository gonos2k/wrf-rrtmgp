# Saved UDM radius producer/consumer contract

The optional serial trace writes `RRTMGP_UDM_RADIUS_V1` packets after the UDM
call returns to the microphysics driver. The six header integers are domain,
producer step, i, j, kts and kte. The packet retains returned native condensates,
number concentration, density, temperature, three radii and the UDM CF tags.
This is a post-UDM callback snapshot; it is not an independent instrument inside
the effective-radius routine or a proof that the collision PSD is the radiation
PSD. It does not settle the physical units of Nc.

For a serial diagnostic run, use these capture controls:

```sh
export WRF_RRTMGP_CAPTURE_DIR=/absolute/existing/capture-directory
export WRF_RRTMGP_CAPTURE_UDM_RADII=1
export WRF_RRTMGP_CAPTURE_ALL=1
export WRF_RRTMGP_COLUMN_I=13
export WRF_RRTMGP_COLUMN_J=46
```

The capture directory must already exist. Capture supports neither MPI nor more
than one OpenMP thread. Leaving the radius selector unset preserves the disabled
path.

The following command reads saved files and creates a new result file:

```sh
python3 -I -S WRF/test/rrtmgp/test_udm_radius_stage.py \
  --capture-dir /absolute/existing/capture-directory \
  --output build/udm-radius-stage-result.json --require-matched --liquid-formula
```

For each LW/SW raw capture, the checker selects the latest producer for the same
domain and physical column with `producer_step < radiation_step`. This strict
ordering reflects radiation before microphysics in the timestep. It compares
all three source-radius arrays exactly as parsed binary64 values, including
signed zero. The writer promotes default REAL values before ES25.16 output.
Native vector lengths must agree; the producer records the native k bounds.
Both call clocks and their lag are recorded when the producer clock is present.
An available consumer CF source tag must match that producer's CF tag. CF tags
are distinct from radius producer steps.

An initial or restarted radiation call without an earlier producer is reported
as `NOT_RUN_INIT`; it is not verified by matching initial fields to later output.
`--require-matched` requires at least one matched consumer. The check rejects
duplicate fields or call identities, malformed filename/header identities,
wrong phases, missing fields, incorrect dimensions, nonfinite values, future
producer clocks and radius mismatches. It pins consumed files and detects edits
during inspection. It does not reopen history files or authenticate an
executable from a capture alone.

The current radiation QC, QI, QS, Nc, density and temperature can differ from the
earlier producer's state. Their changed-layer counts are descriptive. The
checker does not enforce an immediate radius formula against current radiation
condensates, and it does not infer that intervening physics leaves them fixed.

`--liquid-formula` adds a conditional ideal REAL64 calculation using the producer
QC, Nc, density and water-density constant:

```text
r = 0.5 / (pi * rho_water * Nc / (6 * QC * rho))**(1/3)
```

It uses the source's liquid guard thresholds and reports the ideal bound at
2.51–50 micrometres. It reports captured-minus-ideal differences without declaring
a compiler bit identity: default-real constants, products and exponent rounding
can differ. Interpreting this as a volume-mean moment radius requires a consistent
definition of Nc and liquid mass at that stage. Neither a correction factor nor
physical accuracy follows from this diagnostic.

Offline manufactured-file controls run without WRF or a compiler:

```sh
python3 -I -S WRF/test/rrtmgp/test_udm_radius_stage.py --self-test
```

Their success verifies the checker and its failure paths. Actual producer and
consumer evidence requires retained source, executable,
namelist and execution receipts. No physical gate is closed by these fixtures.
