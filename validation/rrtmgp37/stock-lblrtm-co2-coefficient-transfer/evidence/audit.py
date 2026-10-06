#!/usr/bin/env python3
"""One reviewed, saved-only 801-line interpolation/pressure-path audit.

No solver/build, AER ASCII, TAPE5/6, CAND or OD is opened. Corrected SUI is
an explicit observed input, not an independently reconstructed gas amount.
"""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
PINS = {
    'roster': ('build/udm37-lblrtm-candidate-decision-reader-run-v2/report.json', '3244591f8545ba8f91f9c0f9ce3a8e8717ba7ec21487b13a0360e9d60ef83c51', 1370214),
    'census': ('build/udm37-lblrtm-co2-target-companion-census-v1/run-v1/result.json', 'eb8243244ff65d396c1c797195e7dcc36111dd7cce9a084c8873ec0aad109e22', 108576),
    'ancestry': ('build/udm37-lblrtm-left-censored-ancestry-run-v2/runs/od-v1/UDM37_ANCESTRY', '8b628c5e7889537efee83069d971e4118df687852ccfd5990d3aab03003f7e80', 72144),
    'panel': ('build/udm37-lblrtm-left-censored-ancestry-run-v2/runs/od-v1/UDM37_PANEL_TRACE', 'e80e8e10c80a6af43f31a5123b9024fabb1d87a149f01f6edd0679bdb42f5ee0', 307584),
    'terms': ('build/udm37-lblrtm-left-censored-ancestry-run-v2/runs/od-v1/UDM37_R3_TERM_TRACE', '5167f1496f7c34577a755f8c5ebd71e59a20245ebf057f9bfc25a260f0e2ccec', 14753208),
}
TAPE3 = ROOT / 'build/udm37-lblrtm-held-state-r3terms-cpl-od-run-v1/runs/od-v1/TAPE3'
TAPE3_HISTORICAL_SHA = '56bd55fa256ed3b3a672bd4bcd88034cd7086d4fbef2a1def9480199dab2b388'
TARGET_VFT = 662.695395555556
TARGET_BINS = (61, 62, 63, 64)
NI = 'seq phase reason layer pass_id block_id slot_id batch_id buffer_i outer_j encoded_MOL isotope original_IFLAG JRAD ILNFLG'.split()
NF = 'VFT VBOT VTOP input_VNU adjusted_VNU input_line_strength prethermal_SUI corrected_SUI YI GI PAVP0 PAVP2 ALFL ALFV RECALF ZETA SP SPPSP EPP BETACR SCOR XKT TAVE PAVE TEMP0 P0'.split()
TI = 'seq stage layer batch i j1 j3 molecule isotope flag izeta iz3 j3shft jmin1 jmax1'.split()
TF = 'vft dvr3 vnu sp sppsp recalf str f3 z before after zslope zint conf3 sui gi yi pavp0 pavp2 alfl zeta meta_vnu'.split()
METRICS = ('YI', 'GI', 'PAVP0', 'PAVP2', 'SP_from_observed_corrected_SUI', 'SPPSP_from_observed_corrected_SUI', 'shifted_VNU', 'term_meta_VNU')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def stat(path):
    s = path.stat()
    return {'size': s.st_size, 'inode': s.st_ino, 'mtime_ns': s.st_mtime_ns}


def pinned(name):
    rel, wanted, size = PINS[name]
    path = ROOT / rel
    before = stat(path)
    b = path.read_bytes()
    require(len(b) == size and sha(b) == wanted and stat(path) == before, name + ' immutable input pin')
    return b


def records(data):
    p = 0
    while p < len(data):
        require(p + 8 <= len(data), 'short record marker')
        n = struct.unpack_from('<i', data, p)[0]
        require(0 <= n <= 64 * 1024 * 1024 and p + n + 8 <= len(data), 'record length')
        require(data[p:p+4] == data[p+n+4:p+n+8], 'record trailer')
        yield data[p+4:p+n+4]
        p += n + 8
    require(p == len(data), 'trailing partial record')


def bit(x):
    return struct.pack('<d', x)


def ulp(x, y):
    def order(a):
        n = struct.unpack('<Q', bit(a))[0]
        return (~n & ((1 << 64) - 1)) if n >> 63 else n | (1 << 63)
    return abs(order(x) - order(y))


def context(ancestry, panel):
    states, count = set(), 0
    for line in ancestry.decode('ascii').splitlines():
        t = line.split()
        require(len(t) == 42 and t[0] == 'UDM37ANC1', 'ancestry schema')
        d = dict(zip(NI, map(int, t[1:16])))
        d.update(zip(NF, (float(s.replace('D', 'E')) for s in t[16:])))
        require(d['seq'] == count + 1 and (d['phase'], d['reason'], d['layer']) == (2, 9, 21), 'ancestry scope/sequence')
        require(all(math.isfinite(d[k]) for k in NF), 'ancestry nonfinite')
        states.add(tuple(bit(d[k]) for k in ('TAVE', 'PAVE', 'TEMP0', 'P0', 'PAVP0', 'PAVP2')))
        count += 1
    require(count == 72 and len(states) == 1, 'layer21 state not uniformly observed across72 records')
    values = [struct.unpack('<d', b)[0] for b in next(iter(states))]
    state = dict(zip(('TAVE', 'PAVE', 'TEMP0', 'P0', 'PAVP0', 'PAVP2'), values))
    require(all(state[k] > 0 for k in state), 'nonpositive state')
    require(bit(state['PAVE'] / state['P0']) == bit(state['PAVP0']), 'observed normalized pressure')
    require(bit(state['PAVP0'] * state['PAVP0']) == bit(state['PAVP2']), 'observed squared pressure')
    it = iter(records(panel))
    selected = []
    panels = 0
    for h in it:
        require(len(h) == 232 and h[:8] == b'UDMTRC1 ', 'panel header layout')
        ints = struct.unpack_from('<19q', h, 8)
        vals = struct.unpack_from('<9d', h, 160)
        require(all(math.isfinite(v) for v in vals), 'panel header nonfinite')
        for n in ints[2:5]:
            b = next(it, None)
            require(n > 0 and b is not None and len(b) == 8 * n, 'panel array layout')
            # Skip stored R1/R2/R3 numeric arrays; no array value is decoded.
        panels += 1
        if ints[1] == 21:
            require(vals[3] <= vals[8] <= vals[4], 'selected panel target bounds')
            require(bit(vals[0]) == bit(state['PAVE']) and bit(vals[1]) == bit(state['TAVE']), 'independent panel state disagreement')
            selected.append({'stage': ints[0], 'layer': ints[1], 'V1P': vals[3], 'V2P': vals[4], 'target': vals[8]})
    require(selected, 'no selected layer21 panel state')
    state['ancestry_records'] = count
    state['panel_records'] = panels
    state['layer21_panel_headers'] = selected
    return state


def load_roster(doc, census):
    require(doc['join']['target_term_updates_joined'] == 6072 and doc['join']['target_full_invocation_identities'] == 837, 'prior target accounting')
    require(census['matched_main_count'] == 801 and census['companion_cardinality_counts'] == {'1': 801}, 'prior structural census')
    rows = [r for r in doc['join']['target_unique_identity_summary'] if r['encoded_MOL'] % 100 == 2 and r['original_IFLAG'] == 1]
    require(len(rows) == 801, 'target CO2 roster count')
    lookup, identities = {}, {}
    for r in rows:
        key = (r['LNCOR_batch'], r['slot_id'])
        require(key not in lookup and r['pass_id'] == 21, 'ambiguous target key')
        lookup[key] = r
        identities[(r['block_id'], r['slot_id'])] = r
    require(len(identities) == 801, 'duplicate physical input main')
    require({(r['block'], r['slot'], r['mol'], r['iflg']) for r in census['record_matches']} == {(r['block_id'], r['slot_id'], r['encoded_MOL'], r['original_IFLAG']) for r in rows}, 'observed census roster drift')
    return lookup, identities


def input_pairs(identities, census):
    before = stat(TAPE3)
    require(before['size'] == 122157832, 'historical TAPE3 size')
    expected_ranges = {r['range']: r for r in census['range_read']['selected_range_hashes']}
    pairs, read_bytes, hashes = {}, 0, {}
    off = {'vnu': (0, 8, 'd'), 'sp': (2000, 4, 'f'), 'alfa': (3000, 4, 'f'), 'epp': (4000, 4, 'f'), 'mol': (5000, 4, 'i'), 'hwhms': (6000, 4, 'f'), 'tmpalf': (7000, 4, 'f'), 'pshift': (8000, 4, 'f'), 'iflg': (9000, 4, 'i')}
    def slot(b, s):
        d = {k: struct.unpack_from('<' + fmt, b, base + width * (s-1))[0] for k, (base, width, fmt) in off.items()}
        d['amol'] = struct.unpack_from('<f', b, 5000 + 4 * (s-1))[0]
        return d
    def read_range(f, label, start, size):
        f.seek(start)
        b = f.read(size)
        require(len(b) == size and sha(b) == expected_ranges[label]['sha256'], 'fresh selected-range pin mismatch ' + label)
        hashes[label] = sha(b)
        return b
    with TAPE3.open('rb') as f:
        header = read_range(f, 'header', 0, 1672)
        require(len(list(records(header))) == 1, 'TAPE3 first record')
        read_bytes += len(header)
        for block in range(484, 497):
            b = read_range(f, 'block-' + str(block), 1672 + (block-1)*39040, 39040)
            rr = list(records(b))
            require(len(rr) == 2 and len(rr[0]) == 24 and len(rr[1]) == 39000, 'TAPE3 selected panel layout')
            lo, hi, n, words = struct.unpack('<ddii', rr[0])
            require(words == 9750 and 1 <= n <= 250 and math.isfinite(lo) and math.isfinite(hi) and lo <= hi, 'TAPE3 header')
            for (bi, si), r in identities.items():
                if bi != block:
                    continue
                main = slot(rr[1], si)
                require(main['mol'] == r['encoded_MOL'] and main['iflg'] == 1 and si < n, 'TAPE3 main identity/companion boundary')
                # INPUT_BLOCK has BRD_MOL_FLG_IN(7,250) at byte10000.
                # LNCOR's additional center-shift branch needs sum(flags)>0
                # AND IBRD>0. Prove the first predicate false for each target;
                # never assume the unobserved IBRD configuration is disabled.
                main['broadener_flags'] = struct.unpack_from('<7i', rr[1], 10000 + 28*(si-1))
                require(sum(main['broadener_flags']) <= 0, 'additional broadener-specific shift branch needs independent inputs')
                companion = slot(rr[1], si+1)
                require(companion['iflg'] == -1, 'TAPE3 foreign companion flag')
                a = (companion['vnu'], companion['alfa'], companion['amol'], companion['tmpalf'])
                c = (companion['sp'], companion['epp'], companion['hwhms'], companion['pshift'])
                require(all(math.isfinite(v) for v in a+c), 'nonfinite companion coefficients')
                require(all(math.isfinite(main[k]) for k in ('vnu', 'pshift')), 'nonfinite main input center/shift')
                pairs[(r['LNCOR_batch'], si)] = {'main': main, 'A': a, 'B': c, 'identity': r}
            read_bytes += len(b)
    require(before == stat(TAPE3) and len(pairs) == 801 and read_bytes == 509192, 'TAPE3 stable bounded input')
    return pairs, {'read_bytes': read_bytes, 'stat_before_after_equal': True, 'range_hashes': hashes, 'historical_whole_file_SHA256': TAPE3_HISTORICAL_SHA, 'fresh_whole_file_hash': False, 'additional_pressure_shift_branch_first_predicate_false_count': len(pairs), 'broadener_flag_patterns': {str(pattern): count for pattern, count in collections.Counter(tuple(p['main']['broadener_flags']) for p in pairs.values()).items()}}


def compare_terms(data, pairs, state):
    temps = (200.0, 250.0, 296.0, 340.0)
    # Literal LNCOR loop selects interval3 even when T>=340 (extrapolation).
    ilc = next((i for i in range(3) if state['TAVE'] < temps[i+1]), 2)
    rectlc = 1.0 / (temps[ilc+1] - temps[ilc])
    tmpdif = state['TAVE'] - temps[ilc]
    p0 = state['PAVE'] / state['P0']
    p2 = p0 * p0
    rho = p0 * (state['TEMP0'] / state['TAVE'])
    stats = {k: {'checks': 0, 'bit_differences': 0, 'max_ULP': 0, 'max_abs': 0.0} for k in METRICS}
    unique, stages, iso, bins, diffs = set(), collections.Counter(), collections.Counter(), collections.Counter(), []
    check_by_id = {key: dict.fromkeys(METRICS, True) for key in pairs}
    signs = {k: collections.Counter() for k in ('SUI', 'SP', 'strength_factor')}
    recorded = {}
    seq, terms_total, snapshots_total, selected_count, all_selected_count = 0, 0, 0, 0, 0
    it = iter(records(data))
    for b in it:
        require(b[:8] in (b'UDMR3T1 ', b'UDMR3S1 '), 'R3 tag')
        if b[:8] == b'UDMR3S1 ':
            require(len(b) == 200, 'R3 snapshot header')
            ii = struct.unpack_from('<19q', b, 8)
            require(ii[0] == seq+1 and ii[2] == 21, 'R3 snapshot sequence/layer')
            a = next(it, None)
            require(ii[3] > 0 and a is not None and len(a) == 8*ii[3], 'R3 snapshot array shape')
            snapshots_total += 1
            seq += 1
            continue  # Do not decode snapshot array values or rerun R3 accounting.
        require(len(b) == 304, 'R3 term layout')
        t = dict(zip(TI, struct.unpack_from('<15q', b, 8)))
        t.update(zip(TF, struct.unpack_from('<22d', b, 128)))
        require(t['seq'] == seq+1 and t['layer'] == 21 and t['stage'] in (1, 2), 'R3 term identity')
        require(all(math.isfinite(t[k]) for k in TF), 'R3 nonfinite term')
        seq += 1
        terms_total += 1
        if bit(t['vft']) != bit(TARGET_VFT) or t['j3'] not in TARGET_BINS:
            continue
        all_selected_count += 1
        if t['molecule'] != 2:
            continue
        selected_count += 1
        key = (t['batch'], t['i'])
        require(key in pairs, 'CO2 target contributor missing from observed roster')
        pair = pairs[key]
        ident = pair['identity']
        require(t['isotope'] == ident['isotope'] and t['flag'] == ident['original_IFLAG'] == 1, 'CO2 isotope/flag mismatch')
        a, c = pair['A'], pair['B']
        yi = a[ilc] + ((a[ilc+1] - a[ilc]) * rectlc) * tmpdif
        gi = c[ilc] + ((c[ilc+1] - c[ilc]) * rectlc) * tmpdif
        factor = 1.0 + gi * p2
        sp = t['sui'] * factor
        require(sp != 0.0 and math.isfinite(sp), 'reconstructed target SP invalid denominator')
        sppsp = ((t['sui'] * yi) * p0) / sp
        center = pair['main']['vnu'] + rho * pair['main']['pshift']
        expected = (yi, gi, p0, p2, sp, sppsp, center, center)
        observed = (t['yi'], t['gi'], t['pavp0'], t['pavp2'], t['sp'], t['sppsp'], t['vnu'], t['meta_vnu'])
        for name, value, ref in zip(METRICS, expected, observed):
            require(math.isfinite(value), 'nonfinite independently reconstructed value')
            z = stats[name]
            z['checks'] += 1
            n = ulp(value, ref)
            z['max_ULP'] = max(n, z['max_ULP'])
            z['max_abs'] = max(z['max_abs'], abs(value-ref))
            if bit(value) != bit(ref):
                z['bit_differences'] += 1
                check_by_id[key][name] = False
                if len(diffs) < 20:
                    diffs.append({'batch': key[0], 'slot': key[1], 'sequence': seq, 'metric': name, 'ULP': n, 'abs': abs(value-ref)})
        immutable = tuple(bit(t[k]) for k in ('sui', 'yi', 'gi', 'pavp0', 'pavp2', 'sp', 'sppsp', 'meta_vnu'))
        require(key not in recorded or recorded[key] == immutable, 'same-identity target operands vary across writes')
        if key not in recorded:
            recorded[key] = immutable
            iso[str(t['isotope'])] += 1
            for k, v in (('SUI', t['sui']), ('SP', t['sp']), ('strength_factor', factor)):
                signs[k]['positive' if v > 0 else 'negative' if v < 0 else 'zero'] += 1
        unique.add(key)
        stages[str(t['stage'])] += 1
        bins[str(t['j3'])] += 1
    require((seq, terms_total) == (45785, 45569), 'R3 original record totals')
    require(selected_count == 5930 and all_selected_count == 6072 and unique == set(pairs), 'complete observed801 target coefficient coverage')
    summary = [{'pass': pair['identity']['pass_id'], 'block': pair['identity']['block_id'], 'slot': key[1], 'batch': key[0], 'encoded_MOL': pair['identity']['encoded_MOL'], 'isotope': pair['identity']['isotope'], 'flag': 1, 'checks_bit_exact': check_by_id[key]} for key, pair in sorted(pairs.items())]
    ok = not any(z['bit_differences'] for z in stats.values())
    return {'status': 'PASS_SCOPED_801_CO2_INTERPOLATION_PRESSURE_AND_CENTER_TRANSFER' if ok else 'FAIL_SCOPED_COEFFICIENT_TRANSFER', 'target_record_count': selected_count, 'all_target_records': all_selected_count, 'observed_CO2_identities': len(unique), 'checks': stats, 'total_compared_values': sum(z['checks'] for z in stats.values()), 'differences_first20': diffs, 'identity_checks': summary, 'isotope_counts': dict(iso), 'stage_counts': dict(stages), 'bin_record_counts': dict(bins), 'observed_strength_sign_counts': {k: dict(v) for k, v in signs.items()}, 'selected_temperature_interval_K': [temps[ilc], temps[ilc+1]], 'R3_trace_records': seq, 'R3_term_records': terms_total, 'R3_snapshot_records': snapshots_total}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--run', action='store_true')
    args = ap.parse_args()
    require(args.run and not args.output.exists(), 'explicit reviewed run / fresh output required')
    docs = {name: pinned(name) for name in PINS}
    roster, census = json.loads(docs['roster']), json.loads(docs['census'])
    lookup, identities = load_roster(roster, census)
    state = context(docs['ancestry'], docs['panel'])
    pairs, partial = input_pairs(identities, census)
    require(set(lookup) == set(pairs), 'roster and main/companion bijection')
    result = compare_terms(docs['terms'], pairs, state)
    result.update({'schema': 'UDM37_CO2_OBSERVED801_COEFFICIENT_TRANSFER_V1', 'source_temperature_pressure_context': state, 'TAPE3_selected_ranges': partial, 'input_pins': {name: {'path': val[0], 'sha256': val[1], 'size_bytes': val[2]} for name, val in PINS.items()}, 'new_solver_build_model_calls': 0, 'scope_limits': ['Only801 observed CO2 target contributors at layer21/bins61..64; no all-candidate/rejection or physical group closure.', 'Corrected SUI is taken from saved per-line runtime metadata; this audit does NOT independently establish WK/WKI/SCOR/thermal strength or original ASCII-to-TAPE3 correctness for all801.', 'PAVE/TAVE are cross-observed in saved ancestry and panel headers; layer state invariance is source-backed. Reference constants P0/TEMP0 come from actual ancestry fields.', 'No ordinary/coupled R3 write arithmetic or OD positivity is accepted/reconstructed here; existing negativeOD FAIL remains.', 'Full TAPE3 historical hash is not freshly recomputed; every read header/panel byte range matches the previous actual structural census digest.', 'This checks calculation/transport mechanics of an external LBLRTM reference, not WRF/RRTMGP physical accuracy or residual normality.']})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n')
    print(json.dumps({'status': result['status'], 'identities': result['observed_CO2_identities'], 'compared_values': result['total_compared_values'], 'output': str(args.output)}))
    return 0 if result['status'].startswith('PASS_') else 2


if __name__ == '__main__':
    raise SystemExit(main())
