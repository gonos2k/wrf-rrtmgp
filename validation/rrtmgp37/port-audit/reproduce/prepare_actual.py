from pathlib import Path
import subprocess,shlex,json,hashlib
root=Path.cwd(); wrf=root/'WRF'; out=root/'build/port-audit-inputs'; out.mkdir(exist_ok=True)
module='''MODULE port_audit
 IMPLICIT NONE
 INTEGER,SAVE :: units(2)=0
 LOGICAL,SAVE :: done(2)=.FALSE.
CONTAINS
 SUBROUTINE begin_audit(phase,i,j,gp,icld,iceflag,inflag,play,plev,tlay,tlev,h2o,co2,o3,n2o,ch4,o2,cf,lwp,iwp,swp,rel,rei,res,solar,mu0)
 CHARACTER(*),INTENT(IN):: phase
 INTEGER,INTENT(IN)::i,j,icld,iceflag,inflag
 LOGICAL,INTENT(IN)::gp
 REAL,INTENT(IN)::play(:,:),plev(:,:),tlay(:,:),tlev(:,:),h2o(:,:),co2(:,:),o3(:,:),n2o(:,:),ch4(:,:),o2(:,:),cf(:,:),lwp(:,:),iwp(:,:),swp(:,:),rel(:,:),rei(:,:),res(:,:),solar,mu0
 CHARACTER(1024)::directory
 INTEGER::p,ios
 p=1;IF(phase=='SW') p=2
 IF(i/=1.OR.j/=1.OR.done(p).OR.units(p)/=0) RETURN
 CALL GET_ENVIRONMENT_VARIABLE('WRF_PORT_AUDIT_DIR',directory,status=ios)
 IF(ios/=0.OR.LEN_TRIM(directory)==0) RETURN
 OPEN(NEWUNIT=units(p),FILE=TRIM(directory)//'/'//phase//'.audit',STATUS='REPLACE',ACTION='WRITE',IOSTAT=ios)
 IF(ios/=0) STOP 'audit open failed'
 WRITE(units(p),'(a)') 'PORT_AUDIT_V2'
 WRITE(units(p),*) phase,MERGE(37,4,gp),SIZE(play,1),SIZE(play,2),icld,iceflag,inflag
 CALL rec2(p,'SOLAR_MU0',RESHAPE([solar,mu0],[1,2]))
 CALL rec2(p,'PLAY',play);CALL rec2(p,'PLEV',plev);CALL rec2(p,'TLAY',tlay);CALL rec2(p,'TLEV',tlev)
 CALL rec2(p,'H2O',h2o);CALL rec2(p,'CO2',co2);CALL rec2(p,'O3',o3);CALL rec2(p,'N2O',n2o);CALL rec2(p,'CH4',ch4);CALL rec2(p,'O2',o2)
 CALL rec2(p,'CF',cf);CALL rec2(p,'LWP',lwp);CALL rec2(p,'IWP',iwp);CALL rec2(p,'SWP',swp)
 CALL rec2(p,'REL',rel);CALL rec2(p,'REI',rei);CALL rec2(p,'RES',res)
 END SUBROUTINE
 SUBROUTINE boundary_audit_lw(i,j,tsfc,emis,c11,c12,c22,ccl4)
 INTEGER,INTENT(IN)::i,j
 REAL,INTENT(IN)::tsfc(:),emis(:,:),c11(:,:),c12(:,:),c22(:,:),ccl4(:,:)
 IF(i/=1.OR.j/=1.OR.units(1)==0)RETURN
 CALL rec2(1,'TSFC',RESHAPE(tsfc,[SIZE(tsfc),1]));CALL rec2(1,'EMIS',emis)
 CALL rec2(1,'CFC11',c11);CALL rec2(1,'CFC12',c12);CALL rec2(1,'CFC22',c22);CALL rec2(1,'CCL4',ccl4)
 END SUBROUTINE
 SUBROUTINE boundary_audit_sw(i,j,tsfc,avdir,avdif,andir,andif,adjes,dyofyr)
 INTEGER,INTENT(IN)::i,j,dyofyr
 REAL,INTENT(IN)::tsfc(:),avdir(:),avdif(:),andir(:),andif(:),adjes
 IF(i/=1.OR.j/=1.OR.units(2)==0)RETURN
 CALL rec2(2,'TSFC',RESHAPE(tsfc,[SIZE(tsfc),1]))
 CALL rec2(2,'AVDIR',RESHAPE(avdir,[SIZE(avdir),1]));CALL rec2(2,'AVDIF',RESHAPE(avdif,[SIZE(avdif),1]))
 CALL rec2(2,'ANDIR',RESHAPE(andir,[SIZE(andir),1]));CALL rec2(2,'ANDIF',RESHAPE(andif,[SIZE(andif),1]))
 CALL rec2(2,'ADJES_DYOFYR',RESHAPE([adjes,REAL(dyofyr)],[1,2]))
 END SUBROUTINE
 SUBROUTINE sampled_audit(phase,i,j,cf,lwp,iwp,swp)
 CHARACTER(*),INTENT(IN)::phase
 INTEGER,INTENT(IN)::i,j
 REAL,INTENT(IN)::cf(:,:,:),lwp(:,:,:),iwp(:,:,:),swp(:,:,:)
 INTEGER::p
 p=1;IF(phase=='SW')p=2
 IF(i/=1.OR.j/=1.OR.units(p)==0)RETURN
 CALL rec3(p,'MASK',cf);CALL rec3(p,'SAMPLED_LWP',lwp);CALL rec3(p,'SAMPLED_IWP',iwp);CALL rec3(p,'SAMPLED_SWP',swp)
 END SUBROUTINE
 SUBROUTINE end_audit(phase,i,j,up,dn,hr,upc,dnc,hrc)
 CHARACTER(*),INTENT(IN)::phase
 INTEGER,INTENT(IN)::i,j
 REAL,INTENT(IN)::up(:,:),dn(:,:),hr(:,:),upc(:,:),dnc(:,:),hrc(:,:)
 INTEGER::p
 p=1;IF(phase=='SW')p=2
 IF(i/=1.OR.j/=1.OR.units(p)==0)RETURN
 CALL rec2(p,'UP',up);CALL rec2(p,'DN',dn);CALL rec2(p,'HR',hr);CALL rec2(p,'UPC',upc);CALL rec2(p,'DNC',dnc);CALL rec2(p,'HRC',hrc)
 CLOSE(units(p));units(p)=0;done(p)=.TRUE.
 END SUBROUTINE
 SUBROUTINE rec2(p,name,x)
 INTEGER,INTENT(IN)::p
 CHARACTER(*),INTENT(IN)::name
 REAL,INTENT(IN)::x(:,:)
 INTEGER::i,k
 WRITE(units(p),*)name,2,SHAPE(x)
 DO k=1,SIZE(x,2);DO i=1,SIZE(x,1)
 WRITE(units(p),'(es25.16e3)')x(i,k)
 END DO;END DO
 END SUBROUTINE
 SUBROUTINE rec3(p,name,x)
 INTEGER,INTENT(IN)::p
 CHARACTER(*),INTENT(IN)::name
 REAL,INTENT(IN)::x(:,:,:)
 INTEGER::i,k,c
 WRITE(units(p),*)name,3,SHAPE(x)
 DO k=1,SIZE(x,3);DO c=1,SIZE(x,2);DO i=1,SIZE(x,1)
 WRITE(units(p),'(es25.16e3)')x(i,c,k)
 END DO;END DO;END DO
 END SUBROUTINE
END MODULE
'''
(out/'port_audit.f90').write_text(module)
flags=['-O2','-ftree-vectorize','-funroll-loops','-w','-ffree-form','-ffree-line-length-none','-fconvert=big-endian','-frecord-marker=4','-fallow-argument-mismatch','-fallow-invalid-boz']
includes=['dyn_em','external/esmf_time_f90','main','external/io_netcdf','external/io_int','frame','share','phys','external/rte_rrtmgp/build','wrftladj','chem','inc']
inc=['-I'+str(wrf/p) for p in includes]+['-I'+str(root.parent/'deps/netcdf/include')]
# Mod files and modified objects stay in scratch; linked production files untouched.
with (out/'compile.log').open('w') as log:
 def run(args): subprocess.run(args,cwd=out,check=True,stdout=log,stderr=subprocess.STDOUT)
 run(['gfortran',*flags,'-c','port_audit.f90'])
 for phase in ['sw','lw']:
  name=f'module_ra_rrtmg_{phase}'
  src=(wrf/'phys'/f'{name}.f90').read_text()
  use=f'   USE module_ra_rrtmgp, ONLY: rrtmgp_{phase}_column'
  assert src.count(use)==1
  src=src.replace(use,'   USE port_audit, ONLY: begin_audit, sampled_audit, end_audit, boundary_audit_lw, boundary_audit_sw\n'+use)
  solar='scon,coszen(1)' if phase=='sw' else '0.,0.'
  call=f"         CALL begin_audit('{phase.upper()}',i,j,run_rrtmgp,icld,iceflg{phase},inflg{phase},play,plev,tlay,tlev, &\n           h2ovmr,co2vmr,o3vmr,n2ovmr,ch4vmr,o2vmr,cldfrac,clwpth,ciwpth,cswpth,rel,rei,res,{solar})\n"
  if phase=='sw':call+="         CALL boundary_audit_sw(i,j,tsfc,asdir,asdif,aldir,aldif,adjes,dyofyr)\n"
  else:call+="         CALL boundary_audit_lw(i,j,tsfc,emis,cfc11vmr,cfc12vmr,cfc22vmr,ccl4vmr)\n"
  marker=f'         IF(run_rrtmgp) THEN\n           CALL rrtmgp_{phase}_column'
  assert src.count(marker)==1
  src=src.replace(marker,call+marker)
  marker=f'         call rrtmg_{phase} &'
  assert src.count(marker)==1
  src=src.replace(marker,f"         CALL sampled_audit('{phase.upper()}',i,j,cldfmcl,clwpmcl,ciwpmcl,cswpmcl)\n"+marker)
  if phase=='sw':
   marker='         if (present(sw_zbbcddir)) then'
   endcall="         CALL end_audit('SW',i,j,swuflx,swdflx,swhr,swuflxc,swdflxc,swhrc)\n"
  else:
   marker='         glw(i,j) = dflx(1,1)'
   endcall="         CALL end_audit('LW',i,j,uflx,dflx,hr,uflxc,dflxc,hrc)\n"
  assert src.count(marker)==1
  src=src.replace(marker,endcall+marker)
  (out/f'{name}.f90').write_text(src)
  run(['gfortran',*flags,*inc,'-c',f'{name}.f90','-o',f'{name}.o'])
 # Prepend two wrapper objects; archive existing module members won't be pulled twice.
 cmd=['gfortran',*flags,'-o','wrf-audit.exe',str(wrf/'main/wrf.o'),str(wrf/'main/module_wrf_top.o'),'port_audit.o','module_ra_rrtmg_lw.o','module_ra_rrtmg_sw.o',str(wrf/'main/libwrflib.a')]
 cmd += [str(wrf/p) for p in ['external/fftpack/fftpack5/libfftpack.a','external/io_grib1/libio_grib1.a','external/io_grib_share/libio_grib_share.a','external/io_int/libwrfio_int.a']]
 cmd += ['-L'+str(wrf/'external/esmf_time_f90'),'-lesmf_time',str(wrf/'frame/module_internal_header_util.o'),str(wrf/'frame/pack_utils.o'),'-L'+str(wrf/'external/io_netcdf'),'-lwrfio_nf','-L'+str(root.parent/'deps/netcdf/lib'),'-lnetcdff','-lnetcdf']
 run(cmd)
(out/'build-receipt.json').write_text(json.dumps({'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'executable_sha256':hashlib.sha256((out/'wrf-audit.exe').read_bytes()).hexdigest(),'production_executable_sha256':hashlib.sha256((wrf/'main/wrf.exe').read_bytes()).hexdigest(),'tracked_sources_modified':False},indent=2)+'\n')
print('isolated audit executable built')
