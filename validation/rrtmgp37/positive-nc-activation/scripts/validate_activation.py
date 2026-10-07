#!/usr/bin/env python3
"""Saved-only validator for the activation probe; no model launch here."""
import argparse, hashlib, json, math, pathlib, re, struct, sys

NAME = re.compile(r'^number_d(?P<d>\d+)_tile(?P<tile>\d+)_i(?P<i>\d+)_j(?P<j>\d+)_step(?P<step>\d+)_stage(?P<stage>\d+)_sub(?P<substep>\d+)\.raw$')
EXPECTED = {(step,stage,(1 if stage in (21,23,30,31) else 0))
            for step in (1,2) for stage in (10,11,20,21,23,30,31,40,50,51)}

def f32(x): return struct.unpack('<f',struct.pack('<f',float(x)))[0]
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def pin(p): return {'path':str(p.resolve()),'sha256':sha(p),'size_bytes':p.stat().st_size}
def mul(a,b): return f32(f32(a)*f32(b))
def add(a,b): return f32(f32(a)+f32(b))
def sub(a,b): return f32(f32(a)-f32(b))
def div(a,b): return f32(f32(a)/f32(b))
def source_fsvp_water(t,p=None):
    # Reproduce the source's REAL32 table construction and interpolation order.
    n=7501; xmin=f32(180.0); xmax=f32(330.0)
    xinc=div(sub(xmax,xmin),f32(n-1))
    c1=sub(f32(1.0),div(xmin,xinc)); c2=div(f32(1.0),xinc)
    # Source constants from module_mp_udm.F. Float32 operations mirror default REAL.
    cliq=f32(4190.0); cvap=f32(1870.0); hvap=f32(2501000.0); rv=f32(461.5); ttp=f32(273.16); psat=f32(610.78)
    dldt=sub(cvap,cliq); xa=div(-dldt,rv); xb=add(xa,div(hvap,mul(rv,ttp)))
    table=[]
    for j in range(1,n+1):
        x=add(xmin,mul(f32(j-1),xinc)); tr=div(ttp,x)
        # Table is water-only, hence the source's t >= ttp branch always uses xa/xb.
        powpart=f32(math.pow(float(tr),float(xa)))
        first=mul(psat,powpart)
        e=f32(math.exp(float(mul(xb,sub(f32(1.0),tr)))))
        table.append(mul(first,e))
    xj=min(max(add(c1,mul(c2,t)),f32(1.0)),f32(n))
    jx=min(int(xj),n-1)  # Fortran integer assignment truncates; 1-based jx.
    frac=sub(xj,f32(jx))
    lo=table[jx-1]; hi=table[jx]
    es=add(lo,mul(frac,sub(hi,lo)))
    cap=None
    if p is not None:
        cap=mul(f32(0.99),p)
        es=min(es,cap)
    return es, {'table_index_1based':jx,'fraction':frac,'es_lower':lo,'es_upper':hi,'pressure_cap_Pa':cap}
def qsat_source(t,p,ep2=0.6217504143714905,qmin=1e-15):
    es,_=source_fsvp_water(t,p)
    return max(div(mul(ep2,es),sub(p,es)),f32(qmin))
def parse_packet(path):
    lines=path.read_text().splitlines()
    if len(lines)!=47 or lines[0]!='UDM37NUM1': raise ValueError(f'{path.name}: packet magic/rows')
    hdr=[int(x) for x in lines[1].split()]
    if len(hdr)!=12: raise ValueError(f'{path.name}: header fields')
    clock=[float(x) for x in lines[2].split()]
    if len(clock)!=3 or not all(math.isfinite(x) for x in clock): raise ValueError(f'{path.name}: clock')
    rows=[]
    for index,line in enumerate(lines[3:],1):
        f=line.split()
        if len(f)!=15 or int(f[0])!=index: raise ValueError(f'{path.name}: row schema/index')
        vals=[float(x) for x in f[1:]]
        if not all(math.isfinite(x) for x in vals): raise ValueError(f'{path.name}: nonfinite')
        if any(f32(v)!=v for v in vals): raise ValueError(f'{path.name}: not promoted REAL32')
        rows.append(vals)
    return hdr,clock,rows

def validate(directory):
    directory=pathlib.Path(directory).resolve()
    files=sorted(directory.glob('*.raw'))
    if len(files)!=20: raise ValueError(f'expected 20 number packets, found {len(files)}')
    got={}; packet_pins=[]
    for path in files:
        m=NAME.fullmatch(path.name)
        if not m: raise ValueError(f'unrecognized packet name {path.name}')
        ident={k:int(v) for k,v in m.groupdict().items()}
        key=(ident['step'],ident['stage'],ident['substep'])
        if key not in EXPECTED or key in got: raise ValueError(f'unexpected/duplicate packet {key}')
        if (ident['d'],ident['tile'],ident['i'],ident['j'])!=(1,1,23,2): raise ValueError(f'wrong observer identity {ident}')
        hdr,clock,rows=parse_packet(path)
        expected_avail=17 if ident['stage']==30 else (29 if ident['stage']==31 else (2 if ident['stage']==51 else 0))
        if ident['stage'] in (21,23): expected_avail=17
        if hdr[:10]!=[1,ident['step'],ident['stage'],ident['substep'],1,23,2,1,44,32]: raise ValueError(f'{path.name}: identity/header')
        if hdr[10]!=expected_avail or hdr[11]!=(1 if ident['step']==1 else 0): raise ValueError(f'{path.name}: availability/initializer {hdr[10:]}')
        if clock[0]!=(ident['step']-1)*1.0 or clock[1:]!=[60.0,100000000.0]: raise ValueError(f'{path.name}: clock mismatch {clock}')
        got[key]={'path':path,'header':hdr,'clock':clock,'rows':rows}
        packet_pins.append(pin(path))
    if set(got)!=EXPECTED: raise ValueError(f'packet roster mismatch missing={sorted(EXPECTED-set(got))}')
    for step in (1,2):
        clocks=[got[(step,stage,sub)]['clock'] for _,stage,sub in EXPECTED if _==step]
        if len(set(tuple(x) for x in clocks))!=1: raise ValueError(f'same-step packet clock mismatch at step {step}')
    if got[(2,30,1)]['clock'][0]-got[(1,30,1)]['clock'][0] != 1.0: raise ValueError('XTIME must advance exactly one minute between observed steps')
    step_reports=[]
    for step in (1,2):
        entry_packet=got[(step,21,1)]; a=got[(step,30,1)]; b=got[(step,31,1)]
        if entry_packet['clock']!=a['clock'] or a['clock']!=b['clock']: raise ValueError('stage21/30/31 clock differs')
        entry=entry_packet['rows'][6]; pre=a['rows'][6]; post=b['rows'][6]
        # row fields: T,P,QV,QC,QR,NN,NC,NR,DEN,DEND,RE,NC_ACT,PC_ACT,DT
        es,esinfo=source_fsvp_water(pre[0]); qsat=qsat_source(pre[0],pre[1]); rh=max(div(pre[2],qsat),f32(1e-15))
        ncact=post[11]; pcact=post[12]; dt=post[13]
        if dt<=0: raise ValueError('stage31 DT_SUBSTEP must be positive')
        rh_gate = rh>1.0
        activation_gate = ncact>0.0
        pc_gate = pcact>0.0
        # Source-ordered REAL32 checks for number and water updates; process rates are kept separate.
        ccnmin=f32(50000000.0); ncmin=f32(1.0e-3)
        dn=mul(ncact,dt)
        expected_nn=max(sub(pre[5],dn),ccnmin)
        expected_nc=max(add(pre[6],dn),ncmin)
        mass=mul(pcact,dt)
        expected_qv=max(sub(pre[2],mass),f32(0.0))
        expected_qc=max(add(pre[3],mass),f32(0.0))
        # Host-call thermodynamics: module_model_constants CP=1004.5, CPV=4*RV,
        # XLV=2.5e6, SVPT0=273.15; module_physics_init calls udminit
        # with (CLIQ,CPV), so cached XLV1=CLIQ-CPV. UDM initializes CPM/XLV
        # before subcycling (source lines 996-997); stage21 is that entry state.
        cpd=f32(1004.5); cpv=f32(4.0*f32(461.6)); cliq=f32(4190.0); xlv0=f32(2500000.0); t0c=f32(273.15)
        q_entry=max(entry[2],f32(1e-15))
        cpm=add(mul(cpd,sub(f32(1.0),q_entry)),mul(q_entry,cpv))
        xlv1=sub(cliq,cpv)
        xlv=sub(xlv0,mul(xlv1,sub(entry[0],t0c)))
        tend=add(pre[0],mul(div(mul(pcact,xlv),cpm),dt))
        updates={'NN_expected':expected_nn,'NN_observed':post[5],'NN_exact':post[5]==expected_nn,
          'NC_expected':expected_nc,'NC_observed':post[6],'NC_exact':post[6]==expected_nc,
          'QV_expected':expected_qv,'QV_observed':post[2],'QV_exact':post[2]==expected_qv,
          'QC_expected':expected_qc,'QC_observed':post[3],'QC_exact':post[3]==expected_qc,
          'T_expected':tend,'T_observed':post[0],'T_exact':post[0]==tend}
        if not all(updates[k] for k in ('NN_exact','NC_exact','QV_exact','QC_exact','T_exact')):
            raise ValueError(f'stage30→31 source-state update mismatch at step={step}: {updates}')
        step_reports.append({'step':step,'substep':1,'domain':1,'tile':1,'i':23,'j':2,'k':7,
          'clock':a['clock'],'stage21_entry_T_K':entry[0],'stage21_entry_QV':entry[2],
          'cached_CPM_source_replay':cpm,'cached_XLV_source_replay':xlv,'stage30_availability':a['header'][10],'stage31_availability':b['header'][10],
          'T_K':pre[0],'P_Pa':pre[1],'QV':pre[2],'NN_before_m3':pre[5],'NC_before_m3':pre[6],
          'source_lookup':esinfo,'es_Pa':es,'qsat':qsat,'RH_source_replay':rh,'RH_gate':rh_gate,
          'NC_ACT_RATE_m3_s':ncact,'PC_ACT_RATE_kgkg_s':pcact,'dt_substep_s':dt,
          'activation_gate':activation_gate,'positive_PC_ACT_RATE_gate':pc_gate,'source_stored_updates':updates,
          'rounded_stored_increment_NC_m3':post[6]-pre[6],
          'positive_process_rate_separate_from_stored_increment':bool(ncact>0 and post[6]-pre[6]>0),
          'thermodynamic_source_pins':'module_model_constants.F, module_microphysics_driver.F, module_physics_init.F, module_mp_udm.F',
          'scope':'Source-equation replay at one selected same-call level. Stage21 state supplies cached CPM/XLV inputs; no unit authority or physical acceptance.'})
    rh_ok=any(x['RH_gate'] for x in step_reports)
    act_ok=any(x['activation_gate'] for x in step_reports)
    pc_ok=any(x['positive_PC_ACT_RATE_gate'] for x in step_reports)
    if any(x['activation_gate'] and not x['positive_PC_ACT_RATE_gate'] for x in step_reports): raise ValueError('positive NC_ACT_RATE did not carry a positive PC_ACT_RATE')
    joint=any(x['RH_gate'] and x['activation_gate'] and x['positive_PC_ACT_RATE_gate'] for x in step_reports)
    status='PASS_DISCRIMINATING_ACTIVATION_OBSERVED' if joint else 'NON_DISCRIMINATING_ACTIVATION_NOT_OBSERVED'
    return {'schema':'UDM37_ACTIVATION_OBSERVER_VALIDATION_V1','status':status,'packet_count':20,'row_count':880,
      'packet_pins':packet_pins,'selected_source':step_reports,'separate_gates':{'stage30_source_lookup_RH_gt_1':rh_ok,'stage31_NC_ACT_RATE_gt_0':act_ok,'stage31_PC_ACT_RATE_gt_0':pc_ok,'same_step_joint_gate':joint},
      'physical_acceptance':False,'scientific_accepted':False,
      'limitations':'The manufactured one-cell QVAPOR intervention tests conditional response in this selected state. It does not establish QNC units, activation/population physical validity, PSD/LUT consistency, or forecast relevance.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path)
    a=p.parse_args();result=validate(a.directory);text=json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n'
    if a.output:
        with a.output.open('x') as f:f.write(text)
    print(json.dumps({'status':result['status'],'packet_count':result['packet_count'],'separate_gates':result['separate_gates'],'scientific_accepted':False}))
    if result['status']!='PASS_DISCRIMINATING_ACTIVATION_OBSERVED':return 2
    return 0
if __name__=='__main__':sys.exit(main())
