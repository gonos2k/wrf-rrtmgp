import difflib,hashlib,json,shutil
from pathlib import Path
R=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
D=R/'build/udm37-lblrtm-r3-term-trace-v1'
P=R/'build/udm37-lblrtm-panel-trace-v1'
assert not D.exists()
D.mkdir()
shutil.copytree(P/'source/LBLRTM',D/'source/LBLRTM',symlinks=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source=D/'source/LBLRTM/src/oprop.f90'
old=source.read_text();assert sha(source)=='3479ab50b9edebeb68d6faea77d6559134b2f778343a3bca53d9e73c3a87c37b'
s=old;edits=[]
def replace(a,b):
 global s
 assert s.count(a)==1,(a[:80],s.count(a))
 s=s.replace(a,b);edits.append((a,b))
def snap(stage):
 return f'   CALL udm37_r3_snapshot({stage},R3,ICNTNM,ILBLF4,IXSECT,IR4)\n'
replace('70 CONTINUE\n!\n   CALL CNVFNV', '70 CONTINUE\n!\n'+snap(110)+'   CALL CNVFNV')
replace('   &             IZETA)\n!\n   IF (IPANEL.EQ.0)', '   &             IZETA)\n'+snap(111)+'!\n   IF (IPANEL.EQ.0)')
replace('   IF (IXSECT.GE.1.AND.IR4.EQ.0) THEN\n',snap(120)+'   IF (IXSECT.GE.1.AND.IR4.EQ.0) THEN\n')
replace('      TXS = TXS+TIME-TIME0\n   ENDIF\n!\n   CALL CPUTIM(TPAT0)\n   IF (ILBLF4.GE.1)', '      TXS = TXS+TIME-TIME0\n   ENDIF\n'+snap(121)+'!\n   CALL CPUTIM(TPAT0)\n'+snap(122)+'   IF (ILBLF4.GE.1)')
replace('   &    CALL XINT (V1R4,V2R4,DVR4,R4,1.0,VFT,DVR3,R3,N1R3,N2R3)\n\n', '   &    CALL XINT (V1R4,V2R4,DVR4,R4,1.0,VFT,DVR3,R3,N1R3,N2R3)\n'+snap(123)+snap(124)+'\n')
replace('   &    CALL XINT (V1ABS,V2ABS,DVABS,ABSRB,1.,VFT,DVR3,R3,N1R3,N2R3)\n', '   &    CALL XINT (V1ABS,V2ABS,DVABS,ABSRB,1.,VFT,DVR3,R3,N1R3,N2R3)\n'+snap(125))
replace('   CALL PANEL (R1,R2,R3,KFILE,JRAD,IENTER)\n',snap(126)+'   CALL PANEL (R1,R2,R3,KFILE,JRAD,IENTER)\n'+snap(127))
replace('      SPPSP(I) = SPPI/SP(I)\n', '      SPPSP(I) = SPPI/SP(I)\n      IF (LAYER.EQ.21) CALL udm37_line_store(NLNCR,I,M,ISO,IFLAG,IZ, &\n         SUI,GI,YI,PAVP0,PAVP2,ALFL,ZETA,VNU(I))\n')
start=s.index('SUBROUTINE CNVFNV (');end=s.index('end subroutine CNVFNV',start)
sub=s[start:end]
assert sub.count('   DIMENSION FG(*),XVER(*)\n')==1
subnew=sub.replace('   DIMENSION FG(*),XVER(*)\n','   DIMENSION FG(*),XVER(*)\n   REAL udm37_before_r3\n')
edits.append((sub,subnew));s=s[:start]+subnew+s[end:]
replace('               R3(J3) = R3(J3)+STRF3*F3(IZ3)\n',
 '               IF (LAYER.EQ.21) udm37_before_r3=R3(J3)\n'
 '               R3(J3) = R3(J3)+STRF3*F3(IZ3)\n'
 '               IF (LAYER.EQ.21) CALL udm37_r3_term(1,I,J1,J3,IZ3, &\n'
 '                  J3SHFT,JMIN1,JMAX1,VNU(I),SP(I),SPPSP(I),RECALF(I), &\n'
 '                  STRF3,F3(IZ3),1.0,udm37_before_r3,R3(J3),ZSLOPE,ZINT,CONF3)\n')
replace('                  R3(J3) = R3(J3)+STRF3*F3(IZ3)*ZF3L\n',
 '                  IF (LAYER.EQ.21) udm37_before_r3=R3(J3)\n'
 '                  R3(J3) = R3(J3)+STRF3*F3(IZ3)*ZF3L\n'
 '                  IF (LAYER.EQ.21) CALL udm37_r3_term(2,I,J1,J3,IZ3, &\n'
 '                     J3SHFT,JMIN1,JMAX1,VNU(I),SP(I),SPPSP(I),RECALF(I), &\n'
 '                     STRF3,F3(IZ3),ZF3L,udm37_before_r3,R3(J3),ZSLOPE,ZINT,CONF3)\n')
helper='''

! Observational diagnostics only. Separate diagnostic COMMONs never alias physics.
SUBROUTINE udm37_line_store(batch,i,m,iso,flag,iz,sui,gi,yi,p0,p2,alfl,zeta,vnu)
   IMPLICIT NONE
   INTEGER, INTENT(IN) :: batch,i,m,iso,flag,iz
   REAL, INTENT(IN) :: sui,gi,yi,p0,p2,alfl,zeta
   REAL*8, INTENT(IN) :: vnu
   INTEGER udm37_mi(5,250)
   REAL*8 udm37_mr(8,250)
   COMMON /UDM37_META_I/ udm37_mi
   COMMON /UDM37_META_R/ udm37_mr
   IF(i<1.OR.i>250) STOP 'UDM37 diagnostic metadata index'
   udm37_mi(:,i)=[batch,m,iso,flag,iz]
   udm37_mr(:,i)=[REAL(sui,8),REAL(gi,8),REAL(yi,8),REAL(p0,8), &
      REAL(p2,8),REAL(alfl,8),REAL(zeta,8),vnu]
END SUBROUTINE udm37_line_store

INTEGER FUNCTION udm37_term_unit()
   IMPLICIT NONE
   INTEGER, SAVE :: u=0
   IF(u==0) OPEN(NEWUNIT=u,FILE='UDM37_R3_TERM_TRACE', &
      FORM='UNFORMATTED',STATUS='NEW',ACTION='WRITE')
   udm37_term_unit=u
END FUNCTION udm37_term_unit

INTEGER FUNCTION udm37_term_seq()
   IMPLICIT NONE
   INTEGER, SAVE :: n=0
   n=n+1
   udm37_term_seq=n
END FUNCTION udm37_term_seq

SUBROUTINE udm37_r3_term(stage,i,j1,j3,iz3,j3shft,jmin1,jmax1, &
   vn,sp,sppsp,rec,str,f,z,before,after,zslope,zint,conf3)
   IMPLICIT REAL*8 (V)
   INTEGER, INTENT(IN) :: stage,i,j1,j3,iz3,j3shft,jmin1,jmax1
   REAL*8, INTENT(IN) :: vn
   REAL, INTENT(IN) :: sp,sppsp,rec,str,f,z,before,after,zslope,zint,conf3
   CHARACTER*8 XID,HMOLID,YID
   REAL*8 SECANT,XALTZ
   COMMON /FILHDR/ XID(10),SECANT,PAVE,TAVE,HMOLID(60),XALTZ(4), &
      WK(60),PZL,PZU,TZL,TZU,WBROAD,DV,V1,V2,TBOUND, &
      EMISIV,FSCDID(17),NMOL,LAYER,YI1,YID(10),LSTWDF
   COMMON /XSUB/ VBOT,VTOP,VFT,LIMIN,ILO,IHI,IEOF,IPANEL,ISTOP,IDATA
   COMMON /SUB1/ MAX1,MAX2,MAX3,NLIM1,NLIM2,NLIM3,NLO,NHI,DVR2,DVR3, &
      N1R1,N2R1,N1R2,N2R2,N1R3,N2R3
   INTEGER udm37_mi(5,250),u,q,udm37_term_unit,udm37_term_seq
   REAL*8 udm37_mr(8,250),nu
   COMMON /UDM37_META_I/ udm37_mi
   COMMON /UDM37_META_R/ udm37_mr
   IF(LAYER/=21) RETURN
   nu=VFT+REAL(j3-1)*DVR3
   IF(nu<666.1_8.OR.nu>666.7_8) RETURN
   IF(i<1.OR.i>250) STOP 'UDM37 diagnostic trace index'
   IF(udm37_mr(8,i)/=vn) STOP 'UDM37 diagnostic stale metadata'
   u=udm37_term_unit();q=udm37_term_seq()
   WRITE(u) 'UDMR3T1 ',q,stage,LAYER,udm37_mi(1,i),i,j1,j3, &
      udm37_mi(2:5,i),iz3,j3shft,jmin1,jmax1, &
      VFT,DVR3,vn,sp,sppsp,rec,str,f,z,before,after,zslope,zint,conf3, &
      udm37_mr(:,i)
END SUBROUTINE udm37_r3_term

SUBROUTINE udm37_r3_snapshot(stage,r3,icntnm,ilblf4,ixsect,ir4)
   IMPLICIT REAL*8 (V)
   INTEGER, INTENT(IN) :: stage,icntnm,ilblf4,ixsect,ir4
   REAL, INTENT(IN) :: r3(*)
   CHARACTER*8 XID,HMOLID,YID
   REAL*8 SECANT,XALTZ
   COMMON /FILHDR/ XID(10),SECANT,PAVE,TAVE,HMOLID(60),XALTZ(4), &
      WK(60),PZL,PZU,TZL,TZU,WBROAD,DV,V1,V2,TBOUND, &
      EMISIV,FSCDID(17),NMOL,LAYER,YI1,YID(10),LSTWDF
   COMMON /XSUB/ VBOT,VTOP,VFT,LIMIN,ILO,IHI,IEOF,IPANEL,ISTOP,IDATA
   COMMON /SUB1/ MAX1,MAX2,MAX3,NLIM1,NLIM2,NLIM3,NLO,NHI,DVR2,DVR3, &
      N1R1,N2R1,N1R2,N2R2,N1R3,N2R3
   COMMON /XPANEL/ V1P,V2P,DVP,NLIM,RMIN,RMAX,NPNLXP,NSHIFT,NPTS
   INTEGER u,q,udm37_term_unit,udm37_term_seq
   IF(LAYER/=21) RETURN
   IF(VFT>666.7_8.OR.VFT+REAL(MAX3-1)*DVR3<666.1_8) RETURN
   u=udm37_term_unit();q=udm37_term_seq()
   WRITE(u) 'UDMR3S1 ',q,stage,LAYER,MAX3,NLIM1,NLIM3,ILO,IHI,IPANEL, &
      ISTOP,N1R3,N2R3,NLO,NHI,NSHIFT,icntnm,ilblf4,ixsect,ir4, &
      VFT,DV,DVR3,PAVE,TAVE
   WRITE(u) r3(1:MAX3)
   FLUSH(u)
END SUBROUTINE udm37_r3_snapshot
'''
s+=helper
source.write_text(s)
restored=s[:-len(helper)]
for a,b in reversed(edits):
 assert restored.count(b)==1,b[:80]
 restored=restored.replace(b,a)
assert restored==old
patch=''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='panel-diagnostic/src/oprop.f90',tofile='r3-term-diagnostic/src/oprop.f90'))
(D/'instrumentation.patch').write_text(patch)
changed=[];count=0
for f in (P/'source/LBLRTM').rglob('*'):
 if f.is_file() and not f.is_symlink():
  count+=1
  g=D/'source/LBLRTM'/f.relative_to(P/'source/LBLRTM')
  if sha(f)!=sha(g):changed.append(str(f.relative_to(P/'source/LBLRTM')))
assert changed==['src/oprop.f90'],changed
plan=json.loads((P/'build-plan.json').read_text())
plan.update({'schema':'UDM37_LBLRTM_R3_TERM_TRACE_PLAN_V1','status':'PREPARED_NOT_COMPILED_NOT_RUN','parent_source_path':str(P/'source/LBLRTM/src/oprop.f90'),'parent_source_sha256':sha(P/'source/LBLRTM/src/oprop.f90'),'source_trace_path':str(source),'source_trace_sha256':sha(source),'patch_sha256':sha(D/'instrumentation.patch'),'build_cwd':str(D/'source/LBLRTM/build'),'solver_invocations_planned_max':1,'cases':['original_coupling_SAMPLE4'],'only_source_edit':'oprop.f90 observational OPDPTH/CNVFNV/LNCOR1 hooks plus separate diagnostic-only helpers; inherited PANEL hooks remain','trace_window_cm_1':[666.1,666.7],'trace_layer':21,'metadata':'NLNCR+record index+molecule/isotope/flag; corrected SUI/GI/YI/SP/PAVP2 and broadening/shape operands; includes wings with centers outside window','snapshot_stages':{'110':'before each CNVFNV','111':'after each CNVFNV','120':'before optional XSECTM','121':'after optional XSECTM','122':'before optional LBLF4 XINT','123':'after optional LBLF4 XINT','124':'before optional continuum XINT','125':'after optional continuum XINT','126':'before PANEL','127':'after PANEL carry and origin advance'},'term_stages':{'1':'baseline STRF3*F3','2':'coupling STRF3*F3*ZF3L'},'record_layout':{'marker_bytes':4,'integer_bytes':8,'real_bytes':8,'snapshot_header':'8char+19int+5real, then one R3-array record','term_record':'8char+15int+22real'},'restoration_to_parent_exact':True,'copied_regular_files':count,'no_original_arithmetic_or_assignments_changed':True,'physical_acceptance':'FAIL_NEGATIVE_OD_RETAINED','original_stock_source_and_binary_unchanged':True})
obj=D/'source/LBLRTM/build/lblrtm_v12.17_linux_gnu_dbl.obj'
plan['copied_objects_before']=[{'file':p.name,'sha256':sha(p),'size_bytes':p.stat().st_size} for p in sorted(obj.glob('*.o'))]
(D/'build-plan.json').write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n')
(D/'copy-readback.json').write_text(json.dumps({'regular_files':count,'changed':changed,'restoration_to_parent_exact':True,'source_only_no_execution':True},indent=2)+'\n')
print('Prepared',sha(source),sha(D/'instrumentation.patch'),count,'files; zero build/solver')
