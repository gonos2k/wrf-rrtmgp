#!/usr/bin/env python3
"""Prepared one-pass, read-only AER ASCII -> LNFL TAPE3 -> traced-term audit.

This program is deliberately not executed in the preparation task. A future
reviewed one-use launcher may run it once with a fresh --report path.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import struct
from pathlib import Path

ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
AER = ROOT / 'build/udm37-lblrtm-reference-stage-v1/data/aer_v_3.8.1/line_file/aer_v_3.8.1'
TAPE3 = ROOT / 'build/udm37-lblrtm-held-state-r3terms-cpl-od-run-v1/runs/od-v1/TAPE3'
TAPE5 = ROOT / 'build/udm37-lblrtm-held-state-r3terms-cpl-od-run-v1/runs/od-v1/TAPE5'
TAPE6 = ROOT / 'build/udm37-lblrtm-held-state-r3terms-cpl-od-run-v1/runs/od-v1/TAPE6'
TRACE = ROOT / 'build/udm37-lblrtm-r3-term-trace-v1/r3-accounting-report-v2.json'
LNFL_TAPE5 = ROOT / 'build/udm37-lblrtm-common-band-line-generation-v1/run-v6/TAPE5'
LNFL_POSTFLIGHT = ROOT / 'build/udm37-lblrtm-common-band-line-generation-v1/run-v6/postflight.json'
LNFL_PLAN = ROOT / 'build/udm37-lblrtm-common-band-line-generation-v1/plan-v6.json'
LNFL = ROOT / 'build/udm37-lblrtm-reference-stage-v1/sources/LNFL/src/lnfl.f'
OPROP = ROOT / 'build/udm37-lblrtm-stock-build-v1/attempt-1/source/LBLRTM/src/oprop.f90'
STRUCT = ROOT / 'build/udm37-lblrtm-stock-build-v1/attempt-1/source/LBLRTM/src/struct_types.f90'
PINS = {
    AER: 'd0ec800cfaeaaa7ab7af7b8168f45b205e383272e147373df6d0eed2677f2bd3',
    TAPE3: '56bd55fa256ed3b3a672bd4bcd88034cd7086d4fbef2a1def9480199dab2b388',
    TAPE5: 'a676bc7761e09ab42f212c3cca80ebfd1be27604cd332cc966205d1280ae62dd',
    TAPE6: '4b88814de6c5fe95f1cea65e881fec0e1e6f2320894f1bdacde312be1a2102d2',
    TRACE: 'e44d08ea068c0b5e242f263c3a2f70c2d5ff4b71b529c10604d8be5de1e438ce',
    LNFL_TAPE5: '697357190795f9451e83afe232675dcfd4dc1ddf1c036f1f347c261d973ba970',
    LNFL_POSTFLIGHT: '7d7fc12accebe46b2e5a0d220cc82c8ba103d6b2d2f36953181f45e75534217e',
    LNFL_PLAN: '7ee1eddd5d1c0970503d2dc7730c494f77bb2f919bf822795f6252d57248e6f6',
    LNFL: 'd47b7b296b747837bbec8df06a7c8ea1df2ec241546b1db4a15f6b02b98a4ad6',
    OPROP: '7cf594968ec331da3df75429262c1023c21fc461cbbae208253b0fa870685ef8',
    STRUCT: '55b52495780ae564e66470f6ad3f32afd8b58e0c59a6b78ed82b3f606fb7b16c',
}
# The frozen executed TAPE5 has blank HOLIND, selecting LNFL's stock F100
# RDFIL1 path. The previous plan-v6 all-record 160-char descriptor is stale.
# F100 READ920 spans exactly 100 bytes; coupling READ925 consumes the same row.
TARGETS = [
    {'trace_i':32,'vnu_cm-1':667.385965634841,'sui':0.05631378974057237,'sp':0.05631378974057237,'pavp2':0.11820243703749168,'yi':3.034229991142273,'gi':0.0,'sppsp':1.0431859088670232},
    {'trace_i':60,'vnu_cm-1':667.4004316856123,'sui':0.09792171475469987,'sp':0.09792171475469987,'pavp2':0.11820243703749168,'yi':0.6961040106391907,'gi':0.0,'sppsp':0.23932460529508187},
    {'trace_i':99,'vnu_cm-1':667.423203639405,'sui':0.1339798101145706,'sp':0.1339798101145706,'pavp2':0.11820243703749168,'yi':0.2003582988820076,'gi':0.0,'sppsp':0.06888434783402594},
]
TRACE_PAVP0 = 0.34380581297804097
TAVE_K = 228.3152
P0_MBAR, TEMP0_K = 1013.25, 296.0
# TAPE3 fixed GNU sequential-unformatted block organization.
NWORDS, NLINE, DATABYTES = 9750, 250, 9750 * 4
OFF = {'vnu': (0, 8, 'd'), 'sp': (2000,4,'f'), 'alfa': (3000,4,'f'), 'epp': (4000,4,'f'),
       'mol': (5000,4,'i'), 'hwhms': (6000,4,'f'), 'tmpalf': (7000,4,'f'),
       'pshift': (8000,4,'f'), 'iflg': (9000,4,'i')}

def digest_stream(f):
    h = hashlib.sha256()
    while True:
        b = f.read(1 << 20)
        if not b: break
        h.update(b)
    return h.hexdigest()

def sha(path):
    with path.open('rb') as f: return digest_stream(f)

def stat_pin(path):
    s = path.stat()
    return {'size_bytes': s.st_size, 'mtime_ns': s.st_mtime_ns, 'inode': s.st_ino}

def parse_float(s):
    s = s.strip().replace('D','E').replace('d','e')
    return float(s) if s else None

def ascii_main(line, offset, ordinal, record_sha, record_len):
    # READ920 consumes the first 100 character positions of the source record;
    # any trailing characters are not part of this parsed record.
    if len(line) < 100: return None
    line=line[:100]
    try:
        mol = int(line[0:2]); iso = int(line[2:3]); vnu = parse_float(line[3:15]);
        strsv = parse_float(line[15:25]); trans = parse_float(line[25:35])
        hwhmf = parse_float(line[35:40]); hwhms = parse_float(line[40:45])
        energy = parse_float(line[45:55]); tdep = parse_float(line[55:59]); shift = parse_float(line[59:67])
        ifup = int(line[67:70]); iflo = int(line[70:73]); flag = int(line[98:100])
    except (ValueError, OverflowError):
        return None
    if vnu is None: return None
    return {'ordinal':ordinal,'byte_offset':offset,'record_sha256':record_sha,'record_length':record_len,
            'mol':mol,'iso':iso,'vnu':vnu,'strsv':strsv,'trans':trans,'hwhmf':hwhmf,'hwhms':hwhms,
            'energy':energy,'tdep':tdep,'shift':shift,'ivup':ifup,'ivlo':iflo,'iflg_input':flag}

def ascii_companion(line, offset, ordinal, record_sha, record_len):
    # READ925 is also a 100-column read, with any source trailing columns ignored.
    if len(line) < 100: return None
    line=line[:100]
    try:
        vals=[]
        for k in range(4):
            j=2+24*k
            vals.extend([parse_float(line[j:j+13]),parse_float(line[j+13:j+24])])
        flag=int(line[98:100])
    except (ValueError, OverflowError): return None
    if any(v is None for v in vals): return None
    return {'ordinal':ordinal,'byte_offset':offset,'record_sha256':record_sha,'record_length':record_len,
            'y_g':vals,'iflg_input':flag}

def scan_aer(path):
    # All source rows are parsed in memory only when a target main line is
    # identified; raw source bytes/rows are never copied into the report.
    st0=stat_pin(path); h=hashlib.sha256(); matches=[]; pending=[]; offset=0; ordinal=0
    ranges=[(t['vnu_cm-1']-2.0, t['vnu_cm-1']+2.0) for t in TARGETS]
    with path.open('rb') as f:
        for raw in f:
            h.update(raw); ordinal+=1; here=offset; offset+=len(raw)
            if raw.endswith(b'\n'): raw=raw[:-1]
            if raw.endswith(b'\r'): raw=raw[:-1]
            if len(raw)<100: continue
            recsha=hashlib.sha256(raw).hexdigest()
            try: line=raw.decode('ascii')
            except UnicodeDecodeError: continue
            if pending:
                comp=ascii_companion(line,here,ordinal,recsha,len(raw))
                if comp is not None:
                    pending['companions'].append(comp)
                    if len(pending['companions']) >= pending['required']:
                        matches.append(pending); pending=[]
                    continue
                # Broken expected sequence is retained as an explicit failure.
                pending['sequence_error_at_ordinal']=ordinal; matches.append(pending); pending=[]
            main=ascii_main(line,here,ordinal,recsha,len(raw))
            if not main or main['mol']!=2 or main['iso']!=1 or main['iflg_input']!=-1: continue
            if not any(lo <= main['vnu'] <= hi for lo,hi in ranges): continue
            shift32=unpack_ascii_fp(main['shift'],'f')
            rhorat=TRACE_PAVP0*(TEMP0_K/TAVE_K)
            centers=[abs(main['vnu']+rhorat*shift32-t['vnu_cm-1']) for t in TARGETS]
            target_index=min(range(len(centers)),key=centers.__getitem__)
            if centers[target_index] > 1.e-4: continue
            required=1
            pending={'main':main,'required':required,'companions':[],'target':TARGETS[target_index],
                     'input_shifted_center_cm-1':main['vnu']+rhorat*shift32}
    if pending:
        pending['sequence_error_at_eof']=True; matches.append(pending)
    st1=stat_pin(path); content_sha=h.hexdigest()
    if st0 != st1 or offset != st1['size_bytes']: raise ValueError('AER file changed while streaming')
    if content_sha != PINS[AER]: raise ValueError('AER content pin mismatch')
    return matches, {'stream_sha256':content_sha,'stat_before':st0,'stat_after':st1,'records_seen':ordinal,'bytes_read':offset}

def unpack_ascii_fp(value,kind):
    # GNU single-precision LNFL: implicit REAL*8 is only on V names; companion
    # Y/G values are REAL(4), including Y1 promoted when assigned to VNU1.
    return struct.unpack('<f',struct.pack('<f',float(value)))[0]

def f32(value):
    return struct.unpack('<f',struct.pack('<f',float(value)))[0]

def ulp64(a,b):
    def ordered(x):
        u=struct.unpack('>Q',struct.pack('>d',float(x)))[0]
        return (0x8000000000000000-u) if (u & 0x8000000000000000) else (u+0x8000000000000000)
    return abs(ordered(a)-ordered(b))

def lnfl_main_sp_from_ascii(strsv, vnu):
    # LNFL BLOCKDATA constants and PROGRAM/RDFIL1 arithmetic are REAL(4)
    # through RADCN2 and BETA0; STRSV/VNU are REAL(8), then STR is REAL(4).
    planck4=f32(6.62606876e-27); clight4=f32(2.99792458e10); boltz4=f32(1.3806503e-16)
    radcn2_4=f32(f32(planck4*clight4)/boltz4)
    beta0_4=f32(radcn2_4/f32(296.0))
    return f32(strsv/(vnu*(1.0-math.exp(-beta0_4*vnu))))

def parse_rec(f, expected=None):
    start=f.tell(); lead=f.read(4)
    if not lead: return None
    if len(lead)!=4: raise ValueError('short sequential record marker')
    n=struct.unpack('<i',lead)[0]
    if n<0 or n>10_000_000: raise ValueError(f'invalid record size {n}')
    data=f.read(n); tail=f.read(4)
    if len(data)!=n or len(tail)!=4 or struct.unpack('<i',tail)[0]!=n: raise ValueError(f'bad record at {start}')
    return start,data

def slot(data,s):
    d={}
    for name,(base,w,fmt) in OFF.items(): d[name]=struct.unpack('<'+fmt,data[base+w*s:base+w*(s+1)])[0]
    flag=d['iflg']; d['species']=d['mol']%100 if flag>=0 else None; d['isotope']=(d['mol']%1000)//100 if flag>=0 else None
    # Preserve both interpretations. The companion role comes from LNFL
    # sequence, not this slot's IFLG sign; RDLIN transfers these four bytes.
    d['mol_real4']=struct.unpack('<f',data[5000+4*s:5004+4*s])[0]
    return d

def scan_tape3(path, aer_matches):
    st0=stat_pin(path); h=hashlib.sha256(); candidates=[]; wanted={}
    for m in aer_matches: wanted.setdefault(m['main']['vnu'],[]).append(m)
    with path.open('rb') as f:
        first=parse_rec(f)
        if first is None or len(first[1])!=1664: raise ValueError('unexpected TAPE3 header')
        h.update(struct.pack('<i',len(first[1]))+first[1]+struct.pack('<i',len(first[1])))
        block=0; pending_main=None
        while True:
            head=parse_rec(f)
            if head is None: break
            h.update(struct.pack('<i',len(head[1]))+head[1]+struct.pack('<i',len(head[1])))
            if len(head[1])!=24: raise ValueError('bad block header')
            vlo,vhi,nlines,nwords=struct.unpack('<ddii',head[1])
            if not (math.isfinite(vlo) and math.isfinite(vhi) and 0<nlines<=NLINE and nwords==NWORDS): raise ValueError('bad TAPE3 block metadata')
            row=parse_rec(f)
            if row is None or len(row[1])!=DATABYTES: raise ValueError('bad TAPE3 fixed block')
            h.update(struct.pack('<i',len(row[1]))+row[1]+struct.pack('<i',len(row[1])))
            block+=1; data=row[1]; data_start=row[0]
            for i in range(nlines):
                rec=slot(data,i)
                # Collect the complete adjacent negative-IFLG group for a
                # selected main. A later nonnegative slot closes the group;
                # this lets acceptance detect extra companion records instead
                # of making a one-record cardinality check tautological.
                if pending_main is not None:
                    if rec['iflg'] < 0:
                        rec['_slot_1based']=i+1
                        for pm in pending_main: pm['companions'].append(rec)
                        continue
                    candidates.extend(pending_main); pending_main=None
                if rec['iflg']>=0 and rec['species']==2 and rec['isotope']==1 and rec['iflg']==1:
                    associated=wanted.get(rec['vnu'],[])
                    if associated:
                        pending_main=[{'main':rec,'main_slot_1based':i+1,'block':block,'block_vlo':vlo,'block_vhi':vhi,
                                       'data_record_start':data_start,'companions':[],'aer':am} for am in associated]
        if pending_main is not None: candidates.extend(pending_main)
        if f.tell()!=path.stat().st_size: raise ValueError('TAPE3 trailing/unparsed bytes')
    st1=stat_pin(path); content_sha=h.hexdigest()
    if st0!=st1: raise ValueError('TAPE3 changed during scan')
    if content_sha!=PINS[TAPE3]: raise ValueError('TAPE3 content pin mismatch')
    result=[]; rectlc=1.0/(250.0-200.0); tmpdif=TAVE_K-200.0
    rhorat=TRACE_PAVP0*(TEMP0_K/TAVE_K)
    for c in candidates:
        if len(c['companions'])!=1 or len(c['aer']['companions'])!=1:
            result.append({'target_trace_i':c['aer']['target']['trace_i'],'association':'FAIL_COMPANION_CARDINALITY',
                           'main_vnu_cm-1':c['main']['vnu'],'companion_count':len(c['companions']),
                           'source_companion_count':len(c['aer']['companions']),
                           'main_fields_exact':{},'companion_A_fields_exact':[False]*4,'companion_B_fields_exact':[False]*4,
                           'companion_iflg':None,'source_companion_iflg':None,
                           'absolute_differences_from_trace':{'YI':1e300,'GI':1e300,'SPPSP':1e300},
                           'ULP_differences_from_trace':{'YI':2**64,'GI':2**64,'SPPSP':2**64},
                           'shifted_center_ULP_from_trace':2**64,'SP_reconstructed_from_trace_SUI_GI_PAVP2':None}); continue
        co=c['companions'][0]
        # RDLNFL source: A=(VNU,ALFA,TRANSFER(MOL-as-REAL4),TMPALF),
        # B=(SP,EPP,HWHMS,PSHIFT), then slope before TMPDIF multiplication.
        a=(co['vnu'],co['alfa'],co['mol_real4'],co['tmpalf'])
        b=(co['sp'],co['epp'],co['hwhms'],co['pshift'])
        src=c['aer']['companions'][0]['y_g']
        src_a=(src[0],src[2],src[4],src[6]); src_b=(src[1],src[3],src[5],src[7])
        src_a32=tuple(unpack_ascii_fp(x,'f') for x in src_a)
        src_b32=tuple(unpack_ascii_fp(x,'f') for x in src_b)
        comp_equal_a=tuple(x==y for x,y in zip(a,src_a32)); comp_equal_b=tuple(x==y for x,y in zip(b,src_b32))
        slopey=(a[1]-a[0])*rectlc; slopeg=(b[1]-b[0])*rectlc
        yi=a[0]+slopey*tmpdif; gi=b[0]+slopeg*tmpdif
        target=c['aer']['target']; sppi=target['sui']*yi*TRACE_PAVP0
        spi=target['sui']*(1.0+gi*target['pavp2']); sppspi=sppi/spi
        am=c['aer']['main']
        main_equal={'VNU_exact':c['main']['vnu']==am['vnu'],
            'MOL_ISO':c['main']['mol']==am['mol']+100*am['iso'],
            'IFLG_absolute_input':c['main']['iflg']==abs(am['iflg_input']),
            'SP_from_STRSV_reference_strength_REAL4':c['main']['sp']==lnfl_main_sp_from_ascii(am['strsv'],am['vnu']),
            'ALFA_HWHMF_REAL4':c['main']['alfa']==unpack_ascii_fp(am['hwhmf'],'f'),
            'EPP_ENERGY_REAL4':c['main']['epp']==unpack_ascii_fp(am['energy'],'f'),
            'HWHMS_REAL4':c['main']['hwhms']==unpack_ascii_fp(am['hwhms'],'f'),
            'TMPALF_one_minus_TDEP_REAL4':c['main']['tmpalf']==unpack_ascii_fp(1.0-unpack_ascii_fp(am['tdep'],'f'),'f'),
            'PSHIFT_REAL4':c['main']['pshift']==unpack_ascii_fp(am['shift'],'f')}
        result.append({'target_trace_i':target['trace_i'],'association':'main matched by exact raw VNU and listed source fields; adjacent companion matched by all eight REAL4 promotions',
            'main_vnu_cm-1':c['main']['vnu'],'main_iflg':c['main']['iflg'],'main_slot_1based':c['main_slot_1based'],
            'main_block':c['block'],'main_block_bounds_cm-1':[c['block_vlo'],c['block_vhi']],
            'data_record_start_byte':c['data_record_start'],'companion_slot_1based':co['_slot_1based'],'companion_iflg':co['iflg'],
            'source_record_ids':{'main_sha256':am['record_sha256'],'main_byte_offset':am['byte_offset'],'main_ordinal':am['ordinal'],
                'foreign_companion_sha256':c['aer']['companions'][0]['record_sha256'],
                'foreign_companion_byte_offset':c['aer']['companions'][0]['byte_offset'],
                'foreign_companion_ordinal':c['aer']['companions'][0]['ordinal']},
            'source_companion_count':len(c['aer']['companions']),
            'source_companion_iflg':c['aer']['companions'][0]['iflg_input'],
            'main_fields_exact':main_equal,'companion_A_fields_exact':list(comp_equal_a),'companion_B_fields_exact':list(comp_equal_b),
            'YI':yi,'GI':gi,'SPPI':sppi,'SP_reconstructed_from_trace_SUI_GI_PAVP2':spi,'SPPSP':sppspi,
            'trace_values':{'YI':target['yi'],'GI':target['gi'],'SPPSP':target['sppsp']},
            'absolute_differences_from_trace':{'YI':abs(yi-target['yi']),'GI':abs(gi-target['gi']),'SPPSP':abs(sppspi-target['sppsp'])},
            'ULP_differences_from_trace':{'YI':ulp64(yi,target['yi']),'GI':ulp64(gi,target['gi']),'SPPSP':ulp64(sppspi,target['sppsp'])},
            'center_using_exact_trace_PAVP0_cm-1':c['main']['vnu']+rhorat*c['main']['pshift'],
            'center_using_AER_main_PSHIFT_REAL4_cm-1':c['aer']['input_shifted_center_cm-1'],
            'shifted_center_absdiff_from_trace_cm-1':abs(c['main']['vnu']+rhorat*c['main']['pshift']-target['vnu_cm-1']),
            'shifted_center_ULP_from_trace':ulp64(c['main']['vnu']+rhorat*c['main']['pshift'],target['vnu_cm-1'])})
    return result, {'stream_sha256':content_sha,'stat_before':st0,'stat_after':st1,'blocks':block}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--report',required=True,type=Path); a=ap.parse_args(); out=a.report.resolve()
    if out.exists(): raise FileExistsError(out)
    before={str(p):stat_pin(p) for p in (AER,TAPE3,TAPE5,TAPE6,TRACE,LNFL_TAPE5,LNFL_POSTFLIGHT,LNFL_PLAN,LNFL,OPROP,STRUCT)}
    for p,expected in PINS.items():
        if not p.is_file(): raise FileNotFoundError(p)
        if p not in (AER,TAPE3) and sha(p)!=expected: raise ValueError(f'pin mismatch: {p}')
    trace=json.loads(TRACE.read_text())
    if trace.get('status')!='PASS_SCOPED_EXACT_UPDATE_ACCOUNTING_AND_NONINTERFERENCE': raise ValueError('trace scope/status mismatch')
    for target in TARGETS:
        terms=[]
        for section in trace['target_R3_accounting']:
            terms.extend(q for q in section.get('largest_negative_coupling_terms',[]) if q.get('i')==target['trace_i'])
        if not terms or any(q.get('pavp0')!=TRACE_PAVP0 or q.get('yi')!=target['yi'] or q.get('gi')!=target['gi'] or q.get('sppsp')!=target['sppsp'] for q in terms):
            raise ValueError('target constants do not match pinned trace report')
    tape5_lines=TAPE5.read_text().splitlines()
    if not any('3.4836124E+02' in line and '228.3152' in line for line in tape5_lines): raise ValueError('exact layer-21 TAPE5 P/T row absent')
    if any('NOCPL' in line for line in tape5_lines): raise ValueError('executed TAPE5 unexpectedly requests NOCPL')
    lnfl_tape5=LNFL_TAPE5.read_bytes().splitlines()
    if len(lnfl_tape5)<3 or b'NOCPL' in lnfl_tape5[2]: raise ValueError('run-v6 LNFL control is not blank-HOLIND default')
    tape6_lines=TAPE6.read_text().splitlines()
    if len(tape6_lines)<5 or 'IBRD' not in tape6_lines[3] or tape6_lines[4].split()[-1]!='0':
        raise ValueError('LBLRTM TAPE6 does not show IBRD=0')
    aer, aer_read=scan_aer(AER)
    tape, tape_read=scan_tape3(TAPE3,aer)
    for p,expected in PINS.items():
        if p not in (AER,TAPE3) and sha(p)!=expected: raise ValueError(f'post-pin mismatch: {p}')
    after={str(p):stat_pin(p) for p in (AER,TAPE3,TAPE5,TAPE6,TRACE,LNFL_TAPE5,LNFL_POSTFLIGHT,LNFL_PLAN,LNFL,OPROP,STRUCT)}
    if before!=after: raise ValueError('input stat changed across audit')
    # Match each of three targets uniquely on main physical identity, raw VNU,
    # translated center, plus TAPE3-derived YI/GI/SPPSP; do not claim anything
    # about OD validity or all spectral records.
    matched=[]
    for target in TARGETS:
        selected=[x for x in tape if x.get('target_trace_i')==target['trace_i']]
        matched.append({'target':target,'match_count':len(selected),'records':selected})
    checks=[]
    for entry in matched:
        xs=entry['records']
        checks.append(len(xs)==1)
        if len(xs)==1:
            x=xs[0]
            checks.extend([all(x['main_fields_exact'].values()),all(x['companion_A_fields_exact']),all(x['companion_B_fields_exact']),
                           x['companion_iflg']<0 and x['companion_iflg']==x['source_companion_iflg'] and x['source_companion_count']==1,
                           x['shifted_center_ULP_from_trace']==0,
                           all(v==0 for v in x['ULP_differences_from_trace'].values()),
                           x['SP_reconstructed_from_trace_SUI_GI_PAVP2']==entry['target']['sp']])
    audit_pass=bool(checks) and all(checks)
    result={'schema':'UDM37_LBLRTM_COUPLING_ORIGINAL_ASCII_TO_TAPE3_AUDIT_V2','status':'PASS_SCOPED_RECORD_AND_COEFFICIENT_PATH' if audit_pass else 'FAIL_RETAINED',
        'scope':'Only three traced CO2 isotope-1 flag-1 main records and their single foreign companion are resolved.',
        'provenance':{'pins':{str(p):{'sha256_expected':PINS.get(p),'stat_before':before[str(p)],'stat_after':after[str(p)]} for p in PINS},
            'aer_scan':aer_read,'tape3_scan':tape_read},
        'audit_result':{'aer_candidate_count':len(aer),'tape3_exact_raw_vnu_count':len(tape),'target_matches':matched},
        'comparisons':'The report contains source row hashes/offsets but no raw ASCII/TAPE3 line text or full coefficient vectors. It reports main/companion field-equality booleans plus derived YI/GI/SPPI/SPPSP.',
        'acceptance_predicates':{'one_unique_match_per_target':True,'all_listed_main_source_fields_equal':True,
            'main_fields_checked':['VNU','MOL/ISO','IFLG','SP transformed from STRSV','ALFA','EPP','HWHMS','TMPALF','PSHIFT'],
            'all_8_companion_values_equal_after_LNFL_REAL4_promotion':True,'companion_flag_negative_and_source_equal':True,
            'shifted_center_exact_binary64':True,'trace_YI_GI_SPPSP_exact_binary64':True,'no_missing_or_duplicate_records':True},
        'scientific_limit':'Record association and source arithmetic only; this does not establish physical validity of coupling coefficients or explain all negative OD.'}
    out.parent.mkdir(parents=True,exist_ok=True)
    payload=(json.dumps(result,indent=2,sort_keys=True)+'\n').encode()
    fd=os.open(out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(payload); f.flush(); os.fsync(f.fileno())
    return 0 if audit_pass else 1
if __name__=='__main__': raise SystemExit(main())
