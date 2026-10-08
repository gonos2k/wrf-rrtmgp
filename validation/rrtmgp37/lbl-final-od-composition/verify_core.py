"""Replay observed selected PANEL arithmetic; physical validity remains unapproved."""
import math,struct
TARGET=618.6144711111115

def require(ok,message):
    if not ok:raise ValueError(message)

def bits(x):return struct.pack('<d',x)
def same(a,b,message):require(bits(a)==bits(b),message)
def decode(trace):
    rows=[]
    for seq,line in enumerate(trace.splitlines(),1):
        a=line.split();require(len(a)>=5,'record width')
        tag=a[0];ints=list(map(int,a[1:5]));v=list(map(float,a[5:]))
        require(ints==[seq,21,14,len(v)],'sequence/layer/panel/width')
        require(all(math.isfinite(x) for x in v),'finite trace')
        rows.append((tag,v))
    return rows

def frame(v):
    require(len(v)==61,'frame width')
    return {'grid':v[:4],'R1':dict(zip(range(289,325),v[4:40])),'R2':dict(zip(range(72,85),v[40:53])),'R3':dict(zip(range(17,25),v[53:61]))}

def deposit(before,src,index):
    base=index-((index-1)%4);j=(base-1)//4+1;r=(index-1)%4
    if r==0:return before+src[j]
    a,b,c,d=[src[k] for k in (j-1,j,j+1,j+2)]
    if r==1:return before+(-7/128)*a+(105/128)*b+(35/128)*c+(-5/128)*d
    if r==2:return before+(-1/16)*(a+d)+(9/16)*(b+c)
    return before+(-5/128)*a+(35/128)*b+(105/128)*c+(-7/128)*d

def analyze(trace,header,data):
    rows=decode(trace)
    expected_tags=['PRE_XSECT','PRE_EXTRA','EXTRA_FLAGS']+['XINT_EXTRA']*8+['CONT_META','POST_EXTRA','PRE_PANEL','PANEL_META','POST_R2','POST_R1']+['RAD_MULT']*36+['PRE_OUTPUT']
    require([t for t,v in rows]==expected_tags,'ordered record roster')
    singles=['PRE_XSECT','PRE_EXTRA','EXTRA_FLAGS','POST_EXTRA','CONT_META','PRE_PANEL','PANEL_META','POST_R2','POST_R1','PRE_OUTPUT']
    d={}
    for tag in singles:
        hits=[v for t,v in rows if t==tag];require(len(hits)==1,'unique '+tag);d[tag]=hits[0]
    require(set(t for t,v in rows)==set(singles+['XINT_EXTRA','RAD_MULT']),'exact tags')
    frames={k:frame(d[k]) for k in singles if k not in ('EXTRA_FLAGS','PANEL_META','CONT_META')}
    vft,dv,dv2,dv3=frames['PRE_PANEL']['grid']
    for k,f in frames.items():require(f['grid']==[vft,dv,dv2,dv3],'grid continuity '+k)
    same(vft+304*dv,TARGET,'target coordinate R1');same(vft+76*dv2,TARGET,'target coordinate R2');same(vft+19*dv3,TARGET,'target coordinate R3')
    require(d['EXTRA_FLAGS']==[0,1,1,0,33,2432,13,612,6,155],'actual extra/valid range flags')
    meta=d['PANEL_META'];require(len(meta)==11 and meta[:7]==[33,2432,13,609,0,0,0],'actual output route')
    same(meta[7],vft+32*dv,'V1P');same(meta[9],dv,'DVP');require(meta[10]==2400,'NLIM')
    # XSECTM was active, but selected array ranges did not change.
    require(frames['PRE_XSECT']==frames['PRE_EXTRA'],'selected cross-section array invariance')
    for key in ('R1','R2'):require(frames['PRE_EXTRA'][key]==frames['POST_EXTRA'][key],'extra preserves '+key)
    extra=[v for t,v in rows if t=='XINT_EXTRA'];require(len(extra)==8 and [int(v[0]) for v in extra]==list(range(17,25)),'exact continuum destinations')
    cm=d['CONT_META'];require(len(cm)==4 and cm[2]>0 and cm[3]>=4,'continuum source extent')
    changes=[];checks=0
    for v in extra:
        require(len(v)==21,'XINT stencil width')
        i,j=map(int,v[:2]);v1,v2,da,af,vi,vj,rec,p,c,b,b1,b2,a0,a1,a2,a3,con,old,new=v[2:]
        require(v[0]==i and v[1]==j and [v1,v2,da]==cm[:3] and af==1,'continuum route')
        require(2<=j and j+2<=int(cm[3]),'defined source extent')
        same(vi,vft+(i-1)*dv3,'XINT VI');same(rec,1/da,'XINT RECDVA');same(vj,v1+(j-1)*da,'XINT VJ')
        same(p,rec*(vi-vj),'XINT P');same(c,(3-2*p)*p*p,'XINT C');same(b,.5*p*(1-p),'XINT B');same(b1,b*(1-p),'XINT B1');same(b2,b*p,'XINT B2')
        expected=-a0*b1+a1*(1-c+b2)+a2*(c+b1)-a3*b2
        same(con,expected,'XINT CONTI');same(old,frames['PRE_EXTRA']['R3'][i],'XINT old');same(new,old+con*af,'XINT update');same(new,frames['POST_EXTRA']['R3'][i],'XINT new')
        changes.append({'R3_index':i,'source_J':j,'continuum_increment':con*af,'before':old,'after':new});checks+=12
    require(frames['POST_EXTRA']==frames['PRE_PANEL'],'continuum to PANEL join')
    pre=frames['PRE_PANEL'];r2=frames['POST_R2'];r1=frames['POST_R1'];out=frames['PRE_OUTPUT']
    for key in ('R1','R3'):require(pre[key]==r2[key],'R2 stage preserves '+key)
    for k,old in pre['R2'].items():same(r2['R2'][k],deposit(old,pre['R3'],k),'R3 to R2 '+str(k));checks+=1
    for key in ('R2','R3'):require(r2[key]==r1[key] and r1[key]==out[key],'R1/output preserves '+key)
    for k,old in r2['R1'].items():same(r1['R1'][k],deposit(old,r2['R2'],k),'R2 to R1 '+str(k));checks+=1
    rad=[v for t,v in rows if t=='RAD_MULT'];require(len(rad)==36 and [v[0] for v in rad]==list(range(289,325)),'exact radiation destinations')
    samples=[]
    require(len(header)==32,'OD panel header layout')
    v1p,v2p,dvp,n=struct.unpack('<3dq',header);require(n==2400 and len(data)==8*n,'OD panel payload shape')
    same(v1p,meta[7],'OD V1P');same(v2p,meta[8],'OD V2P');same(dvp,dv,'OD DVP')
    od=struct.unpack('<'+str(n)+'d',data)
    for v in rad:
        require(len(v)==6,'radiation record width');i=int(v[0]);nu,old,mul,new,xkt=v[1:]
        same(nu,vft+(i-1)*dv,'radiation physical coordinate');same(old,r1['R1'][i],'radiation input');require(mul>0 and xkt>0,'radiation positive multiplier')
        same(new,old*mul,'radiation multiplication');same(new,out['R1'][i],'output join')
        sample=i-33+1;same(new,od[sample-1],'actual OD payload')
        require(abs(v1p+(sample-1)*dvp-nu)<1e-10,'OD physical coordinate')
        samples.append({'R1_index':i,'OD_sample_1based':sample,'physical_wavenumber_cm1':nu,'pre_radiation':old,'radiation_multiplier':mul,'OD':new});checks+=6
    selected=next(x for x in samples if x['R1_index']==305)
    require(selected['OD']<0,'negative final OD retained')
    require(sum(r['OD']<0 for r in samples)==31,'selected output sign roster')
    selected.update(R3_pre_continuum=frames['PRE_EXTRA']['R3'][20],continuum_increment=next(x['continuum_increment'] for x in changes if x['R3_index']==20),R3_post_continuum=pre['R3'][20],R2_before_deposit=pre['R2'][77],R2_after_deposit=r2['R2'][77],R1_before_deposit=pre['R1'][305])
    return {'schema':'UDM37_SELECTED_FINAL_OD_COMPOSITION_V1','status':'PASS_SCOPED_SAME_RUN_COMPOSITION_NEGATIVE_OD_RETAINED','selected':selected,'samples':samples,'continuum':changes,'exact_arithmetic_and_value_checks':checks,'trace_records':len(rows),'negative_selected_samples':31,'observed_cross_section_change_in_selected_ranges':False,'R4_active':False,'JRAD':0,'DVOUT':0,'raw_OD_panel_included':True,'independent_continuum_or_RADFNI_generation_validated':False,'line_resolved_full_component_ancestry':False,'upstream_YG_physical_provenance_authenticated':False,'physical_reference_accepted':False,'production_accepted':False}
