#!/usr/bin/env python3
"""Offline harness controls only; no source checkout/build/WRF/MPI."""
import importlib.util,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
from netCDF4 import Dataset
HERE=Path(__file__).resolve().parent

def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);x=importlib.util.module_from_spec(s);s.loader.exec_module(x);return x
m=load(HERE/'winter_validation_v1.py','test_seaice_common')
sp=load(HERE.parent/'udm-seaice-fresh-gnu-dm-sm-v1/prepare_source_v1.py','test_seaice_source')
case=load(HERE/'run_case_v1.py','test_seaice_case')
restart=load(HERE/'run_restart_v1.py','test_seaice_restart')
G={'west_east':3,'south_north':2,'bottom_top':1}

def fixture(path, stamps=m.TIMES, radiation=4):
    with Dataset(path, 'w', format='NETCDF3_64BIT_OFFSET') as ds:
        ds.createDimension('Time', None)
        ds.createDimension('DateStrLen', 19)
        for name, size in G.items():
            ds.createDimension(name, size)
        ds.setncattr('MP_PHYSICS', np.int32(27))
        ds.setncattr('RA_LW_PHYSICS', np.int32(radiation))
        ds.setncattr('RA_SW_PHYSICS', np.int32(radiation))
        v = ds.createVariable('Times', 'S1', ('Time', 'DateStrLen'))
        v[:] = np.asarray([[bytes([c]) for c in s.encode()] for s in stamps], dtype='S1')
        v = ds.createVariable('T2', 'f4', ('Time', 'south_north', 'west_east'), fill_value=-9999.)
        v[:] = np.zeros((len(stamps), 2, 3), dtype='f4')

class NetCDFControls(unittest.TestCase):

    def test_exact_clock_and_physics(self):
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / 'history.nc'
                fixture(p)
                r = m.validate_dataset(p, m.TIMES, 4, G)
                self.assertTrue(r['passed'])
                json.dumps(r)  # Actual netCDF numpy metadata scalars must serialize.
                for stamps in (m.TIMES[:-1], m.TIMES + ['2000-01-25_13:00:00'], m.TIMES[:2] + [m.TIMES[1]] + m.TIMES[3:], list(reversed(m.TIMES))):
                    fixture(p, stamps)
                    self.assertFalse(m.validate_dataset(p, m.TIMES, 4, G)['passed'])
                fixture(p)
                self.assertFalse(m.validate_dataset(p, m.TIMES, 37, G)['passed'])
                self.assertFalse(m.validate_dataset(p, m.TIMES, 4, {**G, 'bottom_top': 2})['passed'])
                with Dataset(p, 'a') as ds:
                    ds.delncattr('MP_PHYSICS')
                self.assertFalse(m.validate_dataset(p, m.TIMES, 4, G)['passed'])

    def test_default_fill_without_attribute_rejected(self):
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / 'history.nc'
                fixture(p)
                with Dataset(p, 'a') as ds:
                    v = ds.createVariable('UNWRITTEN', 'f4', ('Time', 'south_north', 'west_east'))
                    self.assertNotIn('_FillValue', v.ncattrs())
                r = m.validate_dataset(p, m.TIMES, 4, G)
                self.assertFalse(r['passed'])
                self.assertEqual(r['numeric_variables']['UNWRITTEN']['mask_hits'], 25 * 6)

    def test_explicit_missing_fill_and_raw_nan_rejected(self):
            for kind in ('missing_value', '_FillValue', 'nan'):
                with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                    p = Path(tmp) / 'history.nc'
                    fixture(p)
                    with Dataset(p, 'a') as ds:
                        v = ds.variables['T2']
                        v.set_auto_maskandscale(False)
                        if kind == 'missing_value':
                            v.setncattr('missing_value', np.float32(-8888))
                            v[0, 0, 0] = -8888.
                        elif kind == '_FillValue':
                            v[0, 0, 0] = -9999.
                        else:
                            v[0, 0, 0] = np.nan
                    r = m.validate_dataset(p, m.TIMES, 4, G)
                    self.assertFalse(r['passed'])
                    if kind != 'nan':
                        self.assertEqual(r['numeric_variables']['T2']['explicit_fill_or_missing_hits'][kind], 1)
                    else:
                        self.assertEqual(r['numeric_variables']['T2']['raw_nonfinite'], 1)

    def test_decoded_nonfinite_with_finite_raw_rejected(self):
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / 'history.nc'
                fixture(p)
                with Dataset(p, 'a') as ds:
                    v = ds.variables['T2']
                    v.set_auto_maskandscale(False)
                    v[:] = 2.
                    v.setncattr('scale_factor', np.float64(1e308))
                with np.errstate(over='ignore'):
                    r = m.validate_dataset(p, m.TIMES, 4, G)
                self.assertEqual(r['numeric_variables']['T2']['raw_nonfinite'], 0)
                self.assertGreater(r['numeric_variables']['T2']['decoded_nonfinite'], 0)
                self.assertFalse(r['passed'])

    def test_signed_zero_raw_bytes_and_metadata_rejected(self):
            with tempfile.TemporaryDirectory() as tmp:
                a, b = Path(tmp) / 'a.nc', Path(tmp) / 'b.nc'
                fixture(a)
                import shutil
                shutil.copy2(a, b)
                self.assertTrue(m.compare_datasets(a, b)['passed'])
                with Dataset(b, 'a') as ds:
                    ds.variables['T2'][0, 0, 0] = np.float32(-0.)
                r = m.compare_datasets(a, b)
                self.assertTrue(r['all_metadata_equal'])
                self.assertFalse(r['all_variable_raw_bytes_equal'])
                self.assertFalse(r['whole_file_byte_identity'])
                self.assertFalse(r['passed'])
                shutil.copy2(a, b)
                with Dataset(b, 'a') as ds:
                    ds.setncattr('NEW_ATTR', 'changed metadata')
                r = m.compare_datasets(a, b)
                self.assertFalse(r['all_metadata_equal'])
                self.assertTrue(r['all_variable_raw_bytes_equal'])
                self.assertFalse(r['passed'])

    def test_new_numeric_variable_rejected(self):
            with tempfile.TemporaryDirectory() as tmp:
                a, b = Path(tmp) / 'a.nc', Path(tmp) / 'b.nc'
                fixture(a)
                fixture(b)
                with Dataset(b, 'a') as ds:
                    ds.createVariable('EXTRA', 'i4', ('Time',))[:] = 1
                r = m.compare_datasets(a, b)
                self.assertIn('variable_names', r['raw_mismatches'])
                self.assertFalse(r['passed'])

    def test_controlled_env_clears_audit_and_probes(self):
            with patch.dict(os.environ, {'WRF_RRTMGP_CAPTURE_DIR': '/must/not/use', 'WRF_RRTMGP_AUDIT': '1', 'OMP_NUM_THREADS': '8', 'OMP_DISPLAY_AFFINITY': 'TRUE', 'LD_PRELOAD': '/probe.so', 'LD_AUDIT': '/audit.so'}):
                env, cleared = m.clean_run_env(m.MPIEXEC, m.LD_DEFAULT)
                self.assertFalse(any(k.startswith('WRF_RRTMGP_') for k in env))
                self.assertNotIn('LD_PRELOAD', env)
                self.assertNotIn('LD_AUDIT', env)
                self.assertNotIn('OMP_DISPLAY_AFFINITY', env)
                self.assertEqual(env['OMP_NUM_THREADS'], '1')
                self.assertEqual(env['OMP_DYNAMIC'], 'FALSE')
                self.assertIn('LD_PRELOAD', cleared)

def restart_fixture(path, stamps, start, changed_dtype=False):
    with Dataset(path,'w',format='NETCDF3_64BIT_OFFSET') as ds:
        ds.createDimension('Time',None)
        ds.createDimension('DateStrLen',19)
        ds.createDimension('x',2)
        ds.setncattr('START_DATE',start)
        ds.setncattr('SIMULATION_START_DATE','2000-01-24_12:00:00')
        ds.setncattr('MP_PHYSICS',np.int32(27))
        ds.setncattr('RA_LW_PHYSICS',np.int32(4))
        ds.setncattr('RA_SW_PHYSICS',np.int32(4))
        times=ds.createVariable('Times','S1',('Time','DateStrLen'))
        times[:]=np.asarray([[bytes([c]) for c in s.encode()] for s in stamps],dtype='S1')
        v=ds.createVariable('T2','f8' if changed_dtype else 'f4',('Time','x'))
        v.setncattr('units','K')
        v[:]=np.zeros((len(stamps),2))

class RestartControls(unittest.TestCase):

    def setUp(self):
            self.tmp=tempfile.TemporaryDirectory()
            self.root=Path(self.tmp.name)
            self.old=self.root/'continuous.nc';self.new=self.root/'restart.nc'
            restart_fixture(self.old,['2000-01-25_00:00:00','2000-01-25_01:00:00'],'2000-01-24_12:00:00')
            restart_fixture(self.new,['2000-01-25_01:00:00'],'2000-01-25_00:00:00')
            self.reference=m.continuous_slice(self.old)

    def tearDown(self):self.tmp.cleanup()

    def result(self):return m.compare_to_own_slice(self.new,self.reference)

    def test_exact_split_raw_and_explicit_metadata_contract(self):
            got=self.result()
            self.assertTrue(got['passed'])
            self.assertEqual(set(got['global_attribute_differences']),{'START_DATE'})
            self.assertEqual(set(got['dimension_differences']),{'Time'})
            self.assertEqual(got['unexplained_global_attribute_differences'],{})
            self.assertTrue(got['all_raw_dtype_shape_dimensions_bytes_equal'])

    def test_signed_zero_rejected_as_raw_byte_difference(self):
            with Dataset(self.new,'a') as ds:ds.variables['T2'][0,0]=np.float32(-0.)
            got=self.result()
            self.assertFalse(got['passed'])
            self.assertFalse(got['variable_results']['T2']['raw_bytes_equal'])

    def test_wrong_raw_type_and_time_rejected(self):
            restart_fixture(self.new,['2000-01-25_01:00:00'],'2000-01-25_00:00:00',changed_dtype=True)
            self.assertFalse(self.result()['passed'])
            self.assertFalse(self.result()['variable_results']['T2']['dtype_shape_dimensions_equal'])
            restart_fixture(self.new,['2000-01-25_00:00:00'],'2000-01-25_00:00:00')
            got=self.result()
            self.assertFalse(got['variable_results']['Times']['raw_bytes_equal'])
            self.assertFalse(got['passed'])

    def test_unexplained_global_metadata_rejected(self):
            with Dataset(self.new,'a') as ds:ds.setncattr('MP_PHYSICS',np.int32(8))
            got=self.result()
            self.assertFalse(got['passed'])
            self.assertIn('MP_PHYSICS',got['unexplained_global_attribute_differences'])
            self.assertIn('START_DATE',got['expected_run_control_differences'])

    def test_missing_required_startdate_transition_rejected(self):
            with Dataset(self.new,'a') as ds:ds.setncattr('START_DATE','2000-01-24_12:00:00')
            self.assertFalse(self.result()['passed'])
            with Dataset(self.new,'a') as ds:ds.setncattr('START_DATE','wrong-date')
            got=self.result()
            self.assertFalse(got['passed'])
            self.assertIn('START_DATE',got['unexplained_global_attribute_differences'])

    def test_variable_attribute_and_added_variable_rejected(self):
            with Dataset(self.new,'a') as ds:ds.variables['T2'].setncattr('units','C')
            got=self.result()
            self.assertFalse(got['passed'])
            self.assertIn('T2',got['variable_attribute_differences'])
            restart_fixture(self.new,['2000-01-25_01:00:00'],'2000-01-25_00:00:00')
            with Dataset(self.new,'a') as ds:ds.createVariable('EXTRA','f4',('Time',))[:]=0.
            got=self.result()
            self.assertFalse(got['all_variable_names_equal'])
            self.assertFalse(got['passed'])

class AdditionalControls(unittest.TestCase):
    def test_source_collision_precedes_freeze_read(self):
        with tempfile.TemporaryDirectory() as t:
            task=Path(t);(task/'source').mkdir();(task/'source/sentinel').write_bytes(b'preserve')
            with patch.object(sp,'HERE',task),patch.object(sp,'source_inputs',side_effect=AssertionError('must not read')):
                with self.assertRaises(FileExistsError):sp.prepare(SimpleNamespace())
            self.assertEqual((task/'source/sentinel').read_bytes(),b'preserve')

    def test_pending_spec_cannot_create_source(self):
        with tempfile.TemporaryDirectory() as t:
            task=Path(t);f=task/'pending.json';m.write_json(f,{'status':'PENDING_FREEZE','base_commit':m.BASE})
            with patch.object(sp,'HERE',task):
                with self.assertRaises(ValueError):sp.prepare(SimpleNamespace(freeze_spec=f,freeze_sha=m.digest(f),prepare_go=True))
            self.assertFalse((task/'source').exists())

    def test_receipt_collisions_precede_runtime_pins(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'execution-receipt-v1.json').write_bytes(b'prior fail')
            with patch.object(case,'invariants',side_effect=AssertionError('must not read')):
                with self.assertRaises(FileExistsError):case.run(SimpleNamespace(stage_receipt=root/'stage.json'))
            self.assertEqual((root/'execution-receipt-v1.json').read_bytes(),b'prior fail')
            (root/'restart-execution-v1.json').write_bytes(b'prior restart')
            with patch.object(restart,'invariants',side_effect=AssertionError('must not read')):
                with self.assertRaises(FileExistsError):restart.run(SimpleNamespace(stage_receipt=root/'stage.json'))
            self.assertEqual((root/'restart-execution-v1.json').read_bytes(),b'prior restart')

    def test_zero_output_and_false_make_success_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/'empty.f90';f.write_bytes(b'')
            with self.assertRaises(ValueError):m.nonempty_artifact(f)
        self.assertFalse(m.classify_build_log('nothing',0)['passed'])
        self.assertFalse(m.classify_build_log('Error: invalid shape\nExecutables successfully built',0)['passed'])
        self.assertFalse(m.classify_build_log('Executables successfully built',1)['passed'])
        self.assertTrue(m.classify_build_log('Executables successfully built',0)['passed']) # Classification only, not BUILD_PASS.

    def test_named_symlink_and_content_changes(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);f=root/'a';f.write_bytes(b'original');link=root/'link';link.symlink_to(f)
            before=m.link_pin(link);f.write_bytes(b'changed');self.assertNotEqual(before,m.link_pin(link))
            link.unlink();link.symlink_to(root/'missing')
            with self.assertRaises(FileNotFoundError):m.link_pin(link)

    def test_dependency_aslr_normalized_and_loader_included(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);lib=root/'lib.so';lib.write_bytes(b'lib');loader=root/'ld.so';loader.write_bytes(b'loader')
            def result(address):return SimpleNamespace(returncode=0,stdout=f'lib.so => {lib} (0x{address})\n {loader} (0x{address})\n')
            with patch.object(m.subprocess,'run',return_value=result('abc')):a=m.library_pins(root/'not_called','')
            with patch.object(m.subprocess,'run',return_value=result('123')):b=m.library_pins(root/'not_called','')
            self.assertEqual(a,b);self.assertEqual(len(a['libraries']),2)
            lib.write_bytes(b'changed')
            with patch.object(m.subprocess,'run',return_value=result('123')):self.assertNotEqual(a,m.library_pins(root/'not_called',''))

    def test_manifest_corruption_and_linktext_change(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'synthetic';(source/'WRF').mkdir(parents=True)
            config=source/'WRF/configure.wrf';shutil.copy2(m.ROOT/'build/udm-cu-fresh-gnu-v2/source/WRF/configure.wrf',config)
            data=source/'data';data.write_bytes(b'synthetic source');entries=[{'path':'data','type':'file','size':data.stat().st_size,'sha256':m.digest(data)},{'path':'WRF/configure.wrf','type':'file','size':config.stat().st_size,'sha256':m.digest(config)}]
            for i in range(17):
                p=source/f'link{i}';p.symlink_to('data');entries.append({'path':p.name,'type':'symlink','target':'data'})
            manifest=root/'manifest.json';m.write_json(manifest,{'base_commit':m.BASE,'source_path':str(source),'entry_count':len(entries),'symlink_count':17,'files':entries})
            mp=m.pin(manifest);self.assertEqual(m.verify_manifest(mp)['entry_count'],19)
            (source/'link0').unlink();(source/'link0').symlink_to('./data')
            with self.assertRaises(ValueError):m.verify_manifest(mp)
            (source/'link0').unlink();(source/'link0').symlink_to('data');data.write_bytes(b'corrupt')
            with self.assertRaises(ValueError):m.verify_manifest(mp)

    def test_restart_only_five_control_changes(self):
        original=(m.HIST/'ra4/namelist.input').read_text();changed=m.restart_namelist(original)
        self.assertEqual(sum(a!=b for a,b in zip(original.splitlines(),changed.splitlines())),5)
        with self.assertRaises(ValueError):m.restart_namelist(original+'\n restart=.false.,\n')

    def test_checkpoint_semantic_bounds_no_epsilon(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'cp.nc'
            with Dataset(p,'w') as d:
                d.createDimension('Time',1);d.createDimension('south_north',60);d.createDimension('west_east',73)
                for n in ('USTM','QZ0'):d.createVariable(n,'f4',('Time','south_north','west_east'))[:]=0.
            self.assertTrue(m.checkpoint_diagnostics(p)['passed'])
            with Dataset(p,'a') as d:d.variables['QZ0'][0,0,0]=np.float32(1e-30)
            self.assertFalse(m.checkpoint_diagnostics(p)['passed'])
            with Dataset(p,'a') as d:d.variables['QZ0'][0,0,0]=0.;d.variables['USTM'][0,0,0]=-0.01
            self.assertFalse(m.checkpoint_diagnostics(p)['passed'])

    def test_process_group_timeout(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);marker=root/'descendant-survived'
            child=f"import time;from pathlib import Path;time.sleep(1.5);Path({str(marker)!r}).write_text('bad')"
            parent=f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{child!r}]);time.sleep(60)"
            result=m.bounded_process([sys.executable,'-c',parent],root,os.environ.copy(),root/'timeout.log',.2)
            self.assertTrue(result['timed_out']);self.assertNotEqual(result['returncode'],0);time.sleep(1.6);self.assertFalse(marker.exists())

    def test_guards_remain_active_python_optimized(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'existing';p.write_bytes(b'original')
            script=f"import importlib.util;from pathlib import Path;s=importlib.util.spec_from_file_location('m',{str(HERE/'winter_validation_v1.py')!r});m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\ntry:m.collision(Path({str(p)!r}))\nexcept FileExistsError:raise SystemExit(0)\nraise SystemExit(1)"
            r=subprocess.run([sys.executable,'-O','-c',script],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            self.assertEqual(r.returncode,0,r.stdout.decode())

if __name__=='__main__':
    loader=unittest.TestLoader();suite=unittest.TestSuite(loader.loadTestsFromTestCase(c) for c in (NetCDFControls,RestartControls,AdditionalControls))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    output=HERE/'offline-controls-v1.json';m.collision(output)
    m.write_json(output,{'status':'PASS' if result.wasSuccessful() else 'FAIL','tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'scope':'Synthetic NetCDF/files/short Python timeout process only; no source checkout/compiler/WRF/MPI','source_snapshots':0,'compile_invocations':0,'model_invocations':0,'tests':m.pin(Path(__file__)),'common':m.pin(HERE/'winter_validation_v1.py')})
    raise SystemExit(0 if result.wasSuccessful() else 1)
