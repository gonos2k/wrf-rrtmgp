# AER source audit for the negative-OD diagnostic

This is a bounded source/documentation audit of the retained LBLRTM CO2 line-mixing diagnostic. It does not decide that a negative monochromatic total optical depth is physically acceptable or erroneous. It does establish why the no-coupling run cannot serve as the truth reference.

Keep three results distinct. The coupled line-only run (`ICNTNM=0`) has 145,117 negative samples among 63,838,065 and a layer-21 minimum of -5.0522453754 at 666.3964444 cm-1. The coupled continuum-enabled run (`ICNTNM=1`) has 21,712 negatives and layer-21 minimum -4.8844290854 at the same wavenumber. The matched `NOCPL` sensitivity is also `ICNTNM=1`, with an identical TAPE5/profile but a newly generated no-coupling TAPE3; it has 2,391 negatives overall and minimum -0.0009924067 in layer 44. The lower negative count demonstrates sensitivity, not accuracy. LNFL documents NOCPL as suppressing all coupling information from TAPE3/TAPE7.

AER’s LBLRTM page says line coupling was used to derive its CO2 continuum and must be used for accurate calculations with that continuum. The `NOCPL`/continuum-on sensitivity therefore deliberately violates the recommended coupled configuration; it cannot serve as truth. Official AER release metadata pairs LBLRTM v12.17 with MT_CKD 4.3 and AER line file v3.8.1. The local line-generation plan pins that line-file input and coupled TAPE3. The `ICNTNM=0` baseline has no continuum contribution, so an MT_CKD release difference cannot cause its negative samples. Older MT_CKD 4.1 examples are not equivalent to the separate 4.3 continuum-on case.

The source shows a base line contribution followed by a signed coupling correction (`SPPSP`); source-level form alone cannot validate the resulting point value. The next useful reference should retain coupling and use a documented benchmark or independent measured/reference spectrum. A separately labeled continuum-enabled check should use the v12.17 / MT_CKD 4.3 / AER v3.8.1 pairing and independently pin the actual coefficient inputs. Do not relax tolerances or promote NOCPL to a truth oracle.

The instrumented candidate source SHA and stock-source SHA differ; no byte-identity with the upstream release source was asserted. The report preserves that provenance distinction and all local receipt hashes. The review performed no compile, line-file generation, solver run, raw-file scan, or maintainer contact.

Primary sources:

- [AER LBLRTM code page](https://rtweb.aer.com/lblrtm_code.html)
- [AER-RC/LBLRTM release compatibility table](https://github.com/AER-RC/LBLRTM)
- [AER-RC/LBLRTM v12.17 release commit](https://github.com/AER-RC/LBLRTM/commit/a85ac73447c1e62401a57a34bbcb040683345dca)
- [AER-RC/LNFL documentation](https://github.com/AER-RC/LNFL)
- [AER LBLRTM FAQ, coupling section](https://rtweb.aer.com/docs/FAQ_LBLRTM.pdf)
- [Targeted LBLRTM issue search](https://github.com/AER-RC/LBLRTM/issues?q=is%3Aissue+negative+optical+depth+line+mixing) (no matching issue surfaced; the search is not exhaustive)

Structured pins and findings are in [audit.json](audit.json).
