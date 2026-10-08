from pathlib import Path
import re,hashlib,json,shutil,difflib
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
parent=ROOT/'build/udm37-coupling-generation-v1/oprop.observer-v2.f90'
raw=parent.read_text();text=raw
stock=ROOT/'build/udm37-lblrtm-stock-build-v1/attempt-1/source/LBLRTM'
def block(s):return '! UDM37_FINAL_BEGIN\n'+s+'\n! UDM37_FINAL_END\n'
module='''MODULE udm37_final_od
 USE udm37_min_r3, ONLY: min_active,min_panel,min_layer
 IMPLICIT NONE
 INTEGER :: final_u=0,final_seq=0
CONTAINS
 LOGICAL FUNCTION final_active()
 final_active=min_active.AND.min_layer==21.AND.min_panel==14
 END FUNCTION
 SUBROUTINE final_emit(tag,v)
 CHARACTER(*),INTENT(IN)::tag
 REAL*8,INTENT(IN)::v(:)
 IF(.NOT.final_active()) RETURN
 IF(final_u==0) OPEN(NEWUNIT=final_u,FILE='UDM37_FINAL_OD',STATUS='NEW',ACTION='WRITE')
 final_seq=final_seq+1
 WRITE(final_u,'(a,1x,4(i0,1x),*(es26.17e3,1x))') tag,final_seq,min_layer,min_panel,SIZE(v),v
 END SUBROUTINE
 SUBROUTINE final_frame(tag,r1,r2,r3,v,d,d2,d3)
 CHARACTER(*),INTENT(IN)::tag
 REAL*8,INTENT(IN)::r1(*),r2(*),r3(*),v,d,d2,d3
 IF(.NOT.final_active()) RETURN
 CALL final_emit(tag,[v,d,d2,d3,r1(289:324),r2(72:84),r3(17:24)])
 END SUBROUTINE
END MODULE udm37_final_od'''
# Add after existing modules, before first standalone source unit.
pos=text.index('SUBROUTINE HIRAC1 (MPTS)');text=text[:pos]+block(module)+text[pos:]
def region(name,fn):
 global text
 a=text.index('SUBROUTINE '+name+' (');b=text.index('end subroutine '+name,a)+len('end subroutine '+name)
 text=text[:a]+fn(text[a:b])+text[b:]
def after(s,a,b):
 assert s.count(a)==1,(a,s.count(a));return s.replace(a,a+block(b))
def before(s,a,b):
 assert s.count(a)==1,(a,s.count(a));return s.replace(a,block(b)+a)
def hir(s):
 s=after(s,'SUBROUTINE HIRAC1 (MPTS)\n',' USE udm37_final_od')
 s=before(s,'   CALL CPUTIM(TPAT0)\n   IF (ILBLF4.GE.1)'," CALL final_frame('PRE_EXTRA',R1,R2,R3,VFT,DV,DVR2,DVR3)\n CALL final_emit('EXTRA_FLAGS',REAL([ILBLF4,IXSECT,ICNTNM,IR4,N1R1,N2R1,N1R2,N2R2,N1R3,N2R3],8))")
 s=after(s,'   TXINT = TXINT + TPAT1-TPAT0\n'," CALL final_frame('POST_EXTRA',R1,R2,R3,VFT,DV,DVR2,DVR3)")
 return s
region('HIRAC1',hir)
def panel(s):
 s=after(s,'SUBROUTINE PANEL (R1,R2,R3,KFILE,JRAD,IENTER)\n',' USE udm37_final_od')
 s=after(s,'   IMPLICIT REAL*8           (V)\n',' REAL*8 :: final_before')
 s=before(s,'   DO 10 J = LIMLO, LIMHI, 4\n'," CALL final_frame('PRE_PANEL',R1,R2,R3,VFT,DV,DVR2,DVR3)\n CALL final_emit('PANEL_META',[REAL(NLO,8),REAL(NHI,8),REAL(LIMLO,8),REAL(LIMHI,8), &\n REAL(ISTOP,8),REAL(JRAD,8),DVOUT,V1P,V2P,DVP,REAL(NLIM,8)])")
 s=before(s,'   DO 20 J = NLO, NHI, 4\n'," CALL final_frame('POST_R2',R1,R2,R3,VFT,DV,DVR2,DVR3)")
 s=after(s,'20 END DO\n'," CALL final_frame('POST_R1',R1,R2,R3,VFT,DV,DVR2,DVR3)")
 s=before(s,'         R1(I) = R1(I)*RADVI\n'," IF(final_active().AND.I>=289.AND.I<=324) final_before=R1(I)")
 s=after(s,'         R1(I) = R1(I)*RADVI\n'," IF(final_active().AND.I>=289.AND.I<=324) &\n CALL final_emit('RAD_MULT',[REAL(I,8),VFT+REAL(I-1)*DV,final_before,RADVI,R1(I),XKT])")
 s=before(s,'   IF (DVOUT.EQ.0.) THEN\n'," CALL final_frame('PRE_OUTPUT',R1,R2,R3,VFT,DV,DVR2,DVR3)")
 return s
region('PANEL',panel)
restored=re.sub(r'! UDM37_FINAL_BEGIN\n.*?! UDM37_FINAL_END\n','',text,flags=re.S)
assert restored==raw,'exact PR161 restoration'
stage=BASE/'stage';shutil.copytree(stock,stage,symlinks=True)
(stage/'src/oprop.f90').write_text(text);(BASE/'oprop.observer.f90').write_text(text)
(BASE/'observer.patch').write_text(''.join(difflib.unified_diff(raw.splitlines(True),text.splitlines(True),fromfile='pr161/oprop.f90',tofile='final/oprop.f90')))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
(BASE/'preparation.json').write_text(json.dumps({'parent_sha256':sha(parent),'source_sha256':sha(stage/'src/oprop.f90'),'exact_parent_restoration':True,'original_arithmetic_unchanged':True,'selected_layer':21,'selected_panel':14,'ranges':{'R1':[289,324],'R2':[72,84],'R3':[17,24]},'production_accepted':False},indent=2)+'\n')
print('Prepared observer, exact parent restoration')
