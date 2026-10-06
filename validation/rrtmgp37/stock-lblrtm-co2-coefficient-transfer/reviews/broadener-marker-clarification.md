## Follow-up: `-654321` broadener marker

The original terminal review left the meaning of `-654321` open. This additive source check resolves that narrow point: pinned LNFL declares `ADDFLAG(7,250)` and equivalences its first entry with `LSTW2`; its comments define `LSTW2` as the marker used to determine storage length through the end of `IFLG`. LNFL initializes `LSTW2` to `-654321` and passes it to `NWDL` to compute `ILNGTH` (`lnfl.f`, lines 244–256 and 377–387; source SHA is recorded in the JSON).

Thus the observed value is layout metadata, not a physical broadening coefficient. The six vectors containing it have zeros in the other six positions. The saved LBLRTM path copies the flags, and its extra center-shift branch requires a positive flag sum, so this marker does not activate that branch. This clarification does not change the transfer result or establish coupling-group completeness or physical validity.
