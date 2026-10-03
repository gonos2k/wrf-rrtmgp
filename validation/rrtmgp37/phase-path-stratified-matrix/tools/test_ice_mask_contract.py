#!/usr/bin/env python3
"""Offline negative controls for exact native eligibility-mask validation."""
import numpy as np


def expected_mask(cf, iwp, qice_grid_path, diameter_preclip_um):
    cf = np.asarray(cf, dtype=np.float64)
    iwp = np.asarray(iwp, dtype=np.float64)
    qpath = np.asarray(qice_grid_path, dtype=np.float64)
    diameter = np.asarray(diameter_preclip_um, dtype=np.float64)
    if not (cf.shape == iwp.shape == qpath.shape == diameter.shape):
        raise ValueError("shape mismatch")
    if not all(np.isfinite(x).all() for x in (cf, iwp, qpath, diameter)):
        raise ValueError("nonfinite eligibility input")
    return (cf > 0) & (iwp > 0) & (qpath > 0) & (diameter > 180.0)


def check_ice_mode(cf, iwp, qpath, diameter, encoded_expected_mask, actual_changed_mask, di_used, requested):
    expected = expected_mask(cf, iwp, qpath, diameter)
    sidecar_mask = np.asarray(encoded_expected_mask, dtype=bool)
    actual = np.asarray(actual_changed_mask, dtype=bool)
    used = np.asarray(di_used, dtype=np.float64)
    if expected.sum() == 0:
        raise ValueError("ice mode has no eligible layers")
    if not np.array_equal(sidecar_mask, expected):
        raise ValueError("sidecar eligibility mask differs from native inputs")
    if not np.array_equal(actual, expected):
        raise ValueError("reference changed-layer mask differs from native inputs")
    if not np.all(used[expected] == requested):
        raise ValueError("requested diameter not used on every eligible layer")
    if np.any(used[~expected] != np.clip(diameter[~expected], 10.0, 180.0)):
        raise ValueError("inactive layer diameter changed")
    return int(expected.sum())


def main():
    # Four- and six-level profiles remain exact, including all unchanged layers.
    for count in (4, 6):
        n = 9
        cf = np.ones(n)
        iwp = np.ones(n)
        qpath = np.zeros(n)
        d = np.array([120, 181, 182, 183, 184, 185, 186, 100, 90.], dtype=float)
        eligible = np.zeros(n, dtype=bool)
        eligible[1:1 + count] = True
        qpath[eligible] = 1.0
        used = np.clip(d, 10., 180.)
        used[eligible] = 160.
        assert check_ice_mode(cf, iwp, qpath, d, eligible, eligible, used, 160.) == count
    # Zero eligible layers must reject a requested ICE mode rather than pass as a no-op.
    allzero = np.zeros(4, dtype=bool)
    try:
        check_ice_mode(np.ones(4), np.ones(4), np.ones(4), np.full(4, 100.), allzero, allzero,
                       np.full(4, 100.), 160.)
    except ValueError as exc:
        assert "no eligible" in str(exc)
    else:
        raise AssertionError("zero-eligible ICE mode accepted")
    # A high diameter without cloud/native-ice support is inactive. A natural
    # iwp+diameter-only mask that changes it is caught by the exact sidecar mask.
    cf = np.array([1., 0., 1.])
    iwp = np.ones(3)
    qpath = np.array([1., 0., 1.])
    d = np.array([190., 220., 170.])
    expected = expected_mask(cf, iwp, qpath, d)
    assert expected.tolist() == [True, False, False]
    wrong_actual = np.array([True, True, False])
    used = np.array([160., 160., 170.])
    try:
        check_ice_mode(cf, iwp, qpath, d, expected, wrong_actual, used, 160.)
    except ValueError as exc:
        assert "changed-layer mask" in str(exc)
    else:
        raise AssertionError("inactive out-of-range diameter was allowed to change")
    # Exact missing/extra sidecar entries and a wrong requested diameter are caught.
    for bad_mask, bad_used in ((np.array([False, False, False]), np.array([160., 180., 170.])),
                               (np.array([True, True, False]), np.array([160., 160., 170.])),
                               (expected, np.array([140., 180., 170.]))):
        try:
            check_ice_mode(cf, iwp, qpath, d, bad_mask, bad_mask, bad_used, 160.)
        except ValueError:
            pass
        else:
            raise AssertionError("tampered mask or diameter passed")
    print("ice mask contract negative controls PASS: 4/6 exact; zero/inactive/tampered rejected")


if __name__ == "__main__":
    main()
