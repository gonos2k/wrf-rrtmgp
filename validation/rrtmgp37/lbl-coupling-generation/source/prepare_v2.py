from pathlib import Path
import re,json,hashlib,shutil,difflib
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
PREV=ROOT/'build/udm37-minimal-r3-observation-v1';stock=ROOT/'build/udm37-lblrtm-stock-build-v1/attempt-1/source/LBLRTM'
raw=(PREV/'oprop.observer-v2.f90').read_text();text=raw
def block(s):return '! UDM37_COEFF_BEGIN\n'+s+'\n! UDM37_COEFF_END\n'
module='''MODULE udm37_line_coeff
 USE udm37_min_r3, ONLY: min_active,min_panel
 IMPLICIT NONE
 INTEGER :: ln_u=0,ln_seq=0,ln_block=0,ln_first_data=3,ln_record=0
 LOGICAL :: ln_selected(250)=.FALSE.
CONTAINS
 SUBROUTINE ln_emit(tag,slot,mol,iso,v)
 CHARACTER(*),INTENT(IN)::tag
 INTEGER,INTENT(IN)::slot,mol,iso
 REAL*8,INTENT(IN)::v(:)
 IF(.NOT.min_active) RETURN
 IF(ln_u==0) OPEN(NEWUNIT=ln_u,FILE='UDM37_LINE_COEFF',STATUS='NEW',ACTION='WRITE')
 ln_seq=ln_seq+1
 WRITE(ln_u,'(a,1x,8(i0,1x),*(es26.17e3,1x))') &
 tag,ln_seq,ln_block,ln_record,slot,mol,iso,min_panel,SIZE(v),v
 END SUBROUTINE
END MODULE udm37_line_coeff'''
text=block(module)+text
# Dependency module must precede line logger.
start=text.index('! UDM37_MIN_BEGIN\nMODULE udm37_min_r3');end=text.index('! UDM37_MIN_END\n',start)+len('! UDM37_MIN_END\n');minmodule=text[start:end];text=text[:start]+text[end:];text=minmodule+text

def edit_region(name,func):
 global text
 start=text.index('SUBROUTINE '+name+' ');end=text.index('end subroutine '+name,start)+len('end subroutine '+name)
 section=text[start:end];new=func(section);text=text[:start]+new+text[end:]
def after(s,a,b):
 assert s.count(a)==1,(a,s.count(a));return s.replace(a,a+block(b))
def before(s,a,b):
 assert s.count(a)==1,(a,s.count(a));return s.replace(a,block(b)+a)
def rd(s):
 s=after(s,'SUBROUTINE RDLIN\n',' USE udm37_line_coeff') if False else s
 # RDLIN has no parenthesis, USE follows header directly.
 s=s.replace('SUBROUTINE RDLIN\n','SUBROUTINE RDLIN\n'+block(' USE udm37_line_coeff'),1)
 s=after(s,'      read (lnfl) HLINID\n',"      ln_block=0; ln_first_data=3; ln_selected=.FALSE.\n      IF(HLINID(7)(8:8)=='^') ln_first_data=4")
 s=after(s,'10 CALL BUFIN_sgl(Lnfl,LEOF,rdlnpnl,npnlhd)\n',' IF(LEOF/=0) THEN\n ln_block=ln_block+1; ln_record=ln_first_data+2*(ln_block-1)\n ENDIF')
 s=before(s,'   do 15 i=1,rdlnpnl%nrec\n',' ln_selected=.FALSE.\n DO i=1,rdlnpnl%nrec\n IF(ABS(rdlnbuf%vnu(i)-618.023668D0)<1D-12.AND.rdlnbuf%mol(i)==102.AND.rdlnbuf%iflg(i)==1) THEN\n ln_selected(i)=.TRUE.\n CALL ln_emit(\'RAW_LINE\',i,2,1,[rdlnbuf%vnu(i),REAL(rdlnbuf%sp(i),8), &\n REAL(rdlnbuf%alfa(i),8),REAL(rdlnbuf%epp(i),8),REAL(rdlnbuf%hwhm(i),8), &\n REAL(rdlnbuf%tmpalf(i),8),REAL(rdlnbuf%pshift(i),8),REAL(rdlnbuf%iflg(i),8), &\n REAL(rdlnbuf%mol(i),8),REAL(rdlnbuf%brd_mol_flg_in(:,i),8), &\n REAL(rdlnbuf%brd_mol_dat(:,i),8),REAL(rdlnbuf%speed_dep(i),8)])\n ENDIF\n ENDDO')
 s=after(s,'15 continue\n'," DO i=1,rdlnpnl%nrec-1\n IF(ln_selected(i)) CALL ln_emit('RAW_COUPLING',i+1,2,1,[VNU(i+1),SP(i+1),ALFA0(i+1),EPP(i+1), &\n AMOL(i+1),HWHMS(i+1),TMPALF(i+1),PSHIFT(i+1),REAL(IFLG(i+1),8)])\n ENDDO")
 return s
# Manual region for no-argument RDLIN.
a=text.index('SUBROUTINE RDLIN\n');b=text.index('end subroutine RDLIN',a)+len('end subroutine RDLIN');text=text[:a]+rd(text[a:b])+text[b:]

def lnc(s):
 s=after(s,'SUBROUTINE LNCOR1 (NLNCR,IHI,ILO,MEFDP)\n',' USE udm37_line_coeff')
 s=after(s,'   IMPLICIT REAL*8           (V)\n',' REAL*8 :: ln_weight')
 s=after(s,'      MOL(I) = M\n'," IF(ln_selected(I)) THEN\n ln_weight=WK(M)\n IF(ISOTPL_FLAG(M,ISO)/=0) ln_weight=WKI(M,ISO)\n CALL ln_emit('LNC_PRE',I,M,ISO,[VNU(I),S(I),ALFA0(I),EPP(I),HWHMS(I),TMPALF(I),PSHIFT(I), &\n TAVE,TEMP0,PAVE,P0,XKT,RHOSLF(M),RHORAT,TRATIO,PAVP0,PAVP2,BETACR, &\n SCOR(M,ISO),ALFD1(M,ISO),ln_weight,REAL(ISOTPL_FLAG(M,ISO),8),REAL(JRAD,8),RADCN2,ALFMAX,DV,REAL(IBRD,8)])\n ENDIF")
 s=after(s,'      SPPSP(I) = SPPI/SP(I)\n'," IF(ln_selected(I).AND.IFLAG==1) CALL ln_emit('LNC_POST',I,M,ISO,[YI,GI,SUI,SPPI,SP(I), &\n SPPSP(I),RECALF(I),ZETA,REAL(IZETA(I),8),FZETA,ZETDIF,ALFL,ALFAD,ALFV,TMPCOR, &\n ALFA0I,HWHMSI,VNU(I),REAL(ILC,8),RECTLC,TMPDIF,A,B,AVRAT(IZ),AVRAT(IZ+1), &\n REAL(NMINAD,8),REAL(NPLSAD,8),REAL(SUM(brd_mol_flg(:,I)),8),SLOPEA,SLOPEB])")
 return s
edit_region('LNCOR1',lnc)
def cn(s):
 s=s.replace(' USE udm37_min_r3\n',' USE udm37_min_r3\n USE udm37_line_coeff\n',1) # within existing observer block
 s=s.replace(' REAL*8 :: udm37_min_before\n',' REAL*8 :: udm37_min_before\n'+block(' REAL*8 :: ln_base'),1)
 s=after(s,'            STRF3 = DEPTHI*(CF3(IZM)+ZETDIF*(CF3(IZM+1)-CF3(IZM)))\n',' IF(ln_selected(I)) ln_base=STRF3')
 s=before(s,'                  R3(J3) = R3(J3)+STRF3*F3(IZ3)*ZF3L\n'," IF(min_active.AND.ln_selected(I).AND.min_k>0.AND.J3==min_k) &\n CALL ln_emit('CN_GEN',I,2,1,[SP(I),RECALF(I),DEPTHI,REAL(IZM,8),ZETAI(I),ZETDIF, &\n CF3(IZM),CF3(IZM+1),ln_base,CLC3,DPTRAT,STRF3,VNU(I),ZSLOPE,WAVDXF,ZINT,CONF3, &\n REAL(JMIN1,8),REAL(JMAX1,8),REAL(J3SHFT,8),REAL(JMIN3,8),HWDXF,ZF3L,REAL(IZ3,8),F3(IZ3), &\n HWF1,DXF1,REAL(NX1,8),HWF2,DXF2,REAL(NX2,8),HWF3,DXF3,REAL(NX3,8)])")
 return s
edit_region('CNVFNV',cn)
# New USE is enclosed by the existing min marker; restore that line when comparing parent.
restored=re.sub(r'! UDM37_COEFF_BEGIN\n.*?! UDM37_COEFF_END\n','',text,flags=re.S).replace(' USE udm37_min_r3\n USE udm37_line_coeff\n',' USE udm37_min_r3\n')
assert restored==raw,'parent restoration'
stage=BASE/'stage-v2';shutil.copytree(stock,stage,symlinks=True);(stage/'src/oprop.f90').write_text(text);(BASE/'oprop.observer-v2.f90').write_text(text)
(BASE/'observer-v2.patch').write_text(''.join(difflib.unified_diff(raw.splitlines(True),text.splitlines(True),fromfile='pr160/oprop.f90',tofile='line-coeff/oprop.f90')))
def pin(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
(BASE/'preparation-v2.json').write_text(json.dumps({'parent':pin(PREV/'oprop.observer-v2.f90'),'candidate':pin(stage/'src/oprop.f90'),'restoration_exact':True,'native_arithmetic_unchanged':True,'original_line_selector':{'vnu':618.023668,'encoded_MOL':102,'IFLG':1},'physical_reference_accepted':False},indent=2)+'\n')
print('prepared',stage)
