#!/usr/bin/env python3
"""Authenticate the existing compile; no build/model or original receipt rewrite."""
import argparse,hashlib,importlib.util,json,os,re,shlex,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
COMMON=HERE.parent/'udm-seaice-winter-validation-v1/winter_validation_v1.py'
COMMON_SHA='6f66046e785fc5ef69f317daa3ca63a09a4cfab0839a67bea9703ce21691a4e8'
ORIGINAL=HERE/'build-result-v1.json'
ORIGINAL_SHA='35d2297a2d7d553d1f4fe8a2cfc66f02d6811604454a947adc8af90eb778ada1'
if hashlib.sha256(COMMON.read_bytes()).hexdigest()!=COMMON_SHA:raise ValueError('frozen common changed before import')
s=importlib.util.spec_from_file_location('original_seaice_helper',COMMON);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
if m.digest(COMMON)!=COMMON_SHA:raise ValueError('frozen common changed after import')


def require(condition,message):
    if not condition:raise ValueError(message)


def guard_contexts(source,pattern,macros):
    targets={source.count('\n',0,mt.start())+1 for mt in re.finditer(pattern,source,re.I|re.M)}
    stack=[];out=[]
    for number,line in enumerate(source.splitlines(),1):
        directive=re.match(r'^\s*#\s*(ifdef|ifndef|if|elif|else|endif)\b\s*(.*)',line)
        if directive:
            kind,arg=directive.groups()
            if kind in ('ifdef','ifndef','if'):stack.append({'kind':kind,'argument':arg.strip(),'line':number,'alternate':False})
            elif kind=='endif':
                require(bool(stack),'unbalanced CPP endif');stack.pop()
            elif kind=='else':
                require(bool(stack),'unbalanced CPP else');stack[-1]={**stack[-1],'alternate':not stack[-1]['alternate']}
            else:
                require(bool(stack),'unbalanced CPP elif');stack[-1]={'kind':'if','argument':arg.strip(),'line':number,'alternate':False}
        if number in targets:
            conditions=[]
            for entry in stack:
                require(entry['kind'] in ('ifdef','ifndef'),'unsupported actual guard CPP condition requires review')
                require(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',entry['argument']) is not None,'invalid CPP macro')
                active=entry['argument'] in macros
                if entry['kind']=='ifndef':active=not active
                if entry['alternate']:active=not active
                conditions.append({**entry,'active':active})
            out.append({'source_guard_line':number,'source_qz0_line':number+1,'cpp_conditions':conditions,'active':all(x['active'] for x in conditions)})
    require(not stack,'unclosed source CPP conditional')
    return out


def verify_build():
    original_pin=m.require_hash(ORIGINAL,ORIGINAL_SHA);b=json.loads(ORIGINAL.read_text())
    require(b['status']=='BUILD_FAIL_PRESERVED','original FAIL must be retained')
    require(b['compile_invocations']==1 and b['model_invocations']==0,'unexpected original invocation counts')
    require(b['source_unchanged'] and b['dependencies_unchanged'],'original source/deps failed')
    process=b['process'];require(process['returncode']==0 and not process['timed_out'],'compile process failed')
    require(process['command']==['csh','-f','./compile','-j','12','em_real'],'wrong actual compile command')
    m.check_pin(process['log']);text=Path(process['log']['path']).read_text()
    log=m.classify_build_log(text,process['returncode'])
    require(log['successful_footer'] and not log['errors'] and b['footer_success'] and not b['compiler_link_make_errors'],'footer/compiler/link check failed')
    spec,_=m.load_freeze(Path(b['freeze_spec']['path']),b['freeze_spec']['sha256'])
    source=m.verify_manifest(b['source_manifest'],b['production7']);wrf=Path(source['source_path'])/'WRF'
    require(process['cwd']==str(wrf),'compile cwd differs from manifested tree')
    for pin in (b['runner'],b['preparer'],b['shared_dependencies']):m.check_pin(pin)
    m.verify_dependency_inventory(json.loads(Path(b['shared_dependencies']['path']).read_text()))
    require(b['production7']==spec['production7'],'production pins differ from root freeze')
    require(set(b['executables'])=={'wrf.exe','real.exe','ndown.exe','tc.exe'},'missing build executable')
    for name,entry in b['executables'].items():
        require(entry['nonempty_executable_ELF'],'original nonempty ELF check failed');m.check_pin(entry['file'])
        p=Path(entry['file']['path']);require(p.stat().st_size>0 and os.access(p,os.X_OK),'nonempty executable lost')
        with p.open('rb') as stream:require(stream.read(4)==b'\x7fELF','not actual executable ELF')
    require(set(b['generated_production7'])==set(spec['production7']),'missing generated production artifact')
    for rel,entry in b['generated_production7'].items():
        require(set(entry)=={'.f90','.o'},'missing generated source or object')
        for suffix,artifact in entry.items():
            require(artifact['nonempty'],'original generated artifact failed');m.check_pin(artifact['file']);m.nonempty_artifact(Path(artifact['file']['path']))
    m.check_pin(b['binary']);require(b['binary']==b['executables']['wrf.exe']['file'],'main executable identity differs')
    for binary,expected in ((Path(b['binary']['path']),b['binary_libraries']),(m.MPIEXEC,b['mpiexec_libraries'])):
        require(m.library_pins(binary,b['ld_library_path'])==expected,'normalized libraries changed')
    require(m.pin(m.MPIEXEC)==b['mpiexec'],'MPI launcher changed')
    nm=subprocess.run(['nm',b['binary']['path']],env={**b['environment'],'LC_ALL':'C'},text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    require(nm.returncode==0,'nm failed')
    symbols={x:x in nm.stdout for x in b['required_link_symbols']}
    require(all(symbols.values()) and all(b['required_link_symbols'].values()),'required linked symbols absent')
    source_text=(wrf/'phys/module_surface_driver.F').read_text();generated=(wrf/'phys/module_surface_driver.f90').read_text()
    patterns=spec['compiled_surface_patterns'];require(len(patterns)==3,'unexpected frozen pattern set')
    require(b['compiled_surface_patterns']==[{'pattern':x['pattern'],'expected_count':x['count'],'observed_count':len(re.findall(x['pattern'],generated,re.I|re.M)),'passed':len(re.findall(x['pattern'],generated,re.I|re.M))==x['count']} for x in patterns],'original recorded pattern results differ')
    require(all(x['passed'] for x in b['compiled_surface_patterns'][:2]) and not b['compiled_surface_patterns'][2]['passed'],'original failure not solely final QZ0 count')
    commands=[(n,line) for n,line in enumerate(text.splitlines(),1) if line.startswith('/lib/cpp ') and 'module_surface_driver.G' in line and 'module_surface_driver.bb' in line]
    require(len(commands)==1,'recorded surface CPP command missing/ambiguous')
    line_number,command=commands[0];argv=shlex.split(command);macros={}
    for token in argv:
        if token.startswith('-D'):
            name,_,value=token[2:].partition('=');macros[name]=value or '1'
        elif token.startswith('-U'):macros.pop(token[2:],None)
    config=(wrf/'configure.wrf').read_text();active_config='\n'.join(line.split('#',1)[0] for line in config.splitlines())
    require('WRF_USE_CLM' in macros and 'WRF_USE_CTSM' not in macros,'different actual CPP flags')
    require('-DWRF_USE_CLM' in active_config and '-DWRF_USE_CTSM' not in active_config,'config/build CPP flags disagree')
    qz0=patterns[2];contexts=guard_contexts(source_text,qz0['pattern'],macros)
    require(len(contexts)==qz0['count']==4,'all four raw-source QZ0 guards required')
    expected=sum(x['active'] for x in contexts);observed=len(re.findall(qz0['pattern'],generated,re.I|re.M))
    require(expected==observed,'CPP-derived active QZ0 count differs from generated source')
    require([[(y['kind'],y['argument']) for y in x['cpp_conditions']] for x in contexts]==[[],[],[('ifdef','WRF_USE_CLM')],[('ifdef','WRF_USE_CTSM')]],'unexpected guard CPP structure')
    generated_lines=[generated.count('\n',0,mt.start())+2 for mt in re.finditer(qz0['pattern'],generated,re.I|re.M)]
    ustm=[{'label':x['label'],'source_count':len(re.findall(x['pattern'],source_text,re.I|re.M)),'generated_count':len(re.findall(x['pattern'],generated,re.I|re.M)),'expected_count':x['count']} for x in patterns[:2]]
    require(all(x['source_count']==x['generated_count']==x['expected_count'] for x in ustm),'USTM snapshot/restore missing')
    m.require_hash(ORIGINAL,ORIGINAL_SHA);m.verify_manifest(b['source_manifest'],b['production7']);m.load_freeze(Path(b['freeze_spec']['path']),b['freeze_spec']['sha256']);m.verify_dependency_inventory(json.loads(Path(b['shared_dependencies']['path']).read_text()))
    return {'status':'BUILD_PASS_POSTHOC_ATTESTED','original_receipt':original_pin,'original_status':b['status'],'original_checks_except_erroneous_count_passed':True,'source_verified':source,'freeze_spec':b['freeze_spec'],'live_artifact_and_dependency_pins_valid':True,'linked_symbols':symbols,'log_recomputed':log,'surface_CPP_proof':{'recorded_command_log_line':line_number,'recorded_command':command,'macros':macros,'raw_QZ0_guard_count':len(contexts),'source_guard_contexts':contexts,'derived_active_QZ0_guard_count':expected,'generated_QZ0_guard_count':observed,'generated_QZ0_lines':generated_lines,'USTM_counts':ustm},'erratum':{'original_assertion':'four raw-source QZ0 guards must remain four after CPP','corrected_assertion':'generated QZ0 guard count equals active raw-source guards under the actual recorded CPP flags','reason':'WRF_USE_CTSM source branch is disabled; WRF_USE_CLM is enabled. The frozen generated expectation4 was a harness error; source/objects/executables unchanged.'},'new_compile_invocations':0,'new_model_invocations':0,'source_or_original_receipt_mutations':0}


def verify_attestation(expected):
    m.check_pin(expected);receipt=json.loads(Path(expected['path']).read_text())
    require(receipt['status']=='BUILD_PASS_POSTHOC_ATTESTED','missing successful explicit posthoc attestation')
    require(receipt['verifier']==m.pin(Path(__file__)),'posthoc verifier changed')
    actual=verify_build();require(actual==receipt['validation'],'posthoc attestation differs from fresh live validation')
    return actual


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--attest',action='store_true');args=p.parse_args();receipt=HERE/'posthoc-build-attestation-v1.json'
    if args.attest:m.collision(receipt)
    result={'schema':'udm-seaice-posthoc-build-attestation-v1','utc':m.utc_now(),'verifier':m.pin(Path(__file__))}
    try:result['validation']=verify_build();result['status']=result['validation']['status']
    except Exception as exc:result['status']='POSTHOC_VALIDATION_FAIL_PRESERVED';result['error']=f'{type(exc).__name__}: {exc}'
    if args.attest:
        with receipt.open('x') as f:f.write(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'new_compile_invocations':0,'new_model_invocations':0,'receipt_written':args.attest}));return 0 if result['status']=='BUILD_PASS_POSTHOC_ATTESTED' else 1
if __name__=='__main__':raise SystemExit(main())
