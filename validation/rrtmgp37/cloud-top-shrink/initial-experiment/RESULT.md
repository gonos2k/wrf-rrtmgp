# Terminal result: natural cloud-top shrink observed

The one bounded standalone experiment passed at O0 and O2. Across three forwarding branches and three density modes at each optimization level, the first slope call reported liquid top k=5 and the second reported k=4. At removed level k=5, `rslopec2` changed from the initializer value `9.9999998245167004e-15` before the first call to `2.2132137789121487e-10` after it. That value was exactly unchanged before and after the second call. All 18 branch/mode observations passed these checks.

This directly demonstrates within-call top shrink and retention of a computed slope in this synthetic freezing profile. The experiment used the patched candidate only and contained no rain, so it does not test baseline comparison or `qrcon` use. It does not establish that this state occurs in atmospheric cases or characterize production impacts.

The durable process receipt is `run-v1/receipt.json`; the logs, exact source pins, and process PIDs/return codes are retained alongside it. Two candidate executables were built and run (10 compile/link processes, 2 fixture processes, 18 UDM invocations total). There were zero WRF forecast, REAL, or RTE calls.
