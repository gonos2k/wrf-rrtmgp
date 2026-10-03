#!/usr/bin/env python3
"""Temporary-file posthoc/adaptor controls; no source/build/model mutation."""
import builtins,symtable,copy,hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
HERE=Path(__file__).resolve().parent


def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(s);s.loader.exec_module(module);return module


m=load('runtime_adapter_under_test',HERE/'posthoc_runtime_helper_v1.py');v=m._posthoc
prepare=load('case_preparer_under_test',HERE/'prepare_cases_v1.py')
run=load('case_runner_under_test',HERE/'run_case_v1.py')
rprep=load('restart_preparer_under_test',HERE/'prepare_restart_v1.py')
rrun=load('restart_runner_under_test',HERE/'run_restart_v1.py')


class PosthocControls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def write(self,name,data):
        p=self.root/name;p.write_text(json.dumps(data,sort_keys=True,indent=2)+'\n');return p
    def test_wrong_original_failure_hash_rejected(self):
        bad=m.pin(v.ORIGINAL);bad['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'exact preserved original FAIL'):m.build_integrity(bad)
    def test_missing_attestation_rejected(self):
        missing={'path':str(self.root/'missing.json'),'size_bytes':0,'sha256':'0'*64}
        with patch.object(m,'_ATTESTATION',missing),self.assertRaises(FileNotFoundError):m.build_integrity(m.pin(v.ORIGINAL))
    def test_changed_attestation_bytes_rejected(self):
        p=self.root/'receipt.json';p.write_bytes(Path(m._ATTESTATION['path']).read_bytes());expected=m.pin(p);p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'file changed'):v.verify_attestation(expected)
    def test_wrong_attestation_status_rejected(self):
        d=json.loads(Path(m._ATTESTATION['path']).read_text());d['status']='BUILD_PASS';p=self.write('bad-status.json',d)
        with self.assertRaisesRegex(ValueError,'explicit posthoc'):v.verify_attestation(m.pin(p))
    def test_wrong_attestation_verifier_pin_rejected(self):
        d=json.loads(Path(m._ATTESTATION['path']).read_text());d['verifier']['sha256']='0'*64;p=self.write('bad-verifier.json',d)
        with self.assertRaisesRegex(ValueError,'verifier changed'):v.verify_attestation(m.pin(p))
    def test_wrong_attestation_original_fail_context_rejected(self):
        d=json.loads(Path(m._ATTESTATION['path']).read_text());d['validation']['original_receipt']['sha256']='0'*64;p=self.write('bad-original.json',d)
        with patch.object(v,'verify_build',return_value=json.loads(Path(m._ATTESTATION['path']).read_text())['validation']),self.assertRaisesRegex(ValueError,'fresh live validation'):v.verify_attestation(m.pin(p))
    def synthetic_original(self,edit):
        d=json.loads(v.ORIGINAL.read_text());edit(d);p=self.write('synthetic-original.json',d)
        return p,m.digest(p)
    def test_source_tamper_rejected_by_live_verifier(self):
        src=self.root/'source';src.mkdir();f=src/'native-source.F';f.write_text('original\n');expected=m.pin(f)
        manifest={'base_commit':m.BASE,'source_path':str(src),'entry_count':1,'symlink_count':0,'files':[{'path':f.name,'type':'file','size':expected['size_bytes'],'sha256':expected['sha256']}]}
        mp=self.write('synthetic-manifest.json',manifest);f.write_text('modified\n')
        op,sha=self.synthetic_original(lambda d:d.update(source_manifest=m.pin(mp)))
        with patch.object(v,'ORIGINAL',op),patch.object(v,'ORIGINAL_SHA',sha),self.assertRaisesRegex(ValueError,'source manifest mismatch'):v.verify_build()
    def test_artifact_tamper_rejected_by_live_verifier(self):
        f=self.root/'synthetic-wrf.exe';f.write_bytes(b'\x7fELFsynthetic only');f.chmod(0o700);expected=m.pin(f);f.write_bytes(b'\x7fELFmodified only')
        def edit(d):d['executables']['wrf.exe']['file']=expected
        op,sha=self.synthetic_original(edit)
        with patch.object(v,'ORIGINAL',op),patch.object(v,'ORIGINAL_SHA',sha),self.assertRaisesRegex(ValueError,'file changed'):v.verify_build()
    def test_cpp_source_active_count_controls(self):
        pat=r'IF\s*\(\s*myj\s*\)\s*THEN\s*\n\s*qz0\s*\(\s*i\s*,\s*j\s*\)\s*='
        g='IF (myj) THEN\n qz0(i,j) = qz0_sea(i,j)\nENDIF\n';s=g+g+'#ifdef WRF_USE_CLM\n'+g+'#endif\n#ifdef WRF_USE_CTSM\n'+g+'#endif\n'
        for macros,expected in (({},2),({'WRF_USE_CLM':'1'},3),({'WRF_USE_CLM':'1','WRF_USE_CTSM':'1'},4)):
            self.assertEqual(sum(x['active'] for x in v.guard_contexts(s,pat,macros)),expected)
        with self.assertRaisesRegex(ValueError,'requires review'):v.guard_contexts('#if unknown_expression\n'+g+'#endif\n',pat,{})
    def test_four_entrypoint_bodies_only_binding_substitutions(self):
        data=json.loads((HERE/'runtime-manifest-v1.json').read_text())
        for entry in data['entrypoint_bindings']:
            old=Path(entry['original']['path']).read_text();new=Path(entry['new']['path']).read_text();change=entry['exact_binding_substitution']
            self.assertEqual(old.count(change['old']),1);self.assertEqual(old.replace(change['old'],change['new']),new)
            self.assertEqual(m.pin(Path(entry['original']['path'])),entry['original']);self.assertEqual(m.pin(Path(entry['new']['path'])),entry['new'])
    def test_adapter_exports_original_objects_except_build_integrity(self):
        for name,value in vars(m._original).items():
            if not name.startswith('_') and name!='build_integrity':self.assertIs(getattr(m,name),value)
        self.assertIsNot(m.build_integrity,m._original.build_integrity)
    def test_original_function_global_bindings_complete(self):
        known=set(vars(m._original))|set(vars(builtins));missing=[]
        def walk(table):
            for item in table.get_symbols():
                if item.is_global() and item.is_referenced() and item.get_name() not in known:missing.append((table.get_name(),item.get_name()))
            for child in table.get_children():walk(child)
        table=symtable.symtable(m._COMMON.read_text(),str(m._COMMON),'exec')
        for child in table.get_children():
            if child.get_type()=='function':walk(child)
        self.assertEqual(missing,[])
    def test_unmocked_historical_input_contract_and_missing_binding_control(self):
        self.assertEqual(m.INPUTS,('wrfinput_d01','wrfbdy_d01','radiation_iofields.txt'))
        for arm in ('ra37','ra4'):
            result=m.historical_arm(arm)
            self.assertEqual(set(result['inputs']),set(m.INPUTS));self.assertEqual(len(result['runtime_links']),92)
            for name,entry in result['inputs'].items():self.assertEqual(entry['sha256'],m.EXPECTED[name])
            self.assertEqual(result['namelist']['sha256'],m.EXPECTED[arm+'_namelist'])
        # Demonstrate the actual unmocked helper fails if extraction omits the tuple.
        saved=m._original.INPUTS
        try:
            del m._original.INPUTS
            with self.assertRaisesRegex(NameError,'INPUTS'):m.historical_arm('ra37')
        finally:m._original.INPUTS=saved
    def test_case_prepare_default_cannot_stage_or_launch(self):
        root=self.root/'case-stage';hist=self.root/'history.nc';hist.write_bytes(b'synthetic pin only');spec=self.write('spec.json',{'history_references':{'ra4':m.pin(hist)}})
        runtime=self.root/'runtime-link-manifest.json';runtime.write_text('{}');build=self.write('build.json',{})
        args=SimpleNamespace(stage_root=root,build_receipt=build,build_sha=m.digest(build),arm='ra4',prepare_go=False)
        with patch.object(prepare.m,'build_integrity',return_value={'freeze_spec':{'path':str(spec)}}),patch.object(prepare.m,'historical_arm',return_value={}),patch.object(prepare.m,'HIST',self.root),patch.object(prepare.m,'run_one',side_effect=AssertionError('model invoked')) as launcher:
            result=prepare.prepare(args)
        self.assertEqual(result['status'],'READY_CASE_INPUTS_NOT_STAGED');self.assertFalse(root.exists());launcher.assert_not_called()
    def test_case_run_default_cannot_launch_or_write_receipt(self):
        case=self.root/'case';case.mkdir();args=SimpleNamespace(stage_receipt=self.root/'stage.json',stage_sha='0'*64,execute=False);r={'case':{'case_path':str(case)},'build_receipt':{}}
        with patch.object(run,'invariants',return_value=(r,{},{})),patch.object(run.m,'build_integrity',return_value={'production7':{}}),patch.object(run.m,'run_one',side_effect=AssertionError('model invoked')) as launcher:result=run.run(args)
        self.assertEqual(result['status'],'READY_MODEL_NOT_RUN');self.assertFalse((self.root/'execution-receipt-v1.json').exists());launcher.assert_not_called()
    def test_restart_prepare_default_cannot_stage_or_launch(self):
        parent=self.write('parent.json',{});root=self.root/'restart-stage';args=SimpleNamespace(parent_run=parent,parent_sha=m.digest(parent),stage_root=root,prepare_go=False)
        reference={'zero_based_time_index':13,'all_raw_variable_slice_pins':{str(i):{} for i in range(225)}}
        with patch.object(rprep,'parent_integrity',return_value=({'arm':'ra37'},{'case':{'expected_variable_count':225}},{},{'file':{'path':str(parent)}})),patch.object(rprep.m,'continuous_slice',return_value=reference),patch.object(rprep.m,'run_one',side_effect=AssertionError('model invoked')) as launcher:result=rprep.prepare(args)
        self.assertEqual(result['status'],'READY_RESTART_INPUTS_NOT_STAGED');self.assertFalse(root.exists());launcher.assert_not_called()
    def test_restart_run_default_cannot_launch_or_write_receipt(self):
        case=self.root/'case';case.mkdir();checkpoint=case/'wrfrst_d01_2000-01-25_00:00:00';checkpoint.write_text('synthetic')
        args=SimpleNamespace(stage_receipt=self.root/'stage.json',stage_sha='0'*64,execute=False);r={'case':{'case_path':str(case),'arm':'ra37','checkpoint':{'path':str(checkpoint)}}}
        with patch.object(rrun,'invariants',return_value=(r,{},{})),patch.object(rrun.m,'run_one',side_effect=AssertionError('model invoked')) as launcher:result=rrun.run(args)
        self.assertEqual(result['status'],'READY_RESTART_NOT_RUN');self.assertFalse((self.root/'restart-execution-v1.json').exists());launcher.assert_not_called()


if __name__=='__main__':
    output=HERE/'offline-posthoc-controls-v1.json'
    if output.exists():raise FileExistsError(output)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PosthocControls))
    receipt={'status':'PASS' if result.wasSuccessful() else 'FAIL_PRESERVED','utc':m.utc_now(),'test_count':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'test_script':m.pin(Path(__file__)),'runtime_manifest':m.pin(HERE/'runtime-manifest-v1.json'),'adapter':m.pin(HERE/'posthoc_runtime_helper_v1.py'),'posthoc_verifier':m.pin(m._VERIFIER),'scope':'Temporary-file synthetic tamper/default/binding controls; real read-only source/dependency pin checks; no production mutation/stage/build/model','compile_invocations':0,'model_invocations':0,'stage_creations':0}
    with output.open('x') as f:f.write(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
