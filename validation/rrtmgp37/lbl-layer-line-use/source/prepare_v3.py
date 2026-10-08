from pathlib import Path
import re, hashlib, json, shutil, difflib
BASE=Path(__file__).resolve().parent; ROOT=BASE.parents[1]
parent=ROOT/'build/udm37-final-composition-v1/oprop.observer-v2.f90'
old=parent.read_text(); s=old
def block(t): return '! UDM37_USE_BEGIN\n'+t.rstrip()+'\n! UDM37_USE_END\n'
def add(anchor,t,after=False):
 global s
 section=s
 start=0
 if anchor not in ('SUBROUTINE RDLIN\n','SUBROUTINE LNCOR1 (NLNCR,IHI,ILO,MEFDP)\n') and ('I = IOUT' in anchor or 'SPPSP(I) = SPPI' in anchor or '.eq.0.) THEN' in anchor or 'ALFV.LT.DV' in anchor):
  start=s.index('SUBROUTINE LNCOR1 ('); end=s.index('end subroutine LNCOR1',start)
  section=s[start:end]
 if section.count(anchor)!=1: raise ValueError((anchor,section.count(anchor)))
 at=start+section.index(anchor)
 s=s[:at]+(anchor+block(t) if after else block(t)+anchor)+s[at+len(anchor):]
module='''MODULE udm37_layer_use
 USE udm37_min_r3, ONLY:min_active,min_panel,target_nu,min_k
 USE udm37_line_coeff, ONLY:ln_block,ln_record
 IMPLICIT NONE
 INTEGER :: use_u=0,use_seq=0,use_id=0,use_ids(250)=0,use_mol(250)=0,use_flag(250)=0
 INTEGER :: use_reason=0,use_stage=0
 REAL*8 :: use_nu(250)=0D0,use_raw_width=0D0
CONTAINS
 LOGICAL FUNCTION use_selected(i)
 INTEGER,INTENT(IN)::i
 use_selected=min_active.AND.(min_panel==13.OR.min_panel==14).AND.ABS(use_nu(i)-target_nu)<=25D0.AND.use_flag(i)>=0
 END FUNCTION
 SUBROUTINE use_emit(tag,i,v)
 CHARACTER(*),INTENT(IN)::tag
 INTEGER,INTENT(IN)::i
 REAL*8,INTENT(IN)::v(:)
 IF(.NOT.use_selected(i)) RETURN
 IF(use_u==0) OPEN(NEWUNIT=use_u,FILE='UDM37_LAYER_USE',STATUS='REPLACE',ACTION='WRITE')
 use_seq=use_seq+1
 WRITE(use_u,'(A,9(1X,I0),*(1X,ES26.17E3))') tag,use_seq,use_ids(i),ln_block,ln_record, &
 i,use_mol(i),use_flag(i),min_panel,SIZE(v),v
 FLUSH(use_u)
 END SUBROUTINE
 SUBROUTINE use_entry(i,v)
 INTEGER,INTENT(IN)::i
 REAL*8,INTENT(IN)::v(:)
 use_reason=0;use_stage=0;use_ids(i)=0
 IF(.NOT.use_selected(i)) RETURN
 use_id=use_id+1;use_ids(i)=use_id
 CALL use_emit('ENTRY',i,v)
 END SUBROUTINE
 SUBROUTINE use_write(i,phase,idx,lookup,before,after,strf,factor,zfactor)
 INTEGER,INTENT(IN)::i,phase,idx,lookup
 REAL*8,INTENT(IN)::before,after,strf,factor,zfactor
 IF(.NOT.min_active.OR.min_k<=0.OR.idx/=min_k) RETURN
 IF(.NOT.use_selected(i).OR.use_ids(i)<=0) STOP 'Uncaptured R3 target contributor'
 CALL use_emit('WRITE',i,[REAL(phase,8),REAL(idx,8),REAL(lookup,8),before,after,strf,factor,zfactor])
 END SUBROUTINE
END MODULE udm37_layer_use
'''
add('SUBROUTINE HIRAC1 (MPTS)\n',module)
add('SUBROUTINE RDLIN\n',' USE udm37_layer_use',after=True)
add('   do 15 i=1,rdlnpnl%nrec\n',''' IF(min_active) THEN
 DO i=1,rdlnpnl%nrec
 use_nu(i)=rdlnbuf%vnu(i);use_mol(i)=rdlnbuf%mol(i);use_flag(i)=rdlnbuf%iflg(i)
 ENDDO
 ENDIF''')
add('SUBROUTINE LNCOR1 (NLNCR,IHI,ILO,MEFDP)\n',' USE udm37_layer_use',after=True)
add('      I = IOUT(J)\n','''      CALL use_entry(I,[use_nu(I),VNU(I),S(I),DV,ALFMAX,HWF3,VFT,VBOT,VTOP, &
 REAL(ILNFLG,8),DVR4,DPTMN,DPTFC,REAL(JRAD,8),TAVE,PAVE])''',after=True)
add('         call line_exception (1,ipr,h_lncor1,m,nmol,iso,iso_max)\n',' use_reason=1')
add('         call line_exception (2,ipr,h_lncor1,m,nmol,iso,iso_max)\n',' use_reason=2')
add('      IF (SUI.EQ.0.) GO TO 25\n',' IF(SUI.EQ.0.) use_reason=3')
add('      IF (ALFV.LT.DV) THEN\n',' use_raw_width=ALFV')
add('      IF (HWF3*ALFV+VNU(I) .LT. VFT) GO TO 25\n',''' use_stage=1
 CALL use_emit('WIDTH',I,[VNU(I),use_raw_width,ALFV,DV,ALFMAX,REAL(NMINAD,8), &
 REAL(NPLSAD,8),ALFL,ALFAD,ZETA,FZETA,REAL(IZ,8),ZETDIF,AVRAT(IZ),AVRAT(IZ+1), &
 HWF3,VFT,target_nu,REAL(IBRD,8)])
 IF(HWF3*ALFV+VNU(I).LT.VFT) use_reason=4''')
add('      SPPSP(I) = SPPI/SP(I)\n',''' use_stage=2
 CALL use_emit('COEFFICIENT',I,[SP(I),SPPI,SPPSP(I),RECALF(I),YI,GI])''',after=True)
add('            SPEAK = SUI*RECALF(I)\n',''' CALL use_emit('PEAK',I,[SPEAK,DPTMN,DPTFC,DVR4,SUI,RECALF(I)])''',after=True)
add('               IF (SPEAK.LE.DPTMN) THEN\n',' use_reason=5',after=True)
add('                  .eq.0.) THEN\n',' use_reason=6',after=True)
add('            IF (FREJ(J).EQ.HREJ) GO TO 25\n',' IF(FREJ(J).EQ.HREJ) use_reason=7')
add('      GO TO 30\n!\n25    SP(I) = 0.\n',' CALL use_emit("OUTCOME",I,[0D0,REAL(use_stage,8),SP(I),SPPSP(I)])')
add('      SPPSP(I) = 0.\n!\n30 END DO\n',' CALL use_emit("OUTCOME",I,[REAL(use_reason,8),REAL(use_stage,8),SP(I),SPPSP(I)])')
add('&                   XVER,ZETAI,IZETA)\n',' USE udm37_layer_use',after=True)
add(' CALL min_write(\'CN_WRITE\',J3,IZ3,I,1,udm37_min_before,R3(J3), &\n STRF3,F3(IZ3),1D0,VNU(I),SP(I),SPPSP(I))\n',
 ''' IF(min_active.AND.min_k>0.AND.J3==min_k) &
 CALL use_write(I,1,J3,IZ3,udm37_min_before,R3(J3),STRF3,F3(IZ3),1D0)''',after=True)
add(' CALL min_write(\'CN_WRITE\',J3,IZ3,I,2,udm37_min_before,R3(J3), &\n STRF3,F3(IZ3),ZF3L,VNU(I),SP(I),SPPSP(I))\n',
 ''' IF(min_active.AND.min_k>0.AND.J3==min_k) &
 CALL use_write(I,2,J3,IZ3,udm37_min_before,R3(J3),STRF3,F3(IZ3),ZF3L)''',after=True)
stripped=re.sub(r'! UDM37_USE_BEGIN\n.*?! UDM37_USE_END\n','',s,flags=re.S)
if stripped!=old: raise ValueError('parent restoration')
(BASE/'oprop.observer.f90').write_text(s)
(BASE/'observer.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='PR162/oprop.observer-v2.f90',tofile='layer-use/oprop.observer.f90')))
stage=BASE/'stage-v3';shutil.copytree(ROOT/'build/udm37-final-composition-v1/stage-v2',stage,symlinks=True)
shutil.copyfile(BASE/'oprop.observer.f90',stage/'src/oprop.f90')
(BASE/'preparation.json').write_text(json.dumps({'parent_sha256':hashlib.sha256(parent.read_bytes()).hexdigest(),'new_source_sha256':hashlib.sha256(s.encode()).hexdigest(),'strip_new_blocks_restores_parent_bytes':True,'width_window_cm1':25,'layer':21,'target_cm1':618.6144711111115,'production_changed':False},indent=2)+'\n')
print('Prepared observer; new block removal restores PR162 bytes')
