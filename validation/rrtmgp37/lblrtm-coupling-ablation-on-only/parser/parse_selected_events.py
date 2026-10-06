#!/usr/bin/env python3
"""Read-only selected R3-event parser extracted from the reviewed pair runner.

It opens only supplied trace paths, writes a JSON summary, and never launches
LBLRTM. The embedded routines are source-derived from the pinned helper listed
in parser-provenance.json.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, math, struct
from pathlib import Path
from typing import Any
TARGETS = {667.385965634841: 666.3135288888894, 667.4004316856123: 666.3738311111116, 667.423203639405: 666.4341333333339}
TARGET_TOL = 5.0e-10
def sha(path: Path) -> tuple[str, int]:
    h = hashlib.sha256(); size = 0
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b: break
            size += len(b); h.update(b)
    return h.hexdigest(), size

def read_fortran_records(path: Path):
    with path.open("rb") as f:
        while True:
            lead=f.read(4)
            if not lead: return
            if len(lead)!=4: raise RuntimeError("short Fortran record prefix")
            n=struct.unpack("<i",lead)[0]
            if n<0 or n>100_000_000: raise RuntimeError(f"invalid Fortran record length {n}")
            data=f.read(n); trail=f.read(4)
            if len(data)!=n or len(trail)!=4 or struct.unpack("<i",trail)[0]!=n:
                raise RuntimeError("truncated or mismatched Fortran sequential record")
            yield data

def parse_r3_terms(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    it=iter(read_fortran_records(path)); terms=[]; snapshots=[]; seq_expected=1
    ints=['seq','stage','layer','max3','nlim1','nlim3','ilo','ihi','ipanel','istop','n1r3','n2r3','nlo','nhi','nshift','icntnm','ilblf4','ixsect','ir4']
    floats=['vft','dv','dvr3','pave','tave']
    ti=['seq','stage','layer','batch','i','j1','j3','molecule','isotope','flag','izeta','iz3','j3shft','jmin1','jmax1']
    tf=['vft','dvr3','vnu','sp','sppsp','recalf','str','f3','z','before','after','zslope','zint','conf3','sui','gi','yi','pavp0','pavp2','alfl','zeta','meta_vnu']
    for b in it:
        if b[:8]==b'UDMR3S1 ':
            if len(b)!=200: raise RuntimeError("bad R3 snapshot header length")
            row=dict(zip(ints,struct.unpack_from('<19q',b,8)))
            row.update(zip(floats,struct.unpack_from('<5d',b,160)))
            if row['seq']!=seq_expected or row['layer']!=21 or row['max3']<=0:
                raise RuntimeError("R3 snapshot ordering/layer/dimension mismatch")
            arr=next(it); seq_expected+=1
            if len(arr)!=row['max3']*8: raise RuntimeError("R3 snapshot array length mismatch")
            row['_r3']=struct.unpack(f"<{row['max3']}d",arr)
            if not all(math.isfinite(x) for x in row['_r3']): raise RuntimeError("nonfinite R3 snapshot")
            snapshots.append(row)
        elif b[:8]==b'UDMR3T1 ':
            if len(b)!=304: raise RuntimeError("bad R3 term record length")
            row=dict(zip(ti,struct.unpack_from('<15q',b,8)))
            row.update(zip(tf,struct.unpack_from('<22d',b,128)))
            if row['seq']!=seq_expected or row['layer']!=21:
                raise RuntimeError("R3 term ordering/layer mismatch")
            seq_expected+=1
            if not all(math.isfinite(row[k]) for k in tf): raise RuntimeError("nonfinite R3 term")
            terms.append(row)
        else:
            raise RuntimeError(f"unexpected R3 record marker {b[:8]!r}")
    if not terms or not snapshots: raise RuntimeError("R3 stream missing terms or snapshots")
    return terms,snapshots

def line_slot(center: float) -> float | None:
    for target in TARGETS:
        if abs(center-target)<=TARGET_TOL: return target
    return None

def event_key(t: dict[str, Any], selected: bool) -> tuple[Any, ...]:
    # For nonselected records and selected baseline updates, compare term operands, not R3 before/after state.
    operand=t['str']*t['f3']
    if t['stage']==2: operand=operand*t['z']
    return (t['stage'],t['layer'],t['batch'],t['i'],t['molecule'],t['isotope'],t['flag'],
            t['izeta'],t['iz3'],t['j3shft'],t['jmin1'],t['jmax1'],
            struct.pack('<d',t['vnu']),struct.pack('<d',t['vft']),t['j3'],struct.pack('<d',operand))

def validate_ablation_events(baseline_path: Path, off_path: Path, on_path: Path) -> dict[str, Any]:
    baseline,_=parse_r3_terms(baseline_path); off,_=parse_r3_terms(off_path); on,snaps=parse_r3_terms(on_path)
    # OFF trace itself must be exact against the reference before ON can be assessed.
    if sha(baseline_path)!=sha(off_path): raise RuntimeError("OFF R3 term trace not byte-identical to baseline")
    def is_selected(t): return t['molecule']==2 and t['isotope']==1 and line_slot(t['vnu']) is not None
    base_sel=collections.Counter(); off_sel=collections.Counter(); on_sel=collections.Counter()
    base_other=collections.Counter(); on_other=collections.Counter()
    base_probe=collections.Counter(); on_probe=collections.Counter()
    base_line_ids=collections.defaultdict(set); off_line_ids=collections.defaultdict(set); on_line_ids=collections.defaultdict(set)
    base_base_operands=collections.Counter(); off_base_operands=collections.Counter(); on_base_operands=collections.Counter()
    for label,rows in (("base",baseline),("off",off),("on",on)):
        for t in rows:
            if is_selected(t):
                slot=line_slot(t['vnu']); physical=t['vft']+(t['j3']-1)*t['dvr3']
                tup=(t['stage'],slot)
                line_id=(t['batch'],t['i'],t['molecule'],t['isotope'],struct.pack('<d',t['vnu']))
                if label=="base":
                    base_sel[tup]+=1; base_line_ids[slot].add(line_id)
                    if t['stage']==1: base_base_operands[(slot,struct.pack('<d',physical),struct.pack('<d',t['str']*t['f3']))]+=1
                elif label=="off":
                    off_sel[tup]+=1; off_line_ids[slot].add(line_id)
                    if t['stage']==1: off_base_operands[(slot,struct.pack('<d',physical),struct.pack('<d',t['str']*t['f3']))]+=1
                else:
                    on_sel[tup]+=1; on_line_ids[slot].add(line_id)
                    if t['stage']==1: on_base_operands[(slot,struct.pack('<d',physical),struct.pack('<d',t['str']*t['f3']))]+=1
                if abs(physical-TARGETS[slot])<=5e-10:
                    if label=="base": base_probe[tup]+=1
                    if label=="on": on_probe[tup]+=1
            elif label in ("base","on"):
                key=event_key(t,False)
                (base_other if label=="base" else on_other)[key]+=1
    for center in TARGETS:
        if base_sel[(1,center)]<=0 or base_sel[(2,center)]<=0:
            raise RuntimeError(f"baseline trace lacks selected baseline/coupling event at {center}")
        if len(base_line_ids[center])!=1:
            raise RuntimeError(f"expected one predeclared source line identity at {center}; got {len(base_line_ids[center])}")
        if off_line_ids[center]!=base_line_ids[center] or on_line_ids[center]!=base_line_ids[center]:
            raise RuntimeError(f"selected source line identity roster changed at {center}")
        if off_sel[(1,center)]!=base_sel[(1,center)] or off_sel[(2,center)]!=base_sel[(2,center)]:
            raise RuntimeError(f"OFF selected trace event roster differs at {center}")
        if on_sel[(1,center)]!=base_sel[(1,center)] or on_sel[(2,center)]!=0:
            raise RuntimeError(f"ON selected event was not uniquely omitted at {center}")
        if base_probe[(2,center)]<=0 or on_probe[(2,center)]!=0:
            raise RuntimeError(f"fixed physical R3 probe does not confirm coupling omission at {center}")
    if base_base_operands!=off_base_operands or base_base_operands!=on_base_operands:
        raise RuntimeError("selected CO2 baseline operands changed between modes")
    if base_other!=on_other: raise RuntimeError("ON changed nonselected term operand/identity roster")
    # Save physical-coordinate snapshots; the same coordinate can occupy a shifted slot after panel carry.
    carry=[]
    for s in snaps:
        for center in TARGETS.values():
            j0=round((center-s['vft'])/s['dvr3'])
            j=j0+1
            if 1<=j<=s['max3']:
                actual=s['vft']+j0*s['dvr3']
                if abs(actual-center)<=5e-10:
                    carry.append({'snapshot_seq':s['seq'],'stage':s['stage'],'panel_vft':s['vft'],
                                  'dvr3':s['dvr3'],'j3_1based':j,'physical_wavenumber_cm-1':actual,
                                  'r3_value':s['_r3'][j-1]})
    return {'status':'PASS_SCOPED_SELECTED_COUPLING_EVENTS_OMITTED_DESCRIPTIVE_ONLY',
            'baseline_selected_counts':{f"{s}:{c:.13f}":n for (s,c),n in sorted(base_sel.items())},
            'on_selected_counts':{f"{s}:{c:.13f}":n for (s,c),n in sorted(on_sel.items())},
            'selected_source_line_instances':{f"{c:.13f}":len(base_line_ids[c]) for c in TARGETS},
            'selected_baseline_operands_same_across_modes':True,
            'nonselected_operand_identity_multiset_equal':True,
            'fixed_probe_baseline_coupling_counts':{f"{c:.13f}":base_probe[(2,c)] for c in TARGETS},
            'fixed_probe_on_coupling_counts':{f"{c:.13f}":on_probe[(2,c)] for c in TARGETS},
            'on_r3_physical_coordinate_snapshots':carry,
            'numeric_acceptance':'DESCRIPTIVE_ONLY_NO_POSITIVITY_OR_ACCURACY_GATE'}
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--baseline-r3',type=Path,required=True)
    ap.add_argument('--on-r3',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args()
    result=validate_ablation_events(a.baseline_r3,a.baseline_r3,a.on_r3)
    a.output.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'baseline_selected_counts':result['baseline_selected_counts'],'on_selected_counts':result['on_selected_counts'],'fixed_probe_baseline_coupling_counts':result['fixed_probe_baseline_coupling_counts'],'fixed_probe_on_coupling_counts':result['fixed_probe_on_coupling_counts'],'nonselected_operand_identity_multiset_equal':result['nonselected_operand_identity_multiset_equal']}))
if __name__=='__main__': main()
