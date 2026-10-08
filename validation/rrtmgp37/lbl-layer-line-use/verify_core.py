"""Replay the executed layer21 panel13/14 inventory; no physical approval."""
import math, struct, csv, io
from collections import Counter
TARGET=618.6144711111115
WIDTHS={'ENTRY':16,'WIDTH':19,'COEFFICIENT':6,'PEAK':6,'OUTCOME':4,'WRITE':8}
def require(ok,msg):
    if not ok: raise ValueError(msg)
def bits(x): return struct.pack('<d',x)
def same(a,b,msg): require(bits(a)==bits(b),msg)
def parse(trace):
    rows=[]
    for line in trace.splitlines():
        a=line.split(); require(len(a)>=10,'trace header')
        tag=a[0]; n=list(map(int,a[1:10]));v=list(map(float,a[10:]))
        require(tag in WIDTHS and len(v)==n[-1]==WIDTHS[tag] and all(math.isfinite(x) for x in v),'trace schema')
        r=dict(zip(('seq','id','block','record','slot','mol','flag','panel'),n[:8]));r.update(tag=tag,v=v)
        require(r['record']==2*r['block']+1 and 1<=r['slot']<=250 and r['panel'] in (13,14),'origin or panel')
        require(r['seq']==len(rows)+1,'complete sequence');rows.append(r)
    return rows
def inventory_csv(trace):
    records={}
    for r in parse(trace):
        if r['tag']=='ENTRY':records[r['id']]={'ENTRY':r,'writes':[]}
        elif r['tag']=='WRITE':records[r['id']]['writes'].append(r)
        else:records[r['id']][r['tag']]=r
    out=io.StringIO(newline='');writer=csv.writer(out,lineterminator='\n')
    writer.writerow(['lnc_id','panel','TAPE3_record','TAPE3_slot','encoded_molecule','flag','original_centre','shifted_centre',
      'unclamped_width','clamped_width','DV','lower_clamp','upper_clamp','outcome_reason','target_baseline_writes','target_coupling_writes',
      'target_baseline_product','target_signed_coupling_product'])
    for i,e in records.items():
        r=e['ENTRY'];w=e['WIDTH']['v'];v=r['v'];base=coupling=0.;nb=nc=0
        for q in e['writes']:
            z=q['v']
            if z[0]==1:nb+=1;base+=z[5]*z[6]
            else:nc+=1;coupling+=z[5]*z[6]*z[7]
        writer.writerow([i,r['panel'],r['record'],r['slot'],r['mol'],r['flag'],v[0],w[0],w[1],w[2],w[3],int(w[5]),int(w[6]),
            int(e['OUTCOME']['v'][0]),nb,nc,base,coupling])
    return out.getvalue().encode()
def analyze(trace,min_trace,blocks):
    rows=parse(trace); entries={};writes=[];reasons=Counter();clamps=Counter();species=Counter();
    for r in rows:
        i=r['id'];tag=r['tag'];v=r['v']
        if tag=='ENTRY':
            require(i==len(entries)+1,'unique ordered LNC entry')
            entries[i]={'ENTRY':r}; key=str(r['record']);require(key in blocks,'missing actual TAPE3 record')
            raw=blocks[key];j=r['slot']-1;require(len(raw)==39000,'TAPE3 layout')
            nu=struct.unpack_from('<d',raw,8*j)[0];s=struct.unpack_from('<f',raw,2000+4*j)[0]
            mol=struct.unpack_from('<i',raw,5000+4*j)[0];flag=struct.unpack_from('<i',raw,9000+4*j)[0]
            require((mol,flag)==(r['mol'],r['flag']),'actual TAPE3 species/flag')
            same(v[0],nu,'actual TAPE3 original centre');same(v[1],nu,'entry unshifted centre');same(v[2],s,'actual TAPE3 strength')
            require(abs(nu-TARGET)<=25 and flag>=0,'explicit centre window')
            require(v[3]>0 and v[4]>=v[3] and v[5]==64 and v[9]==0 and v[10]==0 and v[13]==0,'executed controls')
            species[str(mol%100)]+=1
            continue
        require(i in entries,'missing LNC entry');e=entries[i];origin=e['ENTRY']
        require(all(r[k]==origin[k] for k in ('block','record','slot','mol','flag')),'entry origin join')
        if tag!='WRITE':
            require(tag not in e,'duplicate stage');require(r['panel']==origin['panel'],'LNC panel join');e[tag]=r
        else:
            require('OUTCOME' in e and e['OUTCOME']['v'][0]==0,'contribution from rejected or unobserved line')
            require(r['panel']==13 and v[0] in (1,2) and v[1]==170,'selected write destination')
            if v[0]==2: require(e['COEFFICIENT']['v'][2]!=0,'coupling branch')
            same(v[4],v[3]+v[5]*v[6]*v[7] if v[0]==2 else v[3]+v[5]*v[6],'selected write replay')
            writes.append(r)
    for e in entries.values():
        require(all(k in e for k in ('WIDTH','COEFFICIENT','OUTCOME')),'complete defined width/coefficient/outcome')
        en=e['ENTRY']['v'];w=e['WIDTH']['v'];c=e['COEFFICIENT']['v'];o=e['OUTCOME']['v'];flag=e['ENTRY']['flag']
        same(w[1],(w[13]+w[12]*(w[14]-w[13]))*(w[7]+w[8]),'unclamped width lookup')
        same(w[2],min(max(w[1],w[3]),w[4]),'width clamp')
        require(w[5]==int(w[1]<w[3]) and w[6]==int(max(w[1],w[3])>w[4]),'width clamp flags')
        require(w[3:5]==en[3:5] and w[15:17]==[en[5],en[6]] and w[17]==TARGET and w[18]==0,'width controls join')
        require(w[15]*w[2]+w[0]>=w[16],'executed left support filter')
        same(c[3],1./w[2],'reciprocal clamped width');same(c[2],c[1]/c[0],'coupling ratio')
        require(o[1]==2 and o[0] in (0,5),'executed outcome stage/reason; other branches not claimed')
        if flag==0:
            require('PEAK' in e,'flag0 peak decision');p=e['PEAK']['v']
            same(p[0],p[4]*p[5],'peak calculation');require(p[1:4]==[en[11],en[12],en[10]],'peak control join')
            require((p[0]<=p[1])==(o[0]==5),'actual peak rejection reason')
            require(c[2]==0,'defined flag0 SPPSP before final zero reset')
        else: require('PEAK' not in e and o[0]==0,'coupled branch bypasses this SPEAK rejection')
        same(o[2],c[0] if o[0]==0 else 0.,'outcome SP')
        same(o[3],c[2],'outcome SPP ratio (defined before final zero assignment)')
        reasons[str(int(o[0]))]+=1;clamps['lower' if w[5] else 'upper' if w[6] else 'none']+=1
    old=[]
    for line in min_trace.splitlines():
        a=line.split()
        if a[0]=='CN_WRITE':
            n=list(map(int,a[1:12]));v=list(map(float,a[12:]));old.append((n,v))
    require(len(old)==len(writes)==1976,'all physical-target CN writes covered')
    for r,(n,v) in zip(writes,old):
        w=r['v'];e=entries[r['id']]
        require((n[1],n[2],n[5],n[6],n[7],n[8])==(21,r['panel'],int(w[1]),int(w[2]),r['slot'],int(w[0])),'parent CN write identity')
        require(len(v)==10,'parent CN width')
        for x,y in zip(w[3:],v[2:7]):same(x,y,'parent CN operand join')
        same(e['WIDTH']['v'][0],v[7],'parent shifted centre');same(e['COEFFICIENT']['v'][0],v[8],'parent SP');same(e['COEFFICIENT']['v'][2],v[9],'parent SPPSP')
    require(len(entries)==9253 and reasons==Counter({'0':5337,'5':3916}) and clamps==Counter({'none':9242,'lower':11}),'exact executed inventory')
    contributors={r['id'] for r in writes};signed={str(ph):{'writes':0,'positive_sum':0.,'negative_magnitude_sum':0.} for ph in (1,2)}
    for r in writes:
        w=r['v'];x=w[5]*w[6];x=x*w[7] if w[0]==2 else x;s=signed[str(int(w[0]))];s['writes']+=1
        s['positive_sum']+=max(x,0.);s['negative_magnitude_sum']+=max(-x,0.)
    selected=[r for r in writes if (r['record'],r['slot'],int(r['v'][0]))==(521,124,2)]
    require(len(selected)==1,'same PR160/161 selected line')
    chosen=selected[0];e=entries[chosen['id']]
    require(chosen['v'][3]>0 and chosen['v'][4]<0,'selected first-negative transition')
    contributing_clamps=Counter('lower' if entries[i]['WIDTH']['v'][5] else 'upper' if entries[i]['WIDTH']['v'][6] else 'none' for i in contributors)
    require(writes[0]['v'][3]==0,'defined selected R3 start')
    for a,b in zip(writes,writes[1:]):same(a['v'][4],b['v'][3],'all selected CN writes form one chain')
    same(writes[-1]['v'][4],-2.5643980319365688e-5,'line-only selected R3 matches PR162 continuum input')
    return {'status':'PASS_SCOPED_LAYER_SELECTION_TO_ALL_SELECTED_R3_WRITES',
      'layer':21,'panels':[13,14],'centre_window_cm1':[TARGET-25,TARGET+25],
      'LNC_entries':len(entries),'unique_TAPE3_lines':len({(e['ENTRY']['record'],e['ENTRY']['slot']) for e in entries.values()}),
      'outcomes':dict(sorted(reasons.items())),'width_clamps':dict(sorted(clamps.items())),'species_entry_counts':dict(sorted(species.items())),
      'R3_target_write_count':len(writes),'R3_target_contributing_lines':len(contributors),'contributing_width_clamps':dict(contributing_clamps),
      'target_contributor_flags':dict(Counter(str(entries[i]['ENTRY']['flag']) for i in contributors)),
      'target_unclamped_width_range':[min(entries[i]['WIDTH']['v'][1] for i in contributors),max(entries[i]['WIDTH']['v'][1] for i in contributors)],
      'selected_R3_after_all_line_writes':writes[-1]['v'][4],
      'signed_R3_contributions':signed,'selected_line':{'record':521,'slot':124,'encoded_molecule':102,'original_centre':e['ENTRY']['v'][0],
       'shifted_centre':e['WIDTH']['v'][0],'unclamped_width':e['WIDTH']['v'][1],'clamped_width':e['WIDTH']['v'][2],
       'DV':e['WIDTH']['v'][3],'left_support_passed':True,'SPEAK_rejection_bypassed':True,'first_negative_after':chosen['v'][4]},
      'scope':'All 1976 selected physical R3 CN writes joined; bounded panel13/14 LNC inventory. Not all-layer/full-band survival or every direct R1/R2 stencil contributor.',
      'grid_convergence_executed':False,'physical_partner_completeness_established':False,'physical_reference_accepted':False,'production_accepted':False}
