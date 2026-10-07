import importlib.util,json,pathlib,tempfile,unittest,sys
sys.dont_write_bytecode=True
P=pathlib.Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('cf_validator',P/'validate_cf_population.py');v=importlib.util.module_from_spec(sp);sp.loader.exec_module(v)
def fmt(x):return format(float(x),'.17e')
def write_cf(p,step,phase,rows):
 h=[1,step,phase,1,1,23,2,1,44,32,44,44,0]
 lines=['UDM37CFPOP1',' '.join(map(str,h)),' '.join(map(fmt,[step-1,60.,60.]))]
 for k,r in enumerate(rows,1):lines.append(f'{k} 1 1 '+' '.join(map(fmt,r)))
 p.write_text('\n'.join(lines)+'\n')
def write_num(p,step,stage,rows):
 sub=1 if stage in (21,23,30,31) else 0
 av=17 if stage in (21,23,30) else 29 if stage==31 else 2 if stage==51 else 0
 lines=['UDM37NUM1',' '.join(map(str,[1,step,stage,sub,1,23,2,1,44,32,av,int(step==1)])),' '.join(map(fmt,[step-1,60.,1.e8]))]
 for k,r in enumerate(rows,1):lines.append(f'{k} '+' '.join(map(fmt,r)))
 p.write_text('\n'.join(lines)+'\n')
def fixture(d,fraction=.5,nc=1.e8):
 for step in (1,2):
  r=[v.f32(fraction),v.f32(280.),v.f32(9.e4),v.f32(.01),v.f32(1.e-4),0.,v.f32(2.e-5),0.,0.,0.,v.f32(1.e8),v.f32(nc),v.f32(2.e5),v.f32(1.1)]
  a=[r[:] for _ in range(44)]
  b=[r[:] for r in a]
  for r in b:
   for m in v.MASS:r[m]=v.f32(r[m]/r[0])
  c=[r[:] for r in b]
  # Intervening legitimate process changes; inverse2→3 is intentionally false.
  c[6][4]=v.f32(c[6][4]*.75);c[6][11]=v.f32(c[6][11]+64.)
  z=[r[:] for r in c]
  for r in z:
   for m in v.MASS:r[m]=v.f32(r[m]*r[0])
  for phase,rows in enumerate((a,b,c,z),1):write_cf(d/f'population_d1_tile1_i23_j2_step{step}_sub1_phase{phase}.cfpop',step,phase,rows)
  nn=[[r[j] for j in v.NUM_TO_CF]+[0.]*5 for r in a]
  for stage in (10,11,20,21,23,30,31,40,50,51):
   rows=[r[:] for r in nn]
   if stage in (21,23,30,31):
    for r in rows:r[13]=60.
   if stage==51:
    for r in rows:r[10]=v.f32(8.e-6)
   sub=1 if stage in (21,23,30,31) else 0
   write_num(d/f'number_d1_tile1_i23_j2_step{step}_stage{stage}_sub{sub}.raw',step,stage,rows)
def corrupt(d,name,line,token,value):
 p=d/name;q=p.read_text().splitlines();r=q[line].split();r[token]=str(value);q[line]=' '.join(r);p.write_text('\n'.join(q)+'\n')
class Controls(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.d=pathlib.Path(self.tmp.name);fixture(self.d)
 def tearDown(self):self.tmp.cleanup()
 def reject(self):
  with self.assertRaises(ValueError):v.validate(self.d)
 def test_positive_fractional_and_process_change(self):
  r=v.validate(self.d);self.assertTrue(r['status'].startswith('PASS'));self.assertEqual(r['transformation_checks'],1056);self.assertEqual(r['unchanged_number_checks'],528);self.assertEqual(r['predivision_NUMBER23_joins'],88);self.assertEqual(r['return_helper_state_joins'],176);self.assertEqual(len(r['discriminating_selected_levels']),2);self.assertGreater(r['intervening_process_changes'][0]['changed_mass_fields'],0)
 def test_cf_one_is_non_discriminating(self):fixture(self.d,1.);self.assertTrue(v.validate(self.d)['status'].startswith('NON_DISCRIMINATING'))
 def test_zero_nc_is_non_discriminating(self):fixture(self.d,.5,0.);self.assertTrue(v.validate(self.d)['status'].startswith('NON_DISCRIMINATING'))
 def test_bad_mask(self):corrupt(self.d,'population_d1_tile1_i23_j2_step1_sub1_phase1.cfpop',9,1,0);self.reject()
 def test_bad_division(self):corrupt(self.d,'population_d1_tile1_i23_j2_step1_sub1_phase2.cfpop',9,7,v.f32(.00019));self.reject()
 def test_bad_restoration(self):corrupt(self.d,'population_d1_tile1_i23_j2_step1_sub1_phase4.cfpop',9,7,v.f32(.00017));self.reject()
 def test_number_mutation(self):corrupt(self.d,'population_d1_tile1_i23_j2_step1_sub1_phase4.cfpop',9,14,v.f32(9.e7));self.reject()
 def test_bad_clock(self):corrupt(self.d,'population_d1_tile1_i23_j2_step1_sub1_phase3.cfpop',2,0,1.);self.reject()
 def test_helper_state_mutation(self):corrupt(self.d,'number_d1_tile1_i23_j2_step1_stage50_sub0.raw',9,4,v.f32(.0002));self.reject()
 def test_missing_phase(self):(self.d/'population_d1_tile1_i23_j2_step1_sub1_phase1.cfpop').unlink();self.reject()
 def test_extra_cf_file(self):(self.d/'extra.cfpop').write_bytes((self.d/'population_d1_tile1_i23_j2_step1_sub1_phase1.cfpop').read_bytes());self.reject()
 def test_nonfinite(self):corrupt(self.d,'population_d1_tile1_i23_j2_step1_sub1_phase1.cfpop',9,7,'NaN');self.reject()
if __name__=='__main__':unittest.main()
