"""Replay bounded actual grid/threshold experiments; no physical approval."""
import math, struct
from collections import Counter
TARGET=618.6133629315808
H=0.003941167029890377
ARMS=('h','half','quarter','weak10','weak0')
WIDTHS={'ENTRY':16,'WIDTH':19,'COEFFICIENT':6,'PEAK':6,'OUTCOME':4,'WRITE':8}
def require(ok,msg):
    if not ok: raise ValueError(msg)
def same(a,b,msg): require(struct.pack('<d',a)==struct.pack('<d',b),msg)
def parse(trace):
    rows=[]
    for line in trace.splitlines():
        a=line.split();require(len(a)>=10,'trace header')
        tag=a[0];n=list(map(int,a[1:10]));v=list(map(float,a[10:]))
        require(tag in WIDTHS and len(v)==n[-1]==WIDTHS[tag] and all(math.isfinite(x) for x in v),'trace schema')
        r=dict(zip(('seq','id','block','record','slot','mol','flag','panel'),n[:8]));r.update(tag=tag,v=v)
        require(r['seq']==len(rows)+1 and r['record']==2*r['block']+1 and 1<=r['slot']<=250,'complete sequence and origin')
        rows.append(r)
    return rows

def analyze_arm(trace,min_trace,blocks,name):
    entries={};writes=[]
    for r in parse(trace):
        i=r['id'];tag=r['tag'];v=r['v']
        if tag=='ENTRY':
            require(i==len(entries)+1,'unique ordered entry');entries[i]={'ENTRY':r,'writes':[]}
            raw=blocks[str(r['record'])];j=r['slot']-1
            require(len(raw)==39000,'actual TAPE3 layout')
            same(v[0],struct.unpack_from('<d',raw,8*j)[0],'actual original centre')
            same(v[1],v[0],'unshifted centre');same(v[2],struct.unpack_from('<f',raw,2000+4*j)[0],'actual strength')
            require((r['mol'],r['flag'])==(struct.unpack_from('<i',raw,5000+4*j)[0],struct.unpack_from('<i',raw,9000+4*j)[0]),'actual species/flag')
            require(abs(v[0]-TARGET)<=5 and r['flag']>=0,'bounded centre window')
            expected=H/({'half':2,'quarter':4}.get(name,1))
            same(v[3],expected,'actual DV and requested grid ratio')
            same(v[11],({'weak10':2e-5,'weak0':0.}.get(name,2e-4))/2250.,'actual default/zero threshold normalization')
            require(v[14]>0 and 2250./(v[14]/1.4387752)>10,'executed RADFN high-frequency branch')
            require(v[4]>=v[3] and v[5]==64 and v[9]==0 and v[10]==0 and v[13]==0,'fixed controls')
            continue
        require(i in entries,'entry missing');e=entries[i];o=e['ENTRY']
        require(all(r[k]==o[k] for k in ('block','record','slot','mol','flag')),'line identity join')
        if tag=='WRITE':
            require('OUTCOME' in e and e['OUTCOME']['v'][0]==0 and v[0] in (1,2),'retained contributor')
            same(v[4],v[3]+v[5]*v[6]*v[7] if v[0]==2 else v[3]+v[5]*v[6],'actual write replay')
            e['writes'].append(r);writes.append(r)
        else:
            require(tag not in e and r['panel']==o['panel'],'stage uniqueness');e[tag]=r
    reasons=Counter();clamps=Counter();contributors={};thresholds=set();alphamax=set()
    for e in entries.values():
        require(all(t in e for t in ('WIDTH','COEFFICIENT','OUTCOME')),'complete observed stages')
        en=e['ENTRY']['v'];w=e['WIDTH']['v'];c=e['COEFFICIENT']['v'];o=e['OUTCOME']['v'];flag=e['ENTRY']['flag']
        same(w[1],(w[13]+w[12]*(w[14]-w[13]))*(w[7]+w[8]),'unclamped width lookup')
        same(w[2],min(max(w[1],w[3]),w[4]),'width clamp')
        require(w[5]==int(w[1]<w[3]) and w[6]==int(max(w[1],w[3])>w[4]),'clamp flags')
        require(w[3:5]==en[3:5] and w[17]==TARGET,'width control join')
        same(c[3],1./w[2],'inverse width');same(c[2],c[1]/c[0],'coupling ratio')
        require(o[1]==2 and o[0] in (0,5),'actual observed outcomes')
        if flag==0:
            require('PEAK' in e,'flag0 peak');p=e['PEAK']['v']
            same(p[0],p[4]*p[5],'peak calculation');require(p[1:4]==[en[11],en[12],en[10]],'threshold controls')
            require((p[0]<=p[1])==(o[0]==5),'peak rejection decision')
        else: require('PEAK' not in e and o[0]==0,'coupled line bypass')
        same(o[2],c[0] if o[0]==0 else 0.,'outcome SP');same(o[3],c[2] if o[0]==0 else 0.,'defined outcome SPPSP')
        reasons[str(int(o[0]))]+=1;clamps['lower' if w[5] else 'upper' if w[6] else 'none']+=1
        thresholds.add(en[11]);alphamax.add(en[4])
        if e['writes']:
            key=f"{e['ENTRY']['record']}:{e['ENTRY']['slot']}";require(key not in contributors,'unique contributor origin')
            phases={1:0.,2:0.}
            for r in e['writes']:
                z=r['v'];x=z[5]*z[6];x=x*z[7] if z[0]==2 else x;phases[int(z[0])]+=x
            contributors[key]={'baseline':phases[1],'coupling':phases[2],'width':w[2],'unclamped_width':w[1],'flag':flag,
              'lower_clamp':int(w[5]),'upper_clamp':int(w[6])}
    old=[]
    for line in min_trace.splitlines():
        a=line.split()
        if a[0]=='CN_WRITE':old.append((list(map(int,a[1:12])),list(map(float,a[12:]))))
    require(len(old)==len(writes)>0,'all actual target CN writes covered')
    for r,(n,v) in zip(writes,old):
        z=r['v'];e=entries[r['id']]
        require((n[1],n[2],n[5],n[6],n[7],n[8])==(21,r['panel'],int(z[1]),int(z[2]),r['slot'],int(z[0])),'CN identity')
        require(len(v)==10 and abs(v[0]+(n[5]-1)*v[1]-TARGET)<1e-7,'same physical R3 coordinate')
        for x,y in zip(z[3:],v[2:7]):same(x,y,'CN operand/state join')
        same(e['WIDTH']['v'][0],v[7],'shifted centre join');same(e['COEFFICIENT']['v'][0],v[8],'SP join');same(e['COEFFICIENT']['v'][2],v[9],'ratio join')
    require(len(thresholds)==len(alphamax)==1,'fixed layer threshold/alpha')
    signed={str(ph):{'writes':0,'positive_sum':0.,'negative_magnitude_sum':0.} for ph in (1,2)}
    for r in writes:
        z=r['v'];x=z[5]*z[6];x=x*z[7] if z[0]==2 else x;s=signed[str(int(z[0]))]
        s['writes']+=1;s['positive_sum']+=max(x,0.);s['negative_magnitude_sum']+=max(-x,0.)
    return {'actual_DV':next(iter(entries.values()))['ENTRY']['v'][3],'ALFMAX':next(iter(alphamax)),
      'effective_DPTMN':next(iter(thresholds)),'LNC_entries':len(entries),'retained':reasons['0'],'SPEAK_rejected':reasons['5'],
      'all_entry_width_clamps':dict(sorted(clamps.items())),'contributing_lines':len(contributors),
      'contributing_lower_clamps':sum(c['lower_clamp'] for c in contributors.values()),'contributing_upper_clamps':sum(c['upper_clamp'] for c in contributors.values()),
      'nonzero_R3_product_lines':sum(v['baseline']!=0 or v['coupling']!=0 for v in contributors.values()),
      'zero_R3_product_only_lines':sum(v['baseline']==0 and v['coupling']==0 for v in contributors.values()),
      'CN_writes':len(writes),'write_panels':sorted({r['panel'] for r in writes}),
      'signed_R3_contributions':signed,'contributors':contributors}

def sample_od(header,payload,nu):
    require(len(header)==32,'actual panel header');v1,v2,dv,n,pad=struct.unpack('<dddii',header)
    require(n>0 and dv>0 and len(payload)==8*n,'actual OD payload extent')
    j=round((nu-v1)/dv);require(0<=j<n and abs(v1+j*dv-nu)<1e-7,'physical coordinate on actual grid')
    require(abs(v2-(v1+(n-1)*dv))<1e-7,'panel coordinate extent')
    value=struct.unpack_from('<d',payload,8*j)[0];require(math.isfinite(value),'finite actual OD');return value

def compare(a,b):
    ka=set(a['contributors']);kb=set(b['contributors']);common=ka&kb
    def val(c):return c['baseline']+c['coupling']
    return {'common_lines':len(common),'added_lines':len(kb-ka),'removed_lines':len(ka-kb),
      'common_width_changed':sum(a['contributors'][k]['width']!=b['contributors'][k]['width'] for k in common),
      'common_R3_change':sum(val(b['contributors'][k])-val(a['contributors'][k]) for k in sorted(common)),
      'added_R3_sum':sum(val(b['contributors'][k]) for k in sorted(kb-ka)),
      'removed_R3_sum':sum(val(a['contributors'][k]) for k in sorted(ka-kb)),
      'common_R3_increases':sum(max(val(b['contributors'][k])-val(a['contributors'][k]),0.) for k in sorted(common)),
      'common_R3_decreases':sum(max(val(a['contributors'][k])-val(b['contributors'][k]),0.) for k in sorted(common)),
      'added_nonzero_lines':sum(val(b['contributors'][k])!=0 for k in kb-ka),
      'removed_nonzero_lines':sum(val(a['contributors'][k])!=0 for k in ka-kb)}

def result(arms,samples):
    require(set(arms)==set(samples)==set(ARMS),'complete five ON arms')
    for a in ARMS:
        require(len(samples[a])==81,'81 shared samples');same(arms[a]['ALFMAX'],arms['h']['ALFMAX'],'fixed alpha upper bound')
    for a in ('half','quarter'):same(arms[a]['effective_DPTMN'],arms['h']['effective_DPTMN'],'grid axis fixed threshold')
    require(arms['weak10']['effective_DPTMN']>0 and abs(arms['weak10']['effective_DPTMN']/arms['h']['effective_DPTMN']-.1)<1e-15,'tenfold threshold')
    same(arms['weak0']['effective_DPTMN'],0.,'explicit zero is not default')
    comparisons={}
    for a,b in (('h','half'),('half','quarter'),('h','weak10'),('h','weak0')):
        d=compare(arms[a],arms[b]);d.update(target_OD_change=samples[b][40]-samples[a][40],max_shared_OD_abs_change=max(abs(y-x) for x,y in zip(samples[a],samples[b])))
        comparisons[a+'->'+b]=d
    summary={a:{k:v for k,v in arms[a].items() if k!='contributors'} for a in ARMS}
    for a in ARMS:summary[a].update(target_OD=samples[a][40],shared_window_min_OD=min(samples[a]),shared_window_negative_samples=sum(x<0 for x in samples[a]))
    return {'status':'PASS_SCOPED_EXECUTED_GRID_AND_THRESHOLD_COMPARISON','IOD':2,'target_cm1':TARGET,
      'historical_target_cm1':618.6144711111115,'historical_IOD0_selected_OD':-0.009028119955355695,
      'shared_samples':81,'comparison_interpolation_used':False,'arms':summary,'comparisons':comparisons,
      'formal_convergence_tolerance_defined':False,'physical_reference_accepted':False,'production_accepted':False,
      'scope':'Nearby nested exact-DV point and 81 layer21 OD samples; bounded +/-5 cm-1 line inventory and all target R3 writes. Historical IOD0 FAIL retained. R1/R2/continuum contribution changes are not fully attributed by R3 line sums.'}
