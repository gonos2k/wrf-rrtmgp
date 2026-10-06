#!/usr/bin/env python3
"""Extract pinned WRF statements/constants, then run a manufactured density-basis fixture."""
import argparse, hashlib, json, math, os, re, struct, subprocess, time
from pathlib import Path

PINNED_HEAD = "246e6f74f3b4fdb0727ea6beeb51edafae435173"
PINNED_FILES = {
    "udm": ("WRF/phys/module_mp_udm.F", "9b7b878b263f6b0111edba4cfb1c6c30e53b3f7534035cda2c0411a573b81c2c"),
    "prep": ("WRF/dyn_em/module_big_step_utilities_em.F", "b8c46ba091d017f70e2d75b9a87e198a0242f6c80341cd402d65677ba339a532"),
    "driver": ("WRF/phys/module_microphysics_driver.F", "5f365f23e540a7ef3a37153426517aedf9c79b7802d37d8240ac880a0ed46f25"),
    "constants": ("WRF/share/module_model_constants.F", "5b80377fecdc18a5f0ad38d3b6c15cfc86ad5d76701adbbbb08a08698d0f7062"),
}
EPS32 = 2.0 ** -23
TOL_FACTOR = 16.0


def sha_bytes(b): return hashlib.sha256(b).hexdigest()
def sha_file(p): return sha_bytes(Path(p).read_bytes())
def f32(value): return struct.unpack('=f', struct.pack('=f', value))[0]
def atomic_json(path, obj):
    path=Path(path); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
    os.replace(tmp,path)


def durable_run(argv, cwd, log, env, receipt, key, manifest):
    start=time.time()
    try:
        p=subprocess.run(argv,cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        output=p.stdout; rc=p.returncode
    except Exception as e:
        output=f"{type(e).__name__}: {e}\n"; rc=127
    Path(log).write_text(output)
    row={"argv":argv,"cwd":str(cwd),"returncode":rc,"started_epoch":start,"ended_epoch":time.time(),"log":Path(log).name,"log_sha256":sha_file(log),"stdout_sha256":sha_bytes(output.encode())}
    manifest[key]=row
    atomic_json(receipt,manifest)
    return rc,output,row


def unique_exact_line(path, predicate, label):
    lines=Path(path).read_text(errors='strict').splitlines()
    found=[line for line in lines if predicate(line)]
    if len(found)!=1:
        raise ValueError(f"expected one {label} source line, found {len(found)}")
    return found[0]


def extract_contract(src):
    files={k:src/v[0] for k,v in PINNED_FILES.items()}
    hashes={k:sha_file(p) for k,p in files.items()}
    for k,(_,expected) in PINNED_FILES.items():
        if hashes[k]!=expected: raise ValueError(f"pinned source hash mismatch for {k}: {hashes[k]}")
    prep=files['prep']; udm=files['udm']; driver=files['driver']; constants=files['constants']
    host=unique_exact_line(prep,lambda s: re.match(r'^\s*rho\s*\(i,k,j\)\s*=\s*1\./\s*\(al\(i,k,j\)\+alb\(i,k,j\)\)\s*$',s,re.I) is not None,"host rho assignment")
    dend=unique_exact_line(udm,lambda s: re.match(r'^\s*dend\s*\(k,i\)\s*=\s*\(p\(k,i\)/t\(k,i\)-den\(k,i\)\*rv\)/\(rd-rv\)\s*!\s*dry density\s*$',s,re.I) is not None,"UDM DEND assignment")
    constlines=Path(constants).read_text(errors='strict').splitlines()
    def const_value(name):
        matches=[]
        pat=re.compile(r'^\s*REAL\s*,\s*PARAMETER\s*::\s*'+name+r'\s*=\s*([0-9]+(?:\.[0-9]*)?(?:[EeDd][+-]?[0-9]+)?)\b',re.I)
        for line in constlines:
            m=pat.match(line)
            if m: matches.append((m.group(1),line))
        if len(matches)!=1: raise ValueError(f"expected exactly one {name} real parameter, got {len(matches)}")
        return float(matches[0][0].replace('D','E').replace('d','e')),matches[0][1]
    rd,rdline=const_value('r_d'); rv,rvline=const_value('r_v')
    driverlines=Path(driver).read_text(errors='strict').splitlines()
    uses=[s for s in driverlines if re.match(r'^\s*USE\s+module_model_constants\b',s,re.I)]
    if len(uses)!=1: raise ValueError(f"expected exactly one module_model_constants USE in driver, got {len(uses)}")
    if rd==rv: raise ValueError("Rd-Rv denominator is zero")
    return {"files":files,"hashes":hashes,"host_line":host,"dend_line":dend,"host_statement_sha256":sha_bytes(host.encode()),"dend_statement_sha256":sha_bytes(dend.encode()),"rd":rd,"rv":rv,"rd_line":rdline,"rv_line":rvline,"driver_use":uses[0]}


def parse_output(text, rd, rv):
    lines=text.splitlines()
    if not lines or lines[0].split()!=['REAL_BITS','32']:
        raise ValueError("default REAL storage_size is not the required 32 bits")
    expected=[]; rows=[]
    for ir,rhod in enumerate((0.5,1.0,1.5),1):
        for iq,qv in enumerate((0.0,0.001,0.01,0.02,0.03),1):
            for it,temp in enumerate((250.0,300.0),1):
                expected.append((len(expected)+1,ir,iq,it))
    seen=[]
    for line in lines[1:]:
        f=line.split()
        if len(f)!=12: raise ValueError(f"unexpected output row: {line!r}")
        case,ir,iq,it=map(int,f[:4]); vals=list(map(float,f[4:]))
        if not all(math.isfinite(v) for v in vals): raise ValueError(f"nonfinite value in case {case}")
        seen.append((case,ir,iq,it))
        rhod,qv,temp,rho_active,dend_dry,dend_total,p,alpha=vals
        if (rhod != f32((0.5,1.0,1.5)[ir-1])
                or qv != f32((0.0,0.001,0.01,0.02,0.03)[iq-1])
                or temp != f32((250.0,300.0)[it-1])):
            raise ValueError(f"manufactured input echoes changed at case {case}")
        if alpha != f32(1.0/rhod):
            raise ValueError(f"manufactured alpha changed at case {case}")
        pressure_expected=rhod*temp*(rd+rv*qv)
        if abs(p-pressure_expected)>TOL_FACTOR*EPS32*max(1.,abs(pressure_expected)):
            raise ValueError(f"manufactured pressure disagrees with ideal-mixture input at case {case}")
        dry_expected=rhod*(1.0+qv*rv/(rd-rv)); total_expected=rhod
        td=TOL_FACTOR*EPS32*max(1.0,abs(dry_expected),rhod)
        tm=TOL_FACTOR*EPS32*max(1.0,abs(total_expected),rhod)
        tr=TOL_FACTOR*EPS32*max(1.0,rhod)
        rows.append({"case":case,"rho_index":ir,"qv_index":iq,"temperature_index":it,"rho_dry_input":rhod,"qv":qv,"temperature_K":temp,"host_rho_from_alpha":rho_active,"rho_host_abs_error":abs(rho_active-rhod),"p_synth":p,"alpha_synth":alpha,"udm_dend_when_DEN_is_rho_dry":dend_dry,"analytic_dry_DEN_expected":dry_expected,"dry_DEN_abs_error":abs(dend_dry-dry_expected),"dry_DEN_tolerance":td,"udm_dend_when_DEN_is_rho_total":dend_total,"analytic_total_DEN_expected":total_expected,"total_DEN_abs_error":abs(dend_total-total_expected),"total_DEN_tolerance":tm,"dry_DEN_pass":abs(dend_dry-dry_expected)<=td,"total_DEN_pass":abs(dend_total-total_expected)<=tm,"host_rho_pass":abs(rho_active-rhod)<=tr})
    if seen!=expected: raise ValueError("case roster/order/indices do not match unique expected 30-case Cartesian product")
    return rows


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source-root',required=True,type=Path)
    ap.add_argument('--output-dir',required=True,type=Path)
    ap.add_argument('--fc',default='gfortran')
    a=ap.parse_args(); src=a.source_root.resolve(); out=a.output_dir.resolve()
    if out.exists(): raise SystemExit(f"refusing existing output directory: {out}")
    if not src.is_dir(): raise SystemExit("source root missing")
    git=subprocess.run(['git','rev-parse','HEAD'],cwd=src,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if git.returncode: raise SystemExit(f"cannot record source HEAD: {git.stdout.strip()!r}")
    contract=extract_contract(src)
    template=Path(__file__).with_name('density_fixture_template.f90.in')
    template_bytes=template.read_bytes()
    generated=template_bytes.decode().replace('@RD_VALUE@',format(contract['rd'],'.17g')).replace('@RV_VALUE@',format(contract['rv'],'.17g')).replace('@HOST_RHO_STATEMENT@',contract['host_line']).replace('@UDM_DEND_STATEMENT@',contract['dend_line'])
    if '@' in generated: raise SystemExit("unexpanded template placeholder")
    out.mkdir(parents=True)
    (out/'density_fixture.f90').write_text(generated)
    (out/'source-statements.txt').write_text('\n'.join([f"{contract['files']['prep']}: extracted unique line",contract['host_line'],f"{contract['files']['udm']}: extracted unique line",contract['dend_line'],f"{contract['files']['constants']}: extracted constants",contract['rd_line'],contract['rv_line'],f"{contract['files']['driver']}: import contract",contract['driver_use']])+'\n')
    comp=subprocess.run([a.fc,'--version'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if comp.returncode: raise SystemExit(f"compiler version probe failed rc={comp.returncode}")
    source=(subprocess.run(['git','rev-parse','HEAD'],cwd=src,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout.strip())
    manifest={"schema":"udm-density-contract-fixture-v2","status":"PREPARED_NOT_RUN","source_root":str(src),"source_head":source,"source_files":{k:{"path":PINNED_FILES[k][0],"sha256":contract['hashes'][k]} for k in PINNED_FILES},"extracted":{"host_rho":{"file":PINNED_FILES['prep'][0],"line":5542,"statement":contract['host_line'],"statement_sha256":contract['host_statement_sha256']},"udm_dend":{"file":PINNED_FILES['udm'][0],"line":856,"statement":contract['dend_line'],"statement_sha256":contract['dend_statement_sha256']},"rd":{"file":PINNED_FILES['constants'][0],"statement":contract['rd_line'],"value":contract['rd']},"rv":{"file":PINNED_FILES['constants'][0],"statement":contract['rv_line'],"value":contract['rv']},"driver_import":{"file":PINNED_FILES['driver'][0],"statement":contract['driver_use']}},"runner":{"path":Path(__file__).name,"sha256":sha_file(__file__)},"template":{"path":template.name,"sha256":sha_file(template)},"generated_source":{"path":"density_fixture.f90","sha256":sha_file(out/'density_fixture.f90')},"source_statements":{"path":"source-statements.txt","sha256":sha_file(out/'source-statements.txt')},"compiler":{"command":a.fc,"version_probe_rc":comp.returncode,"version":comp.stdout.strip()},"cases":{"rho_d_kg_m3":[0.5,1.0,1.5],"qv_kg_kg_dry":[0.0,0.001,0.01,0.02,0.03],"temperature_K":[250.0,300.0],"unique_order":"case_id, rho_index, qv_index, temperature_index in nested Cartesian-product order"},"analytic_oracle":{"dry_DEN":"rho_d*(1+qv*Rv/(Rd-Rv))","total_moist_DEN":"rho_d","dry_limit":"both equal rho_d at qv=0"},"tolerance":{"formula":"16*epsilon(REAL32)*max(1,abs(expected),rho_d)","epsilon_real32":EPS32,"factor":TOL_FACTOR,"fixed_before_execution":True},"execution":[]}
    manifest['source_equivalent_head']=PINNED_HEAD
    receipt=out/'manifest.json'; atomic_json(receipt,manifest)
    env=os.environ.copy(); env['OMP_NUM_THREADS']='1'; exe=out/'density_fixture.exe'
    for opt in ('-O0','-O2'):
        tag=opt[2:]
        ccargv=[a.fc,'-std=f2008',opt,'-ffp-contract=off',str(out/'density_fixture.f90'),'-o',str(exe)]
        rc,_,c=durable_run(ccargv,out,out/f'compile-{tag}.log',env,receipt,'last_compile',manifest)
        c['optimization']=opt
        manifest['execution'].append({'optimization':opt,'compile':c}); atomic_json(receipt,manifest)
        if rc: manifest['status']='COMPILE_FAILED'; atomic_json(receipt,manifest); raise SystemExit(f"compile failed {opt}")
        c.update({'executable_sha256':sha_file(exe),'executable_bytes':exe.stat().st_size})
        atomic_json(receipt,manifest)
        rc,text,r=durable_run([str(exe)],out,out/f'run-{tag}.log',env,receipt,'last_run',manifest)
        runobj={'returncode':r['returncode'],'argv':r['argv'],'cwd':r['cwd'],'started_epoch':r['started_epoch'],'ended_epoch':r['ended_epoch'],'log':r['log'],'log_sha256':r['log_sha256'],'stdout_sha256':r['stdout_sha256']}
        entry=manifest['execution'][-1]; entry['run']=runobj; atomic_json(receipt,manifest)
        if rc: manifest['status']='RUN_FAILED'; atomic_json(receipt,manifest); raise SystemExit(f"run failed {opt}")
        try:
            rows=parse_output(text,contract['rd'],contract['rv'])
        except Exception as error:
            manifest['status']='OUTPUT_GATE_FAILED'
            manifest['output_gate_error']=repr(error)
            atomic_json(receipt,manifest)
            raise
        checks=all(x['dry_DEN_pass'] and x['total_DEN_pass'] and x['host_rho_pass'] for x in rows)
        entry.update({'case_results':rows,'counts':{'cases':len(rows),'host_rho_pass':sum(x['host_rho_pass'] for x in rows),'dry_DEN_pass':sum(x['dry_DEN_pass'] for x in rows),'total_DEN_pass':sum(x['total_DEN_pass'] for x in rows),'qv_zero_dry_limit_pass':all(x['dry_DEN_pass'] and x['total_DEN_pass'] for x in rows if x['qv']==0.0)},'result':'PASS_SYNTHETIC_CONTRACT' if checks else 'FAIL_PRESERVED'})
        manifest.pop('last_compile',None); manifest.pop('last_run',None)
        manifest['status']=entry['result']; atomic_json(receipt,manifest)
        atomic_json(out/f'result-{tag}.json',entry)
        if not checks: raise SystemExit(f"oracle failed {opt}; preserved")
    manifest['status']='PASS_SYNTHETIC_CONTRACT_BOTH_O0_O2'; atomic_json(receipt,manifest)
    print(json.dumps({'status':manifest['status'],'output_dir':str(out),'source_head':source,'generated_source_sha256':manifest['generated_source']['sha256'],'case_count_each':30},indent=2))

if __name__=='__main__': main()
