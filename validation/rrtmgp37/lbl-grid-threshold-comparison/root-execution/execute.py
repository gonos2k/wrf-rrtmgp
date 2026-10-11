from run_common import *
stage=BASE/'stage';objects=stage/'build/lblrtm_v12.17_linux_gnu_dbl.obj'
before={p.name:sha(p) for p in objects.glob('*.o')}
run('build',['/usr/bin/make','-f','make_lblrtm','linuxGNUdbl'],stage/'build',ENV)
after={p.name:sha(p) for p in objects.glob('*.o')};changed=[n for n in before if before[n]!=after[n]]
if changed!=['oprop.o']:raise ValueError('unexpected object change')
write('object-comparison.json',{'changed_objects':changed,'other_objects':len(before)-1,'all_other_objects_identical':True})
exe=stage/'lblrtm_v12.17_linux_gnu_dbl'
libs=subprocess.check_output(['/usr/bin/ldd',str(exe)],env=ENV,text=True)
write('execution-identity.json',{'source_sha256':sha(stage/'src/oprop.f90'),'executable_sha256':sha(exe),
  'compiler_version':subprocess.check_output(['/usr/bin/gfortran','--version'],text=True).splitlines()[0],'ldd':libs,'production_accepted':False})
arms=[('h-off',4.,-1.,False),('h',4.,-1.,True),('half',8.,-1.,True),('quarter',16.,-1.,True),('weak10',4.,2e-5,True),('weak0',4.,0.,True)]
write('plan.json',{'arms':[{'name':n,'SAMPLE':s,'DPTMIN_input':d,'observer':o,'IOD':2} for n,s,d,o in arms],
  'held_state_source':'Full original45-layer TAPE5, all state lines identical; official IOD2 exact-DV path fixed in all comparison arms',
  'grid_axis':['h','half','quarter'],'threshold_axis':['h','weak10','weak0'],'probe_separate':True,'production_accepted':False})
for name,sample,threshold,on in arms:
    case,rows=prepare_case('case-'+name,sample,threshold)
    env=ENV.copy();env['UDM37_MIN_R3_TRACE']='1' if on else '0'
    run('solver-'+name,[str(exe)],case,env)
    check_inputs(case,rows)
    print('Completed',name,flush=True)
