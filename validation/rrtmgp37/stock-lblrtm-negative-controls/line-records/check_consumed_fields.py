#!/usr/bin/env python3
"""Supplement a retained failed byte comparison; do not normalize either file."""
import collections, hashlib, importlib.util, itertools, json, struct
from pathlib import Path
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
D=ROOT/'build/udm37-lblrtm-nocpl-line-consumption-v1'
P=ROOT/'build/udm37-lblrtm-nocpl-line-compare-v1/compare_tape3.py'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
spec=importlib.util.spec_from_file_location('retained_comparator',P); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
prior=ROOT/'build/udm37-lblrtm-nocpl-line-compare-v1/results/comparison.json'
r=json.loads(prior.read_text()); assert r['status']=='FAIL_SCOPED_TAPE3_LINE_COMPARISON'
a,sa=m.inspect_tape3(m.CPL_RUN/'TAPE3','cpl'); b,sb=m.inspect_tape3(ROOT/'build/udm37-lblrtm-nocpl-control-v2/run-v2/TAPE3','nocpl')
diffs=collections.Counter(); pattern=collections.Counter(); locations=collections.Counter(); n=0
for x,y in itertools.zip_longest(a,b):
 assert x is not None and y is not None
 n+=1
 changed=[k for k in m.PHYSICAL_FIELDS if x['signature'][k]!=y['signature'][k]]
 for k in changed: diffs[k]+=1
 if changed:
  assert changed==['additional_broadening_flags']
  xf=struct.unpack('<7i',x['signature'][changed[0]]); yf=struct.unpack('<7i',y['signature'][changed[0]])
  assert xf in ((-654321,0,0,0,0,0,0),(0,0,0,0,0,0,0))
  assert yf in ((-654321,0,0,0,0,0,0),(0,0,0,0,0,0,0))
  assert xf[1:]==yf[1:]==(0,0,0,0,0,0)
  assert (x['slot']==1 and xf[0]==-654321) or (y['slot']==1 and yf[0]==-654321)
  pattern[f'{xf}->{yf}']+=1
  locations['cpl_first_slot' if x['slot']==1 else 'nocpl_first_slot']+=1
assert n==648464 and diffs=={'additional_broadening_flags':5702}
flags={}
for arm in ('continuum','sample8','nocpl','nocpl-sample8'):
 p=ROOT/f'build/udm37-lblrtm-held-state-{arm}-od-run-v1/runs/od-v1/TAPE6'
 lines=p.read_text().splitlines(); k=next(i for i,s in enumerate(lines) if 'HIRAC' in s and 'IBRD' in s)
 f=dict(zip(lines[k].split(),map(int,lines[k+1].split())))
 assert f['IBRD']==0 and f['HIRAC']==1 and f['LBLF4']==0
 flags[arm]={'sha256':sha(p),'flags':f}
lnfl=m.LNFL; src=lnfl.read_text()
assert 'equivalence (addflag(1,1),lstw2)' in src and 'lstw2 = -654321' in src
op=ROOT/'build/udm37-lblrtm-stock-build-v1/attempt-1/source/LBLRTM/src/oprop.f90'
s=op.read_text()
assert 'if(sum(brd_mol_flg(:,i)).gt.0.AND.ibrd.gt.0)' in s
assert 'if (brd_mol_flg(m,i).gt.0)' in s
out={'schema':'UDM37_LNFL_NOCPL_CONSUMED_FIELD_REVIEW_V1','status':'PASS_SCOPED_IBRD0_CONSUMED_LINE_FIELDS_WITH_RAW_FAILURE_RETAINED','strict_byte_comparison_status':r['status'],'prior_report_sha256':sha(prior),'comparator_sha256':sha(P),'paired_ordinary_lines':n,'raw_mismatch_counts':dict(diffs),'mismatch_value_patterns':dict(pattern),'mismatch_locations':dict(locations),'record_inputs':{'coupled_sha256':sa['sha256'],'nocpl_sha256':sb['sha256']},'source_pins':{'lnfl':sha(lnfl),'oprop':sha(op)},'executed_flags':flags,'explanation':'The 5702 differences are the LNFL length sentinel -654321 in ADDFLAG(1,1), versus zero at the corresponding ordinary record after coupling removal changes block boundaries. All six other flag components and every other non-IFLG field are byte exact. LNFL stores its length sentinel via EQUIVALENCE and has no EXBRD token in either executed control. LBLRTM executes with IBRD=0; guarded broadening terms are inactive. The unguarded O2 self-shift test reads component 7, which is zero in both files. This supplements rather than replaces the strict raw-field FAIL.','limitations':['No TAPE3 bytes changed or ignored by the original comparison.','No opacity sign or flux accuracy acceptance.','Does not certify controls at IBRD>0 or EXBRD active.','The molecular code follows LNFL MOD(MOL,100); no isotope/species relabeling.'],'model_invocations':0}
(D/'report.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
print(out['status'],n,dict(diffs))
