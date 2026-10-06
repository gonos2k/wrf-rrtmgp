# Selected LNFL coupling-record audit — preparation only

This v2 preparation preserves the unexecuted v1 draft and corrects its companion mapping. It proposes a single bounded offline pass over the pinned AER line source and its already-generated TAPE3. No line scan, compiler, LNFL, or LBLRTM invocation has occurred here.

The audit follows only three traced CO2 isotope-1 flag-1 lines from layer 21. It verifies their source and TAPE3 identity and reconstructs the source-ordered 200–250 K YI/GI interpolation and SPPI/SPPSP terms against the saved trace. It is a representation/arithmetic check, not an assessment of whether line coupling is physically valid or why LBLRTM produced negative optical depth.

The executed LNFL control has blank HOLIND, so the stock F100 parser is the authority: READ920/READ925 consume the first 100 character positions. The inherited plan-v6 note describing all source records as 160 characters is stale and is recorded as such; the proposed reader hashes each full input record but parses the columns LNFL actually reads. For a main input flag -1, LNFL associates one following foreign-coupling record. The corrected slot map is A=(VNU, ALFA, REAL4 reinterpretation of the MOL word, TMPALF), B=(SP, EPP, HWHMS, PSHIFT). Y/G input fields are rounded to REAL(4) before comparison with the TAPE3 representation.

Before any future run, the root and an independent reviewer should review `plan.json` and `read_selected_records.py`. A future run must use one fresh report path, a one-use wrapper, a 120-second process-group timeout and a durable child return-code receipt. Raw source records and full coefficient vectors stay private; the proposed report contains record hashes/offsets, match booleans and derived scalar terms only.

`plan.json` pins every input and relevant source. `read_selected_records.py` has only been syntax-parsed; it has not been executed against the AER file or TAPE3.
