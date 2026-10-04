#!/usr/bin/env python3
"""Compile actual wrapper diagnostic blocks; no model or optical engine runs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
WRF = HERE.parents[1]
FIELDS = re.compile(r'([A-Za-z][A-Za-z0-9_]*)\s*=\s*(.*?)(?=\s+[A-Za-z][A-Za-z0-9_]*\s*=|$)')
TAGS = ('RRTMGP_UDM_PHASE_PATH', 'RRTMGP_CU_POPULATION', 'RRTMGP_CU_LUT_CLIP')
CONTEXT = {'tile_i', 'tile_j', 'domain', 'radiation_step', 'source_time_seconds', 'overlap', 'phase'}
SCHEMES = {
    TAGS[0]: CONTEXT | {'native_grid_path_sum_g_m2', 'cf0_omitted_grid_path_sum_g_m2',
                       'cf0_omitted_layer_count', 'cf0_grid_path_fraction'},
    TAGS[1]: CONTEXT | {'accepted_grid_sum_g_m2', 'rejected_grid_sum_g_m2', 'rejected_grid_max_g_m2',
                       'omitted_cf0_count', 'omitted_cf0_sum_g_m2', 'omitted_cf0_max_g_m2',
                       'negative_source_count', 'negative_active_count'},
    TAGS[2]: CONTEXT | {'low_layers', 'low_grid_path_g_m2', 'high_layers', 'high_grid_path_g_m2',
                       'eligible_grid_path_g_m2', 'clipped_grid_path_fraction', 'max_low_g_m2', 'max_high_g_m2'},
}

def parse_row(line):
    m = re.match(r'\s*(LW|SW) (' + '|'.join(TAGS) + r')\s+', line)
    if not m:
        return None
    fields = {}
    for key, value in FIELDS.findall(line[m.end():]):
        if key in fields:
            raise ValueError('duplicate field ' + key)
        fields[key] = value.strip()
    if set(fields) != SCHEMES[m[2]]:
        raise ValueError('missing or unexpected diagnostic field')
    if fields['phase'] not in ('LIQ', 'ICE', 'RAIN', 'SNOW'):
        raise ValueError('invalid phase')
    for key in ('tile_i', 'tile_j'):
        if not re.fullmatch(r'\d+\s*:\s*\d+', fields[key]):
            raise ValueError('invalid tile')
        fields[key] = tuple(int(x) for x in fields[key].split(':'))
    for key, value in tuple(fields.items()):
        if key in ('phase', 'tile_i', 'tile_j'):
            continue
        if key in ('domain', 'radiation_step', 'source_time_seconds') and value == 'UNAVAILABLE':
            fields[key] = None
            continue
        number = float(value.replace('D', 'E'))
        if not (abs(number) < float('inf')):
            raise ValueError('nonfinite field')
        if key not in CONTEXT and number < 0:
            raise ValueError('negative metric')
        if key in ('domain', 'radiation_step', 'overlap') or key.endswith(('count', 'layers')):
            if number != int(number):
                raise ValueError('noninteger field')
            number = int(number)
        fields[key] = number
    return {'radiation': m[1], 'tag': m[2], 'fields': fields, 'raw': line}

def identity(row, rank):
    f = row['fields']
    if any(f[x] is None for x in ('domain', 'radiation_step', 'source_time_seconds')):
        return None
    return (rank, row['radiation'], row['tag'], f['phase'], f['domain'],
            f['radiation_step'], f['source_time_seconds'], f['tile_i'], f['tile_j'])

def require_unique(rows, rank=0):
    seen = set()
    for row in rows:
        key = identity(row, rank)
        if key is not None:
            if key in seen:
                raise ValueError('duplicate diagnostic call identity')
            seen.add(key)

def block(source, name):
    start, end = '! ' + name + '_BEGIN', '! ' + name + '_END'
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError('nonunique source block: ' + name)
    return source.split(start, 1)[1].split(end, 1)[0]

def pin(path):
    b = path.read_bytes()
    return {'path': str(path), 'size': len(b), 'sha256': hashlib.sha256(b).hexdigest()}

def fixture(source, mutation=None):
    reset = block(source, 'RRTMGP_PHASE_TOTAL_RESET')
    aggregate = block(source, 'RRTMGP_NATIVE_PHASE_SUM')
    gate = block(source, 'RRTMGP_CU_CLIP_GATE')
    context = block(source, 'RRTMGP_PHASE_CONTEXT')
    native_row = block(source, 'RRTMGP_NATIVE_PHASE_ROW')
    # Use the actual native reporting gate and local labels as well as its
    # row writer, so a reporting-policy change cannot hide behind a fixture.
    phase_header = source.split('! RRTMGP_NATIVE_PHASE_ROW_BEGIN', 1)[0]
    phase_header = phase_header[phase_header.rindex('   IF(run_rrtmgp) THEN\n    BLOCK\n     LOGICAL :: report_phase_paths'):]
    native_reporting = phase_header + native_row + '\n     END IF\n    END BLOCK\n   END IF\n'
    cu_rows = block(source, 'RRTMGP_CU_ROWS')
    if mutation == 'ungated':
        gate = gate.replace('IF(icld/=0) THEN', 'IF(.TRUE.) THEN')
    elif mutation == 'wrong_denominator':
        aggregate = aggregate.replace('SUM(REAL(gp_grid(:,gp_phase),8))', 'SUM(REAL(gp_cu_grid(:,1),8))')
    elif mutation == 'stale_reset':
        reset = reset.replace('gp_native_grid_sum=0.d0', 'gp_native_grid_sum=123.d0')
    elif mutation == 'short_buffer':
        pass
    elif mutation is not None:
        raise ValueError(mutation)
    message_len = 512 if mutation == 'short_buffer' else 1024
    return f'''program diagnostic_source_fixture
  implicit none
  call exercise('active',2,1.,rrtmgp_domain_id=2147483647,audit_step=2147483647,audit_time=86400.)
  call exercise('zero',2,0.,rrtmgp_domain_id=1,audit_step=8,audit_time=600.)
  call exercise('again',2,1.,rrtmgp_domain_id=2,audit_step=9,audit_time=600.)
  call exercise('absent',2,1.)
  call exercise('domain_only',2,1.,rrtmgp_domain_id=3)
  call exercise('clock_only',2,1.,audit_step=20,audit_time=1200.)
  call exercise('override',2,1.,mcica_seed_override=0)
  call exercise('negative_override',2,1.,mcica_seed_override=-1)
  call exercise('overlap0',0,1.,rrtmgp_domain_id=1,audit_step=10,audit_time=600.)
  call exercise('overlap1',1,1.,rrtmgp_domain_id=1,audit_step=11,audit_time=600.)
  call exercise('overlap3',3,1.,rrtmgp_domain_id=1,audit_step=12,audit_time=600.)
  call exercise('legacy4',2,1.,run37=.false.)
contains
subroutine exercise(label,icld,scale,rrtmgp_domain_id,audit_step,audit_time,mcica_seed_override,run37)
  use module_ra_rrtmgp_input, only: rrtmgp_summarize_path_clipping
  implicit none
  character(*),intent(in) :: label
  integer,intent(in) :: icld
  real,intent(in) :: scale
  integer,optional,intent(in) :: rrtmgp_domain_id,audit_step,mcica_seed_override
  real,optional,intent(in) :: audit_time
  logical,optional,intent(in) :: run37
  integer,parameter :: kts=1,kte=3,i=1,j=1,ncol=1,its=100000,ite=100001,jts=200000,jte=200001
  logical :: run_rrtmgp,use_cu_population
  integer :: gp_phase,column
  real :: gp_grid(3,6),gp_omitted_phase(3,6),gp_cu_grid(3,2),cu_cf3d(1,3,1)
  real :: gp_cu_reliq(1,3),gp_cu_reice(1,3)
  real(8) :: gp_liq_min,gp_liq_max,gp_ice_min,gp_ice_max
  integer(8) :: gp_cf0_count(4),gp_nlow_tmp,gp_nhigh_tmp
  integer(8) :: gp_cu_clip_low_count(2),gp_cu_clip_high_count(2),gp_cu_omitted_count(2)
  integer(8) :: gp_cu_negative_source(2),gp_cu_negative_active(2)
  real(8) :: gp_native_grid_sum(4),gp_cf0_sum(4),gp_cf0_max(4)
  real(8) :: gp_slow_tmp,gp_mlow_tmp,gp_shigh_tmp,gp_mhigh_tmp,gp_total_tmp
  real(8) :: gp_cu_clip_low_sum(2),gp_cu_clip_low_max(2),gp_cu_clip_high_sum(2)
  real(8) :: gp_cu_clip_high_max(2),gp_cu_clip_total(2)
  real(8) :: gp_cu_accepted_sum(2),gp_cu_rejected_sum(2),gp_cu_rejected_max(2)
  real(8) :: gp_cu_omitted_sum(2),gp_cu_omitted_max(2)
  character(len={message_len}) :: gp_diag_message
  character(len=256) :: gp_diag_context
  character(len=32) :: gp_diag_domain,gp_diag_step,gp_diag_time
  write(*,'(A)') 'CASE '//label
  run_rrtmgp=.true.
  if(present(run37)) run_rrtmgp=run37
  use_cu_population=run_rrtmgp
{reset}
  gp_grid(:,1)=[1.,2.,3.]*scale;gp_grid(:,2)=[4.,0.,6.]*scale
  gp_grid(:,3)=[0.,7.,8.]*scale;gp_grid(:,4)=[9.,10.,0.]*scale
  gp_grid(:,5:6)=1.e8*scale
  gp_omitted_phase=0.
  gp_omitted_phase(1,1)=scale;gp_omitted_phase(1,2)=4.*scale;gp_omitted_phase(1,4)=9.*scale
  gp_cu_grid(:,1)=[2.,0.,5.]*scale;gp_cu_grid(:,2)=[2.,0.,5.]*scale
  if(run_rrtmgp) then
   do column=1,2
{aggregate}
   end do
  end if
  gp_cu_clip_low_count=0;gp_cu_clip_high_count=0
  gp_cu_clip_low_sum=0.;gp_cu_clip_high_sum=0.;gp_cu_clip_low_max=0.;gp_cu_clip_high_max=0.;gp_cu_clip_total=0.
  gp_liq_min=2.5d0;gp_liq_max=21.5d0;gp_ice_min=10.d0;gp_ice_max=180.d0
  cu_cf3d(1,:,1)=[0.5,0.,0.5];gp_cu_reliq(1,:)=[1.,2.5,30.];gp_cu_reice(1,:)=[4.,90.,100.]
  gp_cu_accepted_sum=7.*scale;gp_cu_rejected_sum=scale;gp_cu_rejected_max=scale
  gp_cu_omitted_count=0;gp_cu_omitted_sum=0.;gp_cu_omitted_max=0.
  gp_cu_negative_source=1;gp_cu_negative_active=1
  if(use_cu_population) then
{gate}
  end if
{context}
{native_reporting}
{cu_rows}
end subroutine exercise
subroutine wrf_debug(level,message)
  integer,intent(in) :: level
  character(*),intent(in) :: message
  write(*,'(A)') trim(message)
end subroutine wrf_debug
end program diagnostic_source_fixture
'''

def compile_and_run(source, phase, output, compiler, mutation=None):
    name = phase.lower() + '-' + (mutation or 'actual')
    driver = output / (name + '.f90')
    driver.write_text(fixture(source, mutation))
    executable = output / name
    cmd = [compiler, '-cpp', '-ffree-form', '-ffree-line-length-none', '-fcheck=all',
           '-finit-real=snan', '-J', str(output), '-I', str(output),
           str(WRF / 'phys/module_ra_rrtmgp_input.F'), str(HERE / 'standalone_wrf_error.f90'),
           str(driver), '-o', str(executable)]
    result = subprocess.run(cmd, cwd=output, text=True, capture_output=True)
    (output / (name + '-compile.log')).write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    run = subprocess.run([str(executable)], cwd=output, text=True, capture_output=True)
    (output / (name + '-run.log')).write_text(run.stdout + run.stderr)
    return run

def cases(stdout):
    result, current = {}, None
    for line in stdout.splitlines():
        if line.startswith('CASE '):
            current = line[5:]
            if current in result:
                raise ValueError('duplicate fixture case')
            result[current] = []
        else:
            row = parse_row(line)
            if row:
                if current is None:
                    raise ValueError('row outside case')
                result[current].append(row)
    return result

class ContractTests(unittest.TestCase):
    def test_native_denominator_and_zero_omission(self):
        for phase, c in self.outputs.items():
            rows = {r['fields']['phase']: r['fields'] for r in c['active'] if r['tag'] == TAGS[0]}
            self.assertEqual([rows[p]['native_grid_path_sum_g_m2'] for p in ('LIQ','ICE','RAIN','SNOW')], [12,20,30,38])
            self.assertEqual([rows[p]['cf0_omitted_grid_path_sum_g_m2'] for p in ('LIQ','ICE','RAIN','SNOW')], [2,8,0,18])
            self.assertEqual(rows['RAIN']['cf0_grid_path_fraction'], 0)
            self.assertEqual(rows['ICE']['cf0_grid_path_fraction'], 0.4)
            self.assertAlmostEqual(rows['LIQ']['cf0_grid_path_fraction'], 1/6, places=16)
            self.assertEqual([rows[p]['cf0_omitted_layer_count'] for p in ('LIQ','ICE','RAIN','SNOW')], [2,2,0,2])

    def test_reset_zero_and_absent_context(self):
        for c in self.outputs.values():
            self.assertFalse([r for r in c['zero'] if r['tag'] == TAGS[0]])
            a = [r['fields']['native_grid_path_sum_g_m2'] for r in c['active'] if r['tag'] == TAGS[0]]
            b = [r['fields']['native_grid_path_sum_g_m2'] for r in c['again'] if r['tag'] == TAGS[0]]
            self.assertEqual(a,b)
            for r in c['absent']:
                self.assertIsNone(identity(r,0))
                self.assertIsNone(r['fields']['domain'])
            for r in c['domain_only']:
                self.assertEqual(r['fields']['domain'],3)
                self.assertIsNone(r['fields']['radiation_step'])
                self.assertIsNone(r['fields']['source_time_seconds'])
            for r in c['clock_only']:
                self.assertIsNone(r['fields']['domain'])
                self.assertEqual(r['fields']['radiation_step'],20)
                self.assertEqual(r['fields']['source_time_seconds'],1200)

    def test_cu_overlap_gate_preserves_filter(self):
        for c in self.outputs.values():
            self.assertFalse([r for r in c['overlap0'] if r['tag'] == TAGS[2]])
            for label in ('active','overlap0','overlap1','overlap3'):
                pops = [r for r in c[label] if r['tag'] == TAGS[1]]
                self.assertEqual(len(pops),2)
                self.assertTrue(all(r['fields']['accepted_grid_sum_g_m2']==7 for r in pops))
                self.assertTrue(all(r['fields']['rejected_grid_sum_g_m2']==1 for r in pops))
            for label in ('active','overlap1','overlap3'):
                clip = [r for r in c[label] if r['tag'] == TAGS[2]]
                self.assertEqual(len(clip),2)
                self.assertTrue(all(r['fields']['low_grid_path_g_m2']==2 for r in clip))
                self.assertTrue(all(r['fields']['high_grid_path_g_m2']==5 for r in clip))

    def test_buffers_present_context_and_legacy(self):
        for c in self.outputs.values():
            self.assertEqual(c['legacy4'],[])
            rows = c['active']
            self.assertTrue(any(len(r['raw'])>512 for r in rows))
            self.assertTrue(all(len(r['raw'])<=1024 for r in rows))
            for r in rows:
                self.assertEqual(r['fields']['domain'],2147483647)
                self.assertEqual(r['fields']['radiation_step'],2147483647)
                self.assertEqual(r['fields']['source_time_seconds'],86400)
                self.assertEqual(r['fields']['tile_i'],(100000,100001))

    def test_seed_override_suppression(self):
        for c in self.outputs.values():
            self.assertEqual(c['override'],[])
            self.assertTrue(c['negative_override'])

    def test_parser_rejects_missing_duplicate_nonfinite(self):
        line = next(r['raw'] for r in self.outputs['LW']['active'] if r['tag']==TAGS[0])
        for malformed in (line.split(' cf0_grid_path_fraction=')[0], line+' phase=RAIN',
                          re.sub(r'source_time_seconds=\s*\S+', 'source_time_seconds=nan',line)):
            with self.assertRaises(ValueError): parse_row(malformed)

    def test_parser_interleaved_domains_tiles_steps_phases(self):
        all_rows = []
        for phase in ('LW','SW'):
            for label in ('active','again','overlap1','overlap3'):
                all_rows.extend(self.outputs[phase][label])
        require_unique(list(reversed(all_rows)))
        original = all_rows[0]
        # Independent key changes at the same call context test identity
        # separation rather than relying on several keys changing at once.
        alternatives = [
            re.sub(r'tile_i=\s*100000\s*:\s*100001','tile_i=100002:100003',original['raw']),
            re.sub(r'domain=\s*2147483647','domain=2',original['raw']),
            re.sub(r'radiation_step=\s*2147483647','radiation_step=2',original['raw']),
        ]
        for line in alternatives:
            changed = parse_row(line)
            self.assertNotEqual(identity(original,0),identity(changed,0))
            require_unique([original,changed])
        with self.assertRaises(ValueError): require_unique(all_rows+[all_rows[0]])
        self.assertNotEqual(identity(all_rows[0],0),identity(all_rows[0],1))

    def test_source_boundary_and_once_per_column(self):
        for source in self.sources.values():
            aggregate = block(source,'RRTMGP_NATIVE_PHASE_SUM')
            self.assertEqual(aggregate.count('gp_native_grid_sum(gp_phase)='),1)
            self.assertIn('DO gp_phase=1,4',aggregate)
            self.assertNotIn('gp_rad',aggregate)
            self.assertNotIn('gp_cu_grid',aggregate)
            self.assertNotIn('SAVE',block(source,'RRTMGP_PHASE_CONTEXT').upper())
            self.assertEqual(source.count('CHARACTER(LEN=1024) :: gp_diag_message'),1)
            self.assertIn("' sum_layer_grid_wp_g_m2=',gp_cf0_sum(gp_phase)",source)

    def test_counterfactuals_are_detected(self):
        for phase, c in self.counterfactuals.items():
            ungated = cases(c['ungated'].stdout)
            self.assertTrue([r for r in ungated['overlap0'] if r['tag']==TAGS[2]])
            for name in ('wrong_denominator','stale_reset'):
                rows = cases(c[name].stdout)['active']
                totals = [r['fields']['native_grid_path_sum_g_m2'] for r in rows if r['tag']==TAGS[0]]
                self.assertNotEqual(totals,[12,20,30,38])
            self.assertNotEqual(c['short_buffer'].returncode,0)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', default=shutil.which('gfortran'))
    parser.add_argument('--output-root', type=Path)
    args = parser.parse_args()
    if not args.compiler:
        raise SystemExit('GNU Fortran is required')
    if args.output_root:
        args.output_root.mkdir(parents=True,exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='phase-diagnostic-',dir=args.output_root))
    paths = {'LW':WRF/'phys/module_ra_rrtmg_lw.F', 'SW':WRF/'phys/module_ra_rrtmg_sw.F'}
    inputs = list(paths.values())+[WRF/'phys/module_ra_rrtmgp_input.F',HERE/'standalone_wrf_error.f90',Path(__file__)]
    before = [pin(p) for p in inputs]
    sources = {k:p.read_text() for k,p in paths.items()}
    actual = {k:compile_and_run(s,k,output,args.compiler) for k,s in sources.items()}
    if any(r.returncode for r in actual.values()): raise RuntimeError('actual diagnostic fixture failed')
    ContractTests.sources=sources
    ContractTests.outputs={k:cases(r.stdout) for k,r in actual.items()}
    ContractTests.counterfactuals={k:{m:compile_and_run(s,k,output,args.compiler,m) for m in
        ('ungated','wrong_denominator','stale_reset','short_buffer')} for k,s in sources.items()}
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests))
    after=[pin(p) for p in inputs]
    receipt={'status':'PASS' if result.wasSuccessful() and before==after else 'FAIL_PRESERVED',
             'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
             'input_pins':before,'input_pre_post_identical':before==after,'output_path':str(output),
             'model_invocations':0,'focused_source_extracted_compiles':10,
             'artifacts':[pin(p) for p in sorted(output.iterdir()) if p.is_file()]}
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'status':receipt['status'],'receipt':pin(output/'receipt.json')}))
    raise SystemExit(0 if receipt['status']=='PASS' else 1)

if __name__=='__main__': main()
