from pathlib import Path
import re,json,hashlib,shutil,difflib
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[1]
STOCK=ROOT/'build/udm37-lblrtm-stock-build-v1/attempt-1/source/LBLRTM'
SOURCE=ROOT/'build/udm37-lblrtm-reference-stage-v1/sources/LBLRTM/src/oprop.f90'
raw=SOURCE.read_text(); text=raw
assert (STOCK/'src/oprop.f90').read_bytes()==SOURCE.read_bytes()
def block(s): return '! UDM37_MIN_BEGIN\n'+s+'\n! UDM37_MIN_END\n'
def insert_before(anchor,s):
 global text
 assert text.count(anchor)==1, anchor
 text=text.replace(anchor,block(s)+anchor)
def insert_after(anchor,s):
 global text
 assert text.count(anchor)==1, anchor
 text=text.replace(anchor,anchor+block(s))
module='''MODULE udm37_min_r3
 IMPLICIT NONE
 INTEGER :: min_k=0,min_max=0,min_layer=0,min_panel=0,min_u=0,min_seq=0
 REAL*8 :: min_vft=0D0,min_dv=0D0
 REAL*8, PARAMETER :: target_nu=618.6144711111115D0
 LOGICAL :: min_active=.FALSE.
CONTAINS
 SUBROUTINE min_grid(v,d,n)
 REAL*8,INTENT(IN)::v,d
 INTEGER,INTENT(IN)::n
 INTEGER::candidate
 min_vft=v; min_dv=d; min_max=n; min_k=0
 IF(.NOT.min_active.OR.d<=0D0) RETURN
 candidate=NINT((target_nu-v)/d)+1
 IF(candidate<1.OR.candidate>n) RETURN
 IF(ABS(v+REAL(candidate-1)*d-target_nu)>1D-7) RETURN
 min_k=candidate
 END SUBROUTINE
 SUBROUTINE min_emit(tag,idx,src,line,phase,flags,values)
 CHARACTER(*),INTENT(IN)::tag
 INTEGER,INTENT(IN)::idx,src,line,phase,flags
 REAL*8,INTENT(IN)::values(:)
 IF(.NOT.min_active) RETURN
 IF(min_u==0) OPEN(NEWUNIT=min_u,FILE='UDM37_MIN_R3',STATUS='NEW',ACTION='WRITE')
 min_seq=min_seq+1
 WRITE(min_u,'(a,1x,11(i0,1x),*(es26.17e3,1x))') tag,min_seq,min_layer,min_panel, &
 min_k,min_max,idx,src,line,phase,flags,SIZE(values),min_vft,min_dv,values
 END SUBROUTINE
 SUBROUTINE min_init(layer,v,d,n,r,flags)
 INTEGER,INTENT(IN)::layer,n,flags(4)
 REAL*8,INTENT(IN)::v,d,r(*)
 CHARACTER(8)::switch
 INTEGER::envstatus
 CALL GET_ENVIRONMENT_VARIABLE('UDM37_MIN_R3_TRACE',switch,STATUS=envstatus)
 min_active=layer==21.AND.envstatus==0.AND.TRIM(switch)=='1'
 min_layer=layer; min_panel=1
 CALL min_grid(v,d,n)
 IF(.NOT.min_active) RETURN
 CALL min_emit('INIT',0,0,0,0,0,REAL(flags,8))
 CALL min_frame('INIT_STATE',r,v,d,n,0)
 END SUBROUTINE
 SUBROUTINE min_frame(tag,r,v,d,n,flag)
 CHARACTER(*),INTENT(IN)::tag
 INTEGER,INTENT(IN)::n,flag
 REAL*8,INTENT(IN)::r(*),v,d
 CALL min_grid(v,d,n)
 IF(.NOT.min_active) RETURN
 IF(min_k>0) THEN
 CALL min_emit(tag,min_k,0,0,0,flag,[r(min_k)])
 ELSE
 CALL min_emit(tag,0,0,0,0,flag,[0D0])
 ENDIF
 END SUBROUTINE
 SUBROUTINE min_write(tag,idx,src,line,phase,before,after,a,b,c,vn,sp,spp)
 CHARACTER(*),INTENT(IN)::tag
 INTEGER,INTENT(IN)::idx,src,line,phase
 REAL*8,INTENT(IN)::before,after,a,b,c,vn,sp,spp
 IF(.NOT.min_active.OR.min_k==0.OR.idx/=min_k) RETURN
 CALL min_emit(tag,idx,src,line,phase,1,[before,after,a,b,c,vn,sp,spp])
 END SUBROUTINE
 SUBROUTINE min_shift(v,d,n)
 REAL*8,INTENT(IN)::v,d
 INTEGER,INTENT(IN)::n
 min_panel=min_panel+1
 CALL min_grid(v,d,n)
 CALL min_emit('GRID_SHIFT',min_k,0,0,0,0,[target_nu])
 END SUBROUTINE
END MODULE udm37_min_r3'''
text=block(module)+text
for head in ('SUBROUTINE HIRAC1 (MPTS)\n','SUBROUTINE CNVFNV (VNU,SP,SPPSP,RECALF,R1,R2,R3,F1,F2,F3,FG,      &\n&                   XVER,ZETAI,IZETA)\n','SUBROUTINE PANEL (R1,R2,R3,KFILE,JRAD,IENTER)\n'):
 insert_after(head,' USE udm37_min_r3')
 start=text.index(head)
 pos=text.index('   IMPLICIT REAL*8           (V)\n',start)+len('   IMPLICIT REAL*8           (V)\n')
 text=text[:pos]+block(' REAL*8 :: udm37_min_before')+text[pos:]
insert_before('   V1R4ST = V1R4\n','   CALL min_init(LAYER,VFT,DVR3,MAX3,R3,[ILBLF4,IXSECT,ICNTNM,IR4])')
cn='   CALL CNVFNV (VNU,SP,SPPSP,RECALF,R1,R2,R3,F1,F2,F3,FG,XVER,ZETAI, &\n   &             IZETA)\n'
insert_before(cn,"   CALL min_frame('CN_PRE',R3,VFT,DVR3,MAX3,0)")
insert_after(cn,"   CALL min_frame('CN_POST',R3,VFT,DVR3,MAX3,0)")
insert_before('   IF (VFT.LE.0.) THEN\n',"   CALL min_frame('RSYM_GATE',R3,VFT,DVR3,MAX3,MERGE(1,0,VFT.LE.0.))")
insert_before('   IF (IXSECT.GE.1.AND.IR4.EQ.0) THEN\n',"   CALL min_frame('XSECT_GATE',R3,VFT,DVR3,MAX3,MERGE(1,0,IXSECT.GE.1.AND.IR4.EQ.0))")
insert_before('   CALL PANEL (R1,R2,R3,KFILE,JRAD,IENTER)\n',"   CALL min_frame('PANEL_PRE',R3,VFT,DVR3,MAX3,0)")
insert_before('   VFT = VFT+ REAL(NLIM1-1)*DV\n',"   CALL min_frame('SHIFT_PRE',R3,VFT,DVR3,MAX3,ISTOP)")
insert_after('   VFT = VFT+ REAL(NLIM1-1)*DV\n',"   CALL min_shift(VFT,DVR3,MAX3)")
insert_after('100   CONTINUE\n',"      CALL min_frame('SHIFT_POST',R3,VFT,DVR3,MAX3,ISTOP)")
# Direct CNVFNV mutations, preserving the original arithmetic statements.
for statement,phase,factor in [('               R3(J3) = R3(J3)+STRF3*F3(IZ3)\n',1,'1D0'),('                  R3(J3) = R3(J3)+STRF3*F3(IZ3)*ZF3L\n',2,'ZF3L')]:
 insert_before(statement,' IF(min_active.AND.min_k>0.AND.J3==min_k) udm37_min_before=R3(J3)')
 insert_after(statement,f''' IF(min_active.AND.min_k>0.AND.J3==min_k) &
 CALL min_write('CN_WRITE',J3,IZ3,I,{phase},udm37_min_before,R3(J3), &
 STRF3,F3(IZ3),{factor},VNU(I),SP(I),SPPSP(I))''')
insert_after('         R3(J-NLIM3+1) = R3(J)\n'," CALL min_write('CARRY',J-NLIM3+1,J,0,0,R3(J),R3(J-NLIM3+1),0D0,0D0,0D0,0D0,0D0,0D0)")
insert_after('         R3(J) = 0.\n'," CALL min_write('CLEAR',J,0,0,0,0D0,R3(J),0D0,0D0,0D0,0D0,0D0,0D0)")
# Private copy of XINT used only by the three R3 destination routes. Other callers and ABI remain unchanged.
xint=raw[raw.index('SUBROUTINE XINT ('):raw.index('end subroutine XINT')+len('end subroutine XINT')]
xint=xint.replace('SUBROUTINE XINT (','SUBROUTINE UDM37_MIN_XINT (',1).replace('end subroutine XINT','end subroutine UDM37_MIN_XINT')
xint=xint.replace('   IMPLICIT REAL*8           (V)\n','   USE udm37_min_r3\n   IMPLICIT REAL*8           (V)\n   REAL*8 :: udm37_min_before\n',1)
xint=xint.replace('   DO 10 I = ILO, IHI\n',"   CALL min_emit('XINT_CALL',0,0,0,0,0,[V1A,V2A,DVA,AFACT,REAL(ILO,8),REAL(IHI,8)])\n   DO 10 I = ILO, IHI\n",1)
xint=xint.replace('      R3(I) = R3(I)+CONTI*AFACT\n',"      IF(min_active.AND.min_k>0.AND.I==min_k) udm37_min_before=R3(I)\n      R3(I) = R3(I)+CONTI*AFACT\n      IF(min_active.AND.min_k>0.AND.I==min_k) &\n      CALL min_write('XINT_WRITE',I,J,0,0,udm37_min_before,R3(I),CONTI,AFACT,1D0,VI,0D0,0D0)\n")
for args in ('(V1R4,V2R4,DVR4,R4,1.0,VFT,DVR3,R3,N1R3,N2R3)','(V1ABS,V2ABS,DVABS,ABSRB,1.,VFT,DVR3,R3,N1R3,N2R3)','(V1X,V2X,DVX,RX,1.0,VFT,DVR3,R3,N1R3,N2R3)'):
 assert text.count('CALL XINT '+args)==1
 text=text.replace('CALL XINT '+args,'CALL UDM37_MIN_XINT '+args)
text+= '\n'+block(xint)
restored=re.sub(r'! UDM37_MIN_BEGIN\n.*?! UDM37_MIN_END\n','',text,flags=re.S).replace('CALL UDM37_MIN_XINT ','CALL XINT ')
assert restored.rstrip()==raw.rstrip()
# The only tolerated whitespace delta is the appended separator newline.
assert restored==raw+'\n'
stage=BASE/'stage-v2'; shutil.copytree(STOCK,stage,symlinks=True)
(stage/'src/oprop.f90').write_text(text)
(BASE/'oprop.observer-v2.f90').write_text(text)
(BASE/'observer-v2.patch').write_text(''.join(difflib.unified_diff(raw.splitlines(True),text.splitlines(True),fromfile='stock/oprop.f90',tofile='observer/oprop.f90')))
def pin(p): return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
record={'schema':'UDM37_MIN_R3_PREPARATION_V1','stock':pin(SOURCE),'candidate':pin(stage/'src/oprop.f90'),'observer_strip_restores_original_plus_separator':True,'original_arithmetic_and_XINT_public_ABI_preserved':True,'observed_layer':21,'physical_target_cm1':618.6144711111115,'selected_XINT_routes':3,'R4_requires_runtime_absence_or_defined_ancestry':True,'RSYM_requires_runtime_absence_or_extended_capture':True,'unknown_XINT_source_extent_is_not_assumed_defined':True,'first_negative_acceptance':'Only accept a prefix whose initialization and all mutations precede any unsupported source read. Full optical reference remains FAIL.','production_accepted':False}
(BASE/'preparation-v2.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
