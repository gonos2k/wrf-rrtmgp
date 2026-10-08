"""Root read-only census of pinned publisher ASCII and historical LNFL TAPE3.

No solver execution. Source roster equality is not physical mixing-partner
completeness. Strength is deliberately excluded from the field projection.
"""
from pathlib import Path
from collections import Counter
import hashlib, json, math, struct, gzip

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
ASCII = ROOT/'build/udm37-lblrtm-reference-stage-v1/data/aer_v_3.8.1/line_file/aer_v_3.8.1'
RUN = ROOT/'build/udm37-lblrtm-common-band-line-generation-v1/run-v6'
VMIN, VMAX = 475., 2275.

def require(ok, msg):
    if not ok:
        raise ValueError(msg)

def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]

def number(s):
    x = float(s.replace('D', 'E'))
    require(math.isfinite(x), 'finite scalar')
    return x

def normal(vnu, mol, flag, air, energy, own, exponent, shift):
    return struct.pack('<diifffff', vnu, mol, flag, air, energy, own, exponent, shift)

def side(values, flag):
    require(len(values) == 8 and flag < 0, 'sidecar shape and sign')
    return struct.pack('<8fi', *values, flag)

def digest_counter(c):
    h = hashlib.sha256()
    for key, n in sorted(c.items()):
        h.update(struct.pack('<IQ', len(key), n)); h.update(key)
    return h.hexdigest()

def public_roster(c, name):
    rows = {hashlib.sha256(k).digest(): n for k, n in c.items()}
    require(len(rows) == len(c), 'no observed digest collision')
    raw = b'CO2RSTR1' + struct.pack('<I', len(rows))
    raw += b''.join(k + struct.pack('<I', n) for k, n in sorted(rows.items()))
    packed = gzip.compress(raw, mtime=0)
    (BASE/name).write_bytes(packed)
    return {'path': name, 'bytes': len(packed), 'sha256': hashlib.sha256(packed).hexdigest(),
            'uncompressed_sha256': hashlib.sha256(raw).hexdigest(),
            'unique_fingerprints': len(rows), 'ordinary_lines': sum(rows.values()),
            'literal_publisher_scalar_records_included': False}

def bins(c):
    out = {}
    for key, n in c.items():
        v = struct.unpack_from('<d', key)[0]
        lo = 25 * int(v//25)
        b = out.setdefault(str(lo), {'ordinary': 0, 'coupled': 0})
        b['ordinary'] += n
        b['coupled'] += n * (struct.unpack_from('<i', key, 12)[0] > 0)
    return out

def scan_ascii():
    h = hashlib.sha256(); count = Counter(); flags = Counter()
    offset = 0; pending = None; physical_lines = 0; selected = None
    with ASCII.open('rb') as f:
        for line_number, raw in enumerate(f, 1):
            physical_lines = line_number; h.update(raw)
            start = offset; offset += len(raw)
            if pending is not None:
                text = raw.rstrip(b'\n').decode('ascii')
                require(len(text) == 100 and int(text[:2]) == 2, 'adjacent CO2 sidecar')
                coeffs = []
                for k in range(4):
                    coeffs.extend([f32(number(text[2+24*k:15+24*k])), f32(number(text[15+24*k:26+24*k]))])
                pending['key'] += side(coeffs, int(text[98:100]))
                pending['remaining'] -= 1
                if pending['remaining'] == 0:
                    if not pending.get('outside', False):
                        count[pending['key']] += 1
                    if pending['vnu'] == 618.023668:
                        selected = {k: v for k, v in pending.items() if k not in ('key', 'remaining')}
                        selected['pair_projection_sha256'] = hashlib.sha256(pending['key']).hexdigest()
                    pending = None
                continue
            # Normal F100 lines carry a one-character isotopologue at column3.
            if not raw.startswith(b' 2') or not raw[2:3].isdigit():
                continue
            text = raw.rstrip(b'\n').decode('ascii')
            require(len(text) == 100, 'CO2 ordinary F100 width')
            v = number(text[3:15]); signed = int(text[98:100]); flag = -signed if signed < 0 else 0
            require(flag in (0, 1, 3, 5), 'supported CO2 coupling flag')
            if not VMIN <= v <= VMAX:
                # Consume sidecars outside the requested range too.
                if flag:
                    pending = {'key': b'', 'remaining': 2 if flag == 5 else 1, 'vnu': v, 'outside': True}
                continue
            air = f32(number(text[35:40])); own = f32(number(text[40:45]))
            if own == 0.: own = air  # RDFIL1 non-water zero self-width policy.
            key = normal(v, 2+100*int(text[2]), flag, air, f32(number(text[45:55])), own,
                         f32(1.-f32(number(text[55:59]))), f32(number(text[59:67])))
            flags[str(flag)] += 1
            if flag:
                pending = {'key': key, 'remaining': 2 if flag == 5 else 1, 'vnu': v,
                           'line_1based': line_number, 'offset0': start}
            else:
                count[key] += 1
    require(pending is None, 'complete source sidecars')
    require(selected is not None, 'selected source line present')
    return count, {'path': str(ASCII), 'bytes': offset, 'sha256': h.hexdigest(),
                   'physical_lines': physical_lines, 'CO2_flags': dict(flags), 'selected': selected}

def record(f, h):
    lead = f.read(4)
    if not lead: return None
    require(len(lead) == 4, 'full leading marker'); n = struct.unpack('<i', lead)[0]
    require(0 <= n <= 100000, 'bounded positive record length')
    payload = f.read(n); tail = f.read(4)
    require(len(payload) == n and len(tail) == 4 and struct.unpack('<i', tail)[0] == n, 'sequential record framing')
    h.update(lead); h.update(payload); h.update(tail)
    return payload

def scan_tape3():
    h = hashlib.sha256(); c = Counter(); blocks = 0; records = 0; main_total = 0; side_total = 0
    species = Counter(); coupled = Counter(); flags = Counter(); selected = None
    with (RUN/'TAPE3').open('rb') as f:
        header = record(f, h); records += 1
        require(len(header) == 1664 and header[55:56] != b'^', 'pinned no-negative-EPP-header layout')
        while True:
            bh = record(f, h)
            if bh is None: break
            records += 1; blocks += 1
            require(len(bh) == 24, 'block header width')
            lo, hi, nr, nw = struct.unpack('<ddii', bh)
            require(math.isfinite(lo) and math.isfinite(hi) and lo <= hi and 0 < nr <= 250 and nw == 9750, 'block bounds')
            data = record(f, h); records += 1
            require(len(data) == 39000, 'fixed single input block')
            i = 0
            def val(off, fmt, j): return struct.unpack_from(fmt, data, off + (8 if fmt == '<d' else 4)*j)[0]
            while i < nr:
                flag = val(9000, '<i', i); mol = val(5000, '<i', i); v = val(0, '<d', i)
                require(flag in (0, 1, 3, 5), 'ordinary line or orphan sidecar')
                require(VMIN <= v <= VMAX and lo <= v <= hi, 'ordinary line requested and block range')
                main_total += 1; species[str(mol%100)] += 1
                side_n = 2 if flag == 5 else int(flag > 0)
                key = normal(v, mol, flag, val(3000, '<f', i), val(4000, '<f', i),
                             val(6000, '<f', i), val(7000, '<f', i), val(8000, '<f', i))
                if flag: coupled[str(mol%100)] += 1
                for j in range(i+1, i+1+side_n):
                    require(j < nr, 'coupling pair stays in defined block')
                    sf = val(9000, '<i', j); require(sf < 0, 'negative sidecar flag')
                    coeffs = [val(0, '<d', j)] + [val(off, '<f', j) for off in range(2000, 9000, 1000)]
                    key += side(coeffs, sf); side_total += 1
                if mol%100 == 2:
                    c[key] += 1; flags[str(flag)] += 1
                    if v == 618.023668:
                        require(selected is None, 'unique selected TAPE3 line')
                        selected = {'block_1based': blocks, 'data_record_1based': records, 'slot_1based': i+1,
                                    'vnu': v, 'pair_projection_sha256': hashlib.sha256(key).hexdigest()}
                i += 1 + side_n
        require(f.tell() == (RUN/'TAPE3').stat().st_size, 'exact EOF')
    return c, {'path': str(RUN/'TAPE3'), 'bytes': (RUN/'TAPE3').stat().st_size,
               'sha256': h.hexdigest(), 'physical_records': records, 'blocks': blocks,
               'ordinary_lines': main_total, 'sidecar_records': side_total,
               'species_counts': dict(species), 'coupled_main_counts': dict(coupled),
               'CO2_flags': dict(flags), 'selected': selected}

def main():
    # Save observations before raising on roster differences; never silently fix.
    source, a = scan_ascii(); target, b = scan_tape3()
    plan = json.loads((ROOT/'build/udm37-lblrtm-common-band-line-generation-v1/plan-v6.json').read_text())
    require(a['sha256'] == plan['source_stage']['line_file']['sha256'], 'historical source pin')
    require(b['sha256'] == '56bd55fa256ed3b3a672bd4bcd88034cd7086d4fbef2a1def9480199dab2b388', 'historical TAPE3 pin')
    missing = source - target; extra = target - source
    out = {'schema': 'UDM37_CO2_LNFL_SOURCE_ROSTER_CENSUS_V1', 'source': a, 'TAPE3': b,
           'range_cm1': [VMIN, VMAX], 'projection': 'VNU,encoded molecule/isotope,IFLG,air/self widths,energy,1-TDEP,shift,all adjacent foreign/self Y/G and sidecar flags; normalized strength excluded',
           'source_count': sum(source.values()), 'TAPE3_count': sum(target.values()),
           'missing_count': sum(missing.values()), 'extra_count': sum(extra.values()),
           'source_projection_sha256': digest_counter(source), 'TAPE3_projection_sha256': digest_counter(target),
           'source_bins25cm1': bins(source), 'TAPE3_bins25cm1': bins(target),
           'full_source_and_TAPE3_read_by_root': True, 'solver_or_compiler_processes': 0,
           'original_mixing_physical_partner_completeness_established': False,
           'LBLRTM_layer_rejection_and_finite_support_validated': False,
           'full_strength_normalization_replayed': False, 'physical_reference_accepted': False, 'production_accepted': False}
    out['public_source_roster'] = public_roster(source, 'source-roster.bin.gz')
    out['public_TAPE3_roster'] = public_roster(target, 'TAPE3-roster.bin.gz')
    out['status'] = 'PASS_SCOPED_CO2_SOURCE_TO_TAPE3_ROSTER' if not missing and not extra else 'FAIL_CO2_SOURCE_TO_TAPE3_ROSTER'
    (BASE/'readback.json').write_text(json.dumps(out, indent=2)+'\n')
    print(json.dumps({k: out[k] for k in ('status','source_count','TAPE3_count','missing_count','extra_count')}))
    print(json.dumps({'source_flags': a['CO2_flags'], 'TAPE3_flags': b['CO2_flags'], 'TAPE3_ordinary': b['ordinary_lines']}))
    require(not missing and not extra, 'source roster equality')

if __name__ == '__main__': main()
