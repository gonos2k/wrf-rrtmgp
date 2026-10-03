#!/usr/bin/env python3
"""Focused contracts for optional UDM cloud-fraction extent metadata."""
from pathlib import Path
import tempfile
import numpy as np

from test_column_replay import ReplayError, read_input, validate_udm_cf_extent
from test_udm_cf_replay import b_last_cf_mode
from analyse_udm_physics_audit import raw_cloud_summary


def expect_failure(records, nl, token):
    try:
        validate_udm_cf_extent(records, nl, Path('synthetic.raw'))
    except ReplayError as exc:
        assert token in str(exc), str(exc)
        return
    raise AssertionError(f'expected extent validation failure containing {token!r}')


def main():
    assert validate_udm_cf_extent({}, 3, Path('legacy.raw')) is None
    assert validate_udm_cf_extent({'UDM_CF_TOP': np.array([0.]),
                                   'UDM_CF_SOURCE_STEP': np.array([4.])}, 3,
                                  Path('precip-only.raw')) == 0
    assert validate_udm_cf_extent({'UDM_CF_TOP': np.array([2.]),
                                   'UDM_CF_SOURCE_STEP': np.array([4.])}, 3,
                                  Path('cloudy.raw')) == 2
    assert validate_udm_cf_extent({'UDM_CF_TOP': np.array([-1.]),
                                   'UDM_CF_SOURCE_STEP': np.array([-1.])}, 3,
                                  Path('clear.raw')) == -1
    expect_failure({'UDM_CF_TOP': np.array([1.])}, 3, 'requires UDM_CF_SOURCE_STEP')
    expect_failure({'UDM_CF_TOP': np.array([1.]),
                    'UDM_CF_SOURCE_STEP': np.array([-1.])}, 3, 'same not-called state')
    expect_failure({'UDM_CF_TOP': np.array([4.]),
                    'UDM_CF_SOURCE_STEP': np.array([1.])}, 3, 'outside valid bounds')
    expect_failure({'UDM_CF_TOP': np.array([1.5]),
                    'UDM_CF_SOURCE_STEP': np.array([1.])}, 3, 'finite integer')

    with tempfile.TemporaryDirectory(prefix='udm-cf-audit-') as tmp:
        malformed_raw = Path(tmp) / 'negative-step.raw'
        malformed_raw.write_text(
            'RRTMGP_RAW_V1\nLW 1 1 3\n'
            'CF 3\n0.1 0.2 0.3\n'
            'UDM_CF_TOP 1\n1\nUDM_CF_SOURCE_STEP 1\n-2\n',
            encoding='ascii')
        try:
            raw_cloud_summary(malformed_raw)
        except ValueError as exc:
            assert 'invalid UDM CF top/step extent pair' in str(exc), str(exc)
        else:
            raise AssertionError('audit parser accepted UDM_CF_SOURCE_STEP < -1')

        # Only the diagnosed prefix contributes to ratios. Above TOP the
        # saved working vector can contain arbitrary placeholders, here 1s.
        ratio_raw = Path(tmp) / 'ratio-prefix.raw'
        ratio_raw.write_text(
            'RRTMGP_RAW_V1\nLW 1 1 3\n'
            'CF 3\n0.25 0.5 0.5\n'
            'UDM_CF_USED 3\n0.5 1 1\n'
            'UDM_CF_TOP 1\n1\nUDM_CF_SOURCE_STEP 1\n2\n',
            encoding='ascii')
        ratios = raw_cloud_summary(ratio_raw)['cf']
        assert ratios['builder_to_last_used']['valid_positive_denominator_layers'] == 1
        assert ratios['builder_to_last_used']['mean'] == 0.5
        assert ratios['last_used_to_builder']['valid_positive_denominator_layers'] == 1
        assert ratios['last_used_to_builder']['mean'] == 2.0

        for top, step in ((0, 2), (-1, -1)):
            empty = Path(tmp) / f'ratio-empty-{top}.raw'
            empty.write_text(
                'RRTMGP_RAW_V1\nLW 1 1 3\n'
                'CF 3\n0.25 0.5 0.5\n'
                'UDM_CF_USED 3\n0.5 1 1\n'
                f'UDM_CF_TOP 1\n{top}\nUDM_CF_SOURCE_STEP 1\n{step}\n',
                encoding='ascii')
            empty_cf = raw_cloud_summary(empty)['cf']
            assert empty_cf['builder_to_last_used']['valid_positive_denominator_layers'] == 0
            assert empty_cf['last_used_to_builder']['valid_positive_denominator_layers'] == 0

    original = np.array([0.2, 0.3, 0.4])
    used = np.array([1.0, 0.5, np.nan])
    np.testing.assert_array_equal(b_last_cf_mode(original, used, 2), [1.0, 0.5, 0.4])
    np.testing.assert_array_equal(b_last_cf_mode(original, used, 0), original)
    assert b_last_cf_mode(original, used, -1) is None
    np.testing.assert_array_equal(b_last_cf_mode(original, np.array([0.1, 0.2, 0.3]), None),
                                  [0.1, 0.2, 0.3])

    # Raw extent metadata is optional, so legacy V4 replay inputs remain readable.
    legacy_v4 = ('RRTMGP_REPLAY_V4\nLW 1 1 0 19 1\n'
                 'ICE_ROUGHNESS 1 1\n1\n'
                 'PRECIPITATION_OPTICS 1 1\n1\n'
                 'RWP 1 1\n0\n')
    with tempfile.TemporaryDirectory(prefix='udm-cf-extent-') as tmp:
        path = Path(tmp) / 'legacy-v4.input'
        path.write_text(legacy_v4, encoding='ascii')
        version, nc, nl, *_rest, records = read_input(path)
        assert version == 'LW' and nc == 1 and nl == 1
        assert records['RWP'].shape == (1, 1)
    print('UDM CF extent parser and legacy V4 reader tests passed')


if __name__ == '__main__':
    main()
