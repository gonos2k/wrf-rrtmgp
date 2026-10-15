"""Replay sealed actual CF0 UDM/WRF/RTE evidence; no new model execution."""
import gzip, hashlib, importlib.util, json, math, re
from pathlib import Path
B=Path(__file__).resolve().parent; ROOT=B.parents[2]
def sha(data): return hashlib.sha256(data).hexdigest()
def require(ok,message):
    if not ok: raise ValueError(message)
def read(name): return gzip.decompress((B/'saved'/(name+'.gz')).read_bytes())
def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def packet(case):
    index=json.loads((B/f'saved/host/{case}.terminal.json').read_text());data=read(f'host/{case}.terminal.bin')
    require(index['population_policy']==2 and sha(data)==index['payload_sha256'],'terminal policy/payload differs')
    out={};offset=0
    for row in index['records']:
        require(row['variable'] not in out and row['offset']==offset,'terminal roster')
        part=data[offset:offset+row['bytes']];require(len(part)==row['bytes'] and sha(part)==row['sha256'],'terminal bytes')
        out[row['variable']]=part;offset+=row['bytes']
    require(offset==len(data),'terminal extent');return out

def verify():
    manifest=json.loads((B/'manifest.json').read_text());require(manifest['production_accepted'] is False,'false physical approval')
    roster={str(p.relative_to(B)) for p in B.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
    require(roster==set(manifest['files']),'sealed roster differs')
    for name,row in manifest['files'].items():
        p=B/name;require(not p.is_symlink() and sha(p.read_bytes())==row['sha256'] and len(p.read_bytes())==row['bytes'],'sealed file differs '+name)
    identity=json.loads((B/'identity.json').read_text());require(identity['population_policy']==2 and identity['number_policy']==1 and identity['production_accepted'] is False and identity['physical_gate_closed'] is False,'policy/approval differs')
    for n,digest in identity['source_files'].items():require(sha((ROOT/n).read_bytes())==digest,'current candidate source differs '+n)
    for n,digest in identity['coefficient_files'].items():require(sha((ROOT/n).read_bytes())==digest,'fixed coefficient differs '+n)
    require(read('columns/src/module_ra_rrtmgp.F')==(ROOT/'WRF/phys/module_ra_rrtmgp.F').read_bytes(),'standalone compiled adapter differs')
    test=load(ROOT/'WRF/test/rrtmgp/test_udm_cf0_transition.py','cf0_actual');module=json.loads((B/'saved/module/receipt.json').read_text())
    raw=read('module/production.F');require(sha(raw)==module['source_sha256']==identity['source_files']['WRF/phys/module_mp_udm.F'],'actual compiled source differs')
    require(test.observer(raw)==read('module/observed.F') and test.fixture(ROOT/'WRF')==read('module/fixture.f90'),'actual observer/input differs')
    require(sha(read('module/runner.py'))==module['script_sha256'],'executed module runner differs')
    for opt in ('O0','O2'):
        datasets={}
        for n,p in enumerate(module['processes'],1):
            require(p['status']=='TERMINAL' and p['actual_returncode']==0 and not p['timed_out'],'unreaped/failed actual module process')
            if p['kind'].startswith('UDM_') and '/'+opt+'/' in p['argv'][0]:datasets[p['kind']]=test.parse(read(f'module/command-{n:02d}.stdout').decode())
        require(datasets['UDM_production_off'][1]==datasets['UDM_observed_off'][1],'observer OFF changes output')
        require(test.analyze(datasets['UDM_observed_on'],datasets['UDM_observed_off'])==module['results'][opt],'actual raw local water/latent budget differs')
    require(module['actual_UDM_calls']==36 and module['results']['O0']==module['results']['O2'],'call/optimization count')
    host=json.loads((B/'saved/host/receipt.json').read_text());require(host['executable']==identity['WRF_executable'] and host['continuous_seconds']==60 and host['restart_seconds']==30,'actual host binding')
    require(sha(read('original/wrfinput_d01'))==host['original_input']['sha256'],'original failed physical input differs')
    for n,p in enumerate(host['processes'],1):
        require(p['status']=='TERMINAL' and not p['timed_out'],'host process incomplete')
        text=read(f'host/command-{n:02d}.stdout').decode()
        if 'strict' in p['kind']:
            require('UDM_CF0_REJECT step/sub/i/call_lat/k=5 1 1 1 13' in text and 'CF0 condensate unsupported' in text and 'SUCCESS COMPLETE WRF' not in text,'original failure not reproduced')
            record=next(x for x in text.splitlines() if 'UDM_CF0_REJECT' in x)
            values=list(map(float,record.split('qc/qr/nc/nr/T/qv/rho/cf=')[1].split()))
            require(0.<values[0]<1.e-6 and values[1]>.009 and values[-1]==0.,'first refusal classification differs')
        else:require(p['actual_returncode']==0 and 'SUCCESS COMPLETE WRF' in text and 'FATAL CALLED' not in text,'actual continued host failed')
    require(packet('control')==packet('restart') and len(packet('control'))==211,'restart crossing CF0 differs')
    columns=load(B/'analyze_columns.py','cf0_columns');result=columns.analyze(read)
    require(result==json.loads((B/'result.json').read_text()),'actual later optics replay differs')
    execution=json.loads((B/'saved/columns/execution.json').read_text());require(execution['executable']==identity['column_executable'] and len(execution['processes'])==8,'public-column executable/process count')
    require(all(p['status']=='TERMINAL' and p['actual_returncode']==0 and not p['timed_out'] for p in execution['processes']),'failed/unreaped public-column process')
    moments=json.loads((B/'saved/columns/moments.json').read_text());require(moments['shape_is_declared_research_assumption'] and not moments['fixed_LUT_generation_PSD_certified'] and not moments['production_radius_changed'],'false final PSD approval')
    shape=moments['number_gamma_shape_k'];require(shape==8. and moments['effective_variance']==1./(shape+2),'explicit Gamma definition')
    for case in moments['cases']:
        require(case['source_time_seconds']==50.,'PSD source time differs')
        parser=columns.load_parser();_,raw_input=parser.trace(read('capture/'+case['phase'].lower()+'.raw'),'raw')
        for row in case['records']:
            level=row['native_level']-1
            require(row['qc_grid_kg_kg']==raw_input['SOURCE_QC']['values'][level] and row['eta_grid_kg_dry_inverse']==raw_input['SOURCE_QNC']['values'][level] and row['rho_d_kg_m3']==raw_input['SOURCE_DRY_RHO']['values'][level],'final moments not tied to actual consumed state')
            if row['status']!='APPLICABLE_EXPLICIT_GAMMA':continue
            M0=row['M0_grid_m_minus3'];M3=row['M3_grid'];lam=(M0*shape*(shape+1)*(shape+2)/M3)**(1./3);M2=M0*shape*(shape+1)/lam**2
            require(math.isclose(M0,row['rho_d_kg_m3']*row['eta_grid_kg_dry_inverse'],rel_tol=1.e-14) and math.isclose(M3,3*row['rho_d_kg_m3']*row['qc_grid_kg_kg']/(4*math.pi*1000.),rel_tol=1.e-14),'final M0/M3 definition differs')
            require(math.isclose(M2,row['M2_grid_m_minus1'],rel_tol=1.e-14) and math.isclose(M2,row['M2_independent_quadrature'],rel_tol=5.e-12),'Gamma/quadrature M2 differs')
            require(math.isclose(M3,row['M3_independent_quadrature'],rel_tol=5.e-12) and math.isclose(M3/M2*1.e6,row['reff_um'],rel_tol=1.e-14),'Gamma effective radius differs')
    liquid=json.loads((B/'saved/liquid/result.json').read_text())
    require(liquid['manufactured_optical_probe_not_actual_added_liquid'] is True and liquid['production_accepted'] is False,'manufactured optical probe relabelled')
    require(len(liquid['processes'])==2 and all(p['actual_returncode']==0 and not p['timed_out'] for p in liquid['processes']),'liquid optical probe incomplete')
    for case in liquid['checks']:
        for row in case['checks']:
            require(math.isclose(row['observed_tau_increment'],row['coefficient_formula_tau_increment'],rel_tol=8.e-6,abs_tol=2.e-8),'once-scaled liquid coefficient mismatch')
    require(json.loads((B/'closure-conditions.json').read_text())==json.loads((ROOT/'validation/rrtmgp37/dry-number-grid-v1/closure-conditions.json').read_text()),'seven closure conditions changed')
    return {'status':'PASS_SCOPED_CF0_RESEARCH_TRANSITION','actual_UDM_calls':36,'actual_WRF_processes':4,'original_failure_seconds':40,'continued_seconds':60,'terminal_arrays_bitwise_equal':211,'actual_later_radiation_seconds':50,'standalone_RTE_columns':8,'manufactured_CF0_liquid_columns':2,'fresh_model_runs_in_replay':0,'physical_gate_closed':False,'production_accepted':False}
if __name__=='__main__':print(json.dumps(verify()))
