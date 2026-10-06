# First stock LBLRTM reference executions for UDM27

The stock LBLRTM v12.17 GNU-double executable accepted the captured 45-layer input and completed two optical-depth calculations over 500–2250 cm⁻¹. Both returned zero and produced `ODdeflt_001..045`. An independently checked parser read 63,838,065 finite samples in each case. **Neither result is accepted as a physical accuracy reference:** negative optical depths remain, without clipping or a relaxed tolerance.

| Condition | Negative samples | Minimum OD |
|---|---:|---:|
| Lines + four external cross sections, continua off | 145,117 | −5.052245375427372 |
| Same input, stock continua/CIA on | 21,712 | −4.884429085432753 |

The decks differ by exactly one byte: Record 1.2 ICNTNM changes from 0 to 1. Binary, line database, cross-section tables, pressure/temperature and molecule amounts are unchanged. Adding continua reduces but does not eliminate the anomaly. Independent raw decoding places both minima at layer 21, 666.3964444444449 cm⁻¹; the published raw IEEE words decode to the reported values. Normal process exit, finite values and correct file structure do not establish physical accuracy.

Input/source review and read-only postflight authenticate the stock reader, all 45 layers, GNU mixed-type binary records and retained inputs. The parser verifies record markers, panel coordinates, layer numbers and the serialized pressure/temperature values. It does not pair monochromatic samples with RRTMGP g-point indices or compute fluxes. Small layer summaries are published; full panels and large source/input binaries remain at the hashed private paths.

Source inspection identifies signed line-mixing terms, signed cubic interpolation weights and cold cross-section extrapolation as candidates. It does not identify a unique cause. Fourth-function cutoff subtraction is inactive in this configuration. The positive `RADFN` line-shape radiation term is not blackbody Planck B and cannot itself reverse a sign. See the pinned [LBLRTM source](https://github.com/AER-RC/LBLRTM/tree/a85ac73447c1e62401a57a34bbcb040683345dca/src) and the source-review artifacts.

The stock continuum N₂-complement convention, nominal OD-only heights and cross-section temperature limitations remain explicit. These executions do not close the WRF port’s physical-accuracy gates or explain its held-state flux residual. Next work must discriminate the signed line/profile mechanisms using localized controlled cases, retaining the original negative spectra.

To inspect an available completed case, use `python3 -I -S parse_od.py --run-dir CASE --deck TAPE5 --output NEW_JSON`. The parser requires all 45 products and refuses an existing output path. The hashed stock data/build preparation is outside this small evidence package; this command does not acquire it or launch a model.
