# Dry-sedimentation density contract evidence

This archive ties the V2 UDM call-entry diagnostic to a fresh GNU build, six
bounded SCM runs, and a source-extracted sedimentation fixture. It preserves the
original packets, reports, receipts, and selected logs; the verifier re-parses
the packets rather than trusting the saved reports.

The fresh `em_scm_xy` GNU build completed successfully after one compile
invocation. Its 7,894-entry source manifest was byte-identical before and after.
Six one-minute SCM cases completed with RC 0: cold and warm input, each with
RRTMGP37 diagnostic capture off/on, plus the ordinary RRTMGP4 comparison arm.
The cold and warm RRTMGP37 off/on histories were whole-file byte-identical;
the two RRTMGP4 histories were byte-identical to their saved archive controls.
RRTMGP37-versus-archive comparisons are retained as descriptive differences,
not treated as an accuracy criterion.

The cold and warm capture-on cases each contain six V2 entry packets, six
post-radius packets, and a saved report. The verifier authenticates 12 entry
packets and 12 post-radius packets and independently rebuilds their six-step
same-call joins: 708 levels total, exact source-time matching, and unchanged
binary32 DEN across each native UDM call. V2 records both the selected
`DEND_REEVALUATED_PRECALL_KG_M3` and `DEND_LEGACY_COUNTERFACTUAL_KG_M3`.
In these SCM packets `INPUT_DENSITY_IS_DRY=1`, so selected DEND equals passed
DEN exactly; the legacy formula remains a counterfactual. `DEND_ORIGIN=1`
means an explicit observer reevaluation, not direct observation of UDM's
private local array.

The native source-extracted fixture retained its attempt history. The final
O0/O2 attempt passed its bounded sedimentation and forwarding controls; earlier
rain-only SIGFPE failures and the rain-only hazard remain archived. Its own
weighted-mass checks are fixture-specific. In the moist legacy-density branch,
the dry-mass residual is not a closed dry-water budget. These tests do not
establish a universal density-unit contract, number-unit or PSD authority,
optical accuracy, or production physical-policy closure.

The archive retains two no-model preflight failures: an earlier build attempt
stopped before compilation on a source-manifest mismatch, and a first SCM
runner attempt stopped before output-directory creation because of a Python
NameError. The recovered build and six SCM runs are separate later records; the
preserved failures are not recast as successful attempts. Full execution JSON
receipts and selected logs are gzip-compressed losslessly. No executable or
NetCDF history is included.

Run the stdlib verifier from a checkout containing the pinned source files:

```sh
python3 -I -S validation/rrtmgp37/sedimentation-density/verify.py
```

The verifier checks the closed archive roster and hashes, source pins, receipt
counts/statuses, six SCM history controls, and recomputes the V2 parser reports
from the archived raw packets. It makes no build, model, or RTE calls.
