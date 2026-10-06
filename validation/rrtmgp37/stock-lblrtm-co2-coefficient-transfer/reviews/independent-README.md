# CO2 coefficient-transfer reader review

The static source review is in `source-review.json`; the bounded terminal/result review is in `terminal-review.json`. Together they support a narrow conclusion: the 801 observed CO2 line identities and 5,930 target writes reproduce the saved source interpolation, pressure terms, line strength conditional on observed corrected SUI, and pressure-shifted centers exactly in binary64. The derived result reports 47,440 field comparisons with zero ULP differences; all 801 observed SUI, SP, and strength factors are positive.

The reader's process receipt is terminal: PID 2254879 returned 0, was reaped, and did not time out. Its execution pins the reviewed reader and plan. The actual state was T=228.3152 K and P=348.36124 hPa; four saved panel headers agree with the 72 ancestry records.

This is not an independent reconstruction of the original thermal strength: corrected SUI is a saved input. It does not establish line-list or coupling-group completeness, all-candidate coverage, or physical validity of negative optical depth. The six broadener-flag vectors containing `-654321` are observed as `(-654321,0,0,0,0,0,0)`; source directly copies them and the tested extra shift branch is gated by a positive flag sum, but the sentinel's semantic origin is not established by this review.
