#!/usr/bin/env python3
"""Prepared read-only narrow TAPE3 main/companion extractor; intentionally not run yet."""
from __future__ import annotations
import argparse, hashlib, json, math, struct
from pathlib import Path

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
TAPE3 = ROOT / 'build/udm37-lblrtm-held-state-r3terms-cpl-od-run-v1/runs/od-v1/TAPE3'
TAPE3_SHA = '56bd55fa256ed3b3a672bd4bcd88034cd7086d4fbef2a1def9480199dab2b388'
TAPE5 = ROOT / 'build/udm37-lblrtm-held-state-r3terms-cpl-od-run-v1/runs/od-v1/TAPE5'
TAPE5_SHA = 'a676bc7761e09ab42f212c3cca80ebfd1be27604cd332cc966205d1280ae62dd'
TRACE = ROOT / 'build/udm37-lblrtm-r3-term-trace-v1/r3-accounting-report-v2.json'
TRACE_SHA = 'e44d08ea068c0b5e242f263c3a2f70c2d5ff4b71b529c10604d8be5de1e438ce'
OPROP = ROOT / 'build/udm37-lblrtm-stock-build-v1/attempt-1/source/LBLRTM/src/oprop.f90'
OPROP_SHA = '7cf594968ec331da3df75429262c1023c21fc461cbbae208253b0fa870685ef8'
STRUCT = ROOT / 'build/udm37-lblrtm-stock-build-v1/attempt-1/source/LBLRTM/src/struct_types.f90'
STRUCT_SHA = '55b52495780ae564e66470f6ad3f32afd8b58e0c59a6b78ed82b3f606fb7b16c'
LNFL = ROOT / 'build/udm37-lblrtm-reference-stage-v1/sources/LNFL/src/lnfl.f'
LNFL_SHA = 'd47b7b296b747837bbec8df06a7c8ea1df2ec241546b1db4a15f6b02b98a4ad6'

# GNU little-endian sequential-unformatted TAPE3 layout, as independently
# documented by the retained NOCPL raw-record comparator.
NWORDS, NLINE = 9750, 250
REC_BYTES = NWORDS * 4
OFFSETS = {
    'vnu': (0, 8, 'd'), 'strength': (2000, 4, 'f'),
    'air_width': (3000, 4, 'f'), 'lower_energy': (4000, 4, 'f'),
    'mol_word': (5000, 4, 'i'), 'self_width': (6000, 4, 'f'),
    'temperature_exponent': (7000, 4, 'f'), 'pressure_shift': (8000, 4, 'f'),
    'iflg': (9000, 4, 'i'),
}
TARGETS = [
    {'trace_i': 32, 'species': 2, 'isotope': 1, 'flag': 1, 'trace_vnu_cm-1': 667.385965634841,
     'YI': 3.034229991142273, 'GI': 0.0, 'SPPSP': 1.0431859088670232},
    {'trace_i': 60, 'species': 2, 'isotope': 1, 'flag': 1, 'trace_vnu_cm-1': 667.4004316856123,
     'YI': 0.6961040106391907, 'GI': 0.0, 'SPPSP': 0.23932460529508187},
    {'trace_i': 99, 'species': 2, 'isotope': 1, 'flag': 1, 'trace_vnu_cm-1': 667.423203639405,
     'YI': 0.2003582988820076, 'GI': 0.0, 'SPPSP': 0.06888434783402594},
]
P_LAYER_MBAR, T_LAYER_K, P0_MBAR, T0_K = 348.36124, 228.3152, 1013.25, 296.0
RHO_RATIO = (P_LAYER_MBAR / P0_MBAR) * (T0_K / T_LAYER_K)
RAW_CENTER_SEARCH_HALF_WIDTH_CM1 = 2.0


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def record(f, path: Path):
    start = f.tell()
    marker = f.read(4)
    if not marker:
        return None
    if len(marker) != 4:
        raise ValueError(f'truncated leading marker at byte {start}')
    n = struct.unpack('<i', marker)[0]
    if n < 0 or n > 10_000_000:
        raise ValueError(f'invalid GNU sequential record length {n} at byte {start}')
    payload, tail = f.read(n), f.read(4)
    if len(payload) != n or len(tail) != 4 or struct.unpack('<i', tail)[0] != n:
        raise ValueError(f'truncated/mismatched record at byte {start}')
    return start, payload


def field(payload: bytes, name: str, slot: int):
    off, width, code = OFFSETS[name]
    raw = payload[off + width * slot:off + width * (slot + 1)]
    if len(raw) != width:
        raise ValueError(f'truncated {name} slot {slot + 1}')
    return raw, struct.unpack('<' + code, raw)[0]


def unpack_slot(payload: bytes, slot: int, block: int):
    raw = {}
    values = {}
    for name in OFFSETS:
        raw[name], values[name] = field(payload, name, slot)
    flag, mol = values['iflg'], values['mol_word']
    # Main-line MOL is integer species/isotope code. For IFLG<0, the same
    # four bytes are a REAL(4) coefficient payload, matching RDLIN TRANSFER.
    values['species'] = mol % 100 if flag >= 0 else None
    values['isotope'] = (mol % 1000) // 100 if flag >= 0 else None
    if flag < 0:
        raw['mol_as_real4'] = raw['mol_word']
        values['mol_as_real4'] = struct.unpack('<f', raw['mol_word'])[0]
    return {'block': block, 'slot_1based': slot + 1, 'flag': flag,
            'values': values, 'raw_hex': {k: v.hex() for k, v in raw.items()}}


def iter_slots(path: Path):
    with path.open('rb') as f:
        first = record(f, path)
        if first is None or len(first[1]) != 1664:
            raise ValueError('unexpected/missing 1664-byte TAPE3 file header')
        block = 0
        while True:
            h = record(f, path)
            if h is None:
                break
            if len(h[1]) != 24:
                raise ValueError(f'expected 24-byte block header at {h[0]}')
            vlo, vhi, nlines, nwords = struct.unpack('<ddii', h[1])
            if not (math.isfinite(vlo) and math.isfinite(vhi) and vlo <= vhi and 0 < nlines <= NLINE and nwords == NWORDS):
                raise ValueError(f'invalid block header #{block + 1}')
            d = record(f, path)
            if d is None or len(d[1]) != REC_BYTES:
                raise ValueError(f'invalid fixed data record for block #{block + 1}')
            block += 1
            payload = d[1]
            for slot in range(nlines):
                yield block, slot, unpack_slot(payload, slot, block), (vlo, vhi)
        if f.tell() != path.stat().st_size:
            raise ValueError('stream did not end exactly at EOF')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report', type=Path, required=True)
    args = ap.parse_args()
    out = args.report.resolve()
    if out.exists():
        raise FileExistsError(out)
    for p, expected in ((TAPE3, TAPE3_SHA), (TAPE5, TAPE5_SHA), (TRACE, TRACE_SHA),
                        (OPROP, OPROP_SHA), (STRUCT, STRUCT_SHA), (LNFL, LNFL_SHA)):
        if not p.is_file() or sha(p) != expected:
            raise ValueError(f'pin mismatch: {p}')
    trace = json.loads(TRACE.read_text())
    if trace.get('status') != 'PASS_SCOPED_EXACT_UPDATE_ACCOUNTING_AND_NONINTERFERENCE':
        raise ValueError('trace report status mismatch')
    max_vnu = max(t['trace_vnu_cm-1'] for t in TARGETS)
    candidates = []
    active = None
    for block, slot, row, bounds in iter_slots(TAPE3):
        values = row['values']
        if values['iflg'] >= 0:
            if active is not None:
                candidates.append(active)
                active = None
            if (values['iflg'] in (1, 3, 5) and values['species'] == 2 and values['isotope'] == 1
                    and abs(values['vnu'] - max_vnu) <= RAW_CENTER_SEARCH_HALF_WIDTH_CM1):
                active = {'main': row, 'block_bounds_cm-1': bounds, 'companions': []}
        elif active is not None:
            active['companions'].append(row)
    if active is not None:
        candidates.append(active)
    # This report is a candidate inventory only. No selection/match PASS is
    # inferred until a reviewer checks unique shifted-center and coefficient matches.
    ranked = []
    for target in TARGETS:
        scored = []
        for candidate in candidates:
            v = candidate['main']['values']
            shifted = v['vnu'] + RHO_RATIO * v['pressure_shift']
            scored.append((abs(shifted - target['trace_vnu_cm-1']), candidate, shifted))
        scored.sort(key=lambda x: x[0])
        ranked.append({'target_trace': target, 'closest_candidates': [
            {'shifted_center_abs_difference_cm-1': delta, 'shifted_center_cm-1': shifted,
             'main_and_following_companions': candidate}
            for delta, candidate, shifted in scored[:10]
        ]})
    result = {
        'schema': 'UDM37_LBLRTM_COUPLING_TAPE3_CANDIDATE_AUDIT_V1',
        'status': 'CANDIDATE_INVENTORY_ONLY_NOT_MATCH_ACCEPTANCE',
        'provenance': {'tape3_sha256': sha(TAPE3), 'tape5_sha256': sha(TAPE5),
                       'trace_report_sha256': sha(TRACE), 'oprop_sha256': sha(OPROP),
                       'struct_types_sha256': sha(STRUCT), 'lnfl_sha256': sha(LNFL)},
        'reader': {'record_framing': 'GNU little-endian sequential-unformatted, 4-byte leading/trailing markers',
                   'block_header': 'REAL(8) VLO,VHI; INTEGER(4) nlines,nwords',
                   'data_block': '9750 four-byte words, 250 line slots; only nlines slots emitted',
                   'negative_iflg_mol_decode': 'report raw MOL-slot bytes and reinterpret those exact four bytes as IEEE REAL(4); never classify as species',
                   'candidate_scope': 'main CO2 species=2/isotope=1 with IFLG in {1,3,5}, raw VNU within 2 cm-1 of the three traced post-shift centers; retain following negative-IFLG records until the next main record',
                   'shift_model': 'VNU_work = VNU_raw + RHORAT*PSHIFT, RHORAT=(PAVE/P0)*(TEMP0/TAVE); target deck IBRD=0, so extra broadener-shift correction branch is inactive',
                   'layer21_inputs': {'PAVE_mbar': P_LAYER_MBAR, 'TAVE_K': T_LAYER_K, 'P0_mbar': P0_MBAR, 'TEMP0_K': T0_K, 'RHORAT': RHO_RATIO}},
        'target_candidate_inventories': ranked,
        'limitations': ['Reader has not been run; this is source/plan preparation only.',
                        'Candidate-window membership is not proof of line association; validate unique shifted center and full main/companion mapping.',
                        'No TAPE3 coefficients are decoded or compared by this preparation.',
                        'AER line data and TAPE3 remain private; do not redistribute.',
                        'No physical-validity or optical-depth acceptance follows from record identity.']}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print('CANDIDATE_INVENTORY_ONLY_NOT_MATCH_ACCEPTANCE')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
