"""Scoped selected-line replay; no full TAPE3, OD or executable read."""
import math,struct
PRE_NAMES='VNU S ALFA0 EPP HWHMS TMPALF PSHIFT TAVE TEMP0 PAVE P0 XKT RHOSLF RHORAT TRATIO PAVP0 PAVP2 BETACR SCOR ALFD1 WEIGHT ISOTPL_FLAG JRAD RADCN2 ALFMAX DV IBRD'.split()
POST_NAMES='YI GI SUI SPPI SP SPPSP RECALF ZETA IZETA FZETA ZETDIF ALFL ALFAD ALFV TMPCOR ALFA0I HWHMSI VNU ILC RECTLC TMPDIF A1 A2 A3 A4 B1 B2 B3 B4 AVRAT0 AVRAT1 NMINAD NPLSAD BRD_SUM SLOPEA SLOPEB'.split()
CN_NAMES='SP RECALF DEPTHI IZM ZETA ZETDIF CF0 CF1 BASE CLC3 DPTRAT STRF3 VNU ZSLOPE WAVDXF ZINT CONF3 JMIN1 JMAX1 J3SHFT JMIN3 HWDXF ZF3L IZ3 F3 HWF1 DXF1 NX1 HWF2 DXF2 NX2 HWF3 DXF3 NX3'.split()
def require(ok,msg):
 if not ok:raise ValueError(msg)
def bits(x):return struct.pack('<d',x)
def parse(trace):
 rows=[]
 for line in trace.splitlines():
  a=line.split();tag=a[0];ints=list(map(int,a[1:9]));v=list(map(float,a[9:]));require(len(v)==ints[7] and all(math.isfinite(x) for x in v),'finite record width');rows.append({'tag':tag,'seq':ints[0],'block':ints[1],'record':ints[2],'slot':ints[3],'mol':ints[4],'iso':ints[5],'panel':ints[6],'v':v})
 require([r['tag'] for r in rows]==['RAW_LINE','RAW_COUPLING','LNC_PRE','LNC_POST','CN_GEN'] and [r['seq'] for r in rows]==[1,2,3,4,5],'exact selected event roster')
 require(all((r['block'],r['record'],r['mol'],r['iso'],r['panel'])==(260,521,2,1,13) for r in rows),'line identity join')
 require([r['slot'] for r in rows]==[124,125,124,124,124],'line and sidecar slots')
 require([len(r['v']) for r in rows]==[38,9,27,36,34],'exact field widths')
 return rows

def analyze(trace,header,block_header,data,first):
 rows=parse(trace);raw,side=rows[0]['v'],rows[1]['v'];pre=dict(zip(PRE_NAMES,rows[2]['v']));post=dict(zip(POST_NAMES,rows[3]['v']));cn=dict(zip(CN_NAMES,rows[4]['v']))
 require(len(pre)==len(PRE_NAMES) and len(post)==len(POST_NAMES) and len(cn)==len(CN_NAMES),'schema widths')
 require(len(header)==1664 and header[88:96]==b'  CO2   ' and header[55:56]!=b'^','input header identity')
 require(len(block_header)==24 and len(data)==39000,'included input layout')
 vmin,vmax,nrec,nwds=struct.unpack('<ddii',block_header);require(nrec==249 and nwds==9750 and vmin<=raw[0]<=vmax,'line block bounds')
 def read(i):
  j=i-1;v=[struct.unpack_from('<d',data,8*j)[0]]
  v+=[struct.unpack_from('<i' if a in (3,7) else '<f',data,2000+1000*a+4*j)[0] for a in range(8)]
  return v
 r=read(124);require(r[4]==102 and r[8]==1,'raw encoded species and flag')
 expected=[r[0],r[1],r[2],r[3],r[5],r[6],r[7],r[8],r[4]]
 j=123;expected+=[struct.unpack_from('<i',data,10000+4*(a+7*j))[0] for a in range(7)]
 expected+=[struct.unpack_from('<f',data,17000+4*(a+21*j))[0] for a in range(21)]+[struct.unpack_from('<f',data,38000+4*j)[0]]
 require(len(raw)==38 and all(bits(a)==bits(float(b)) for a,b in zip(raw,expected)),'raw line excerpt join')
 s=read(125);s[4]=struct.unpack_from('<f',data,5000+4*124)[0]
 expected=[s[0],s[1],s[2],s[3],s[4],s[5],s[6],s[7],s[8]]
 require(len(side)==9 and all(bits(a)==bits(float(b)) for a,b in zip(side,expected)) and side[8]==-1,'coupling sidecar excerpt join')
 require(raw[9:]==[0.]*29,'unsupported broadeners or speed dependency')
 require([pre[k] for k in ('VNU','S','ALFA0','EPP','HWHMS','TMPALF','PSHIFT')]==raw[:7],'RDLIN to LNCOR1 join')
 require(pre['ISOTPL_FLAG']==pre['JRAD']==pre['IBRD']==0 and post['BRD_SUM']==0 and post['NMINAD']==post['NPLSAD']==0,'unsupported selected branch')
 require([post[k] for k in ('A1','A2','A3','A4','B1','B2','B3','B4')]==[side[0],side[2],side[4],side[6],side[1],side[3],side[5],side[7]],'temperature coefficient join')
 exact=[];near=[]
 def eq(name,actual,expected):
  require(bits(actual)==bits(expected),name+' binary64 arithmetic');exact.append(name)
 def close(name,actual,expected):
  require(abs(actual-expected)<=8*math.ulp(actual),name+' libm tolerance');near.append({'name':name,'absolute_error':abs(actual-expected),'allowance_ULP':8})
 eq('TRATIO',pre['TRATIO'],pre['TAVE']/pre['TEMP0'])
 eq('RHORAT',pre['RHORAT'],(pre['PAVE']/pre['P0'])*(pre['TEMP0']/pre['TAVE']))
 eq('PAVP0',pre['PAVP0'],pre['PAVE']/pre['P0']);eq('PAVP2',pre['PAVP2'],pre['PAVP0']*pre['PAVP0'])
 eq('XKT',pre['XKT'],pre['TAVE']/pre['RADCN2'])
 eq('BETACR',pre['BETACR'],1./pre['XKT']-1./(pre['TEMP0']/pre['RADCN2']))
 require(post['ILC']==1 and 200<=pre['TAVE']<250,'selected temperature interval')
 eq('RECTLC',post['RECTLC'],1./(250.-200.));eq('TMPDIF',post['TMPDIF'],pre['TAVE']-200.)
 eq('SLOPEA',post['SLOPEA'],(post['A2']-post['A1'])*post['RECTLC'])
 eq('YI',post['YI'],post['A1']+post['SLOPEA']*post['TMPDIF'])
 eq('SLOPEB',post['SLOPEB'],(post['B2']-post['B1'])*post['RECTLC']);eq('GI',post['GI'],post['B1']+post['SLOPEB']*post['TMPDIF'])
 eq('shifted_VNU',post['VNU'],pre['VNU']+pre['RHORAT']*pre['PSHIFT'])
 close('TMPCOR',post['TMPCOR'],pre['TRATIO']**pre['TMPALF'])
 eq('ALFA0I',post['ALFA0I'],pre['ALFA0']*post['TMPCOR']);eq('HWHMSI',post['HWHMSI'],pre['HWHMS']*post['TMPCOR'])
 eq('ALFL',post['ALFL'],post['ALFA0I']*(pre['RHORAT']-pre['RHOSLF'])+post['HWHMSI']*pre['RHOSLF'])
 eq('ALFAD',post['ALFAD'],post['VNU']*pre['ALFD1'])
 eq('ZETA',post['ZETA'],post['ALFL']/(post['ALFL']+post['ALFAD']))
 eq('FZETA',post['FZETA'],100.*post['ZETA']);eq('ZETDIF',post['ZETDIF'],post['FZETA']-(post['IZETA']-1.))
 eq('ALFV',post['ALFV'],(post['AVRAT0']+post['ZETDIF']*(post['AVRAT1']-post['AVRAT0']))*(post['ALFL']+post['ALFAD']))
 require(pre['DV']<post['ALFV']<pre['ALFMAX'],'no width clamp');eq('RECALF',post['RECALF'],1./post['ALFV'])
 sui=pre['S']*pre['WEIGHT'];sui=sui*pre['SCOR']*math.exp(-pre['EPP']*pre['BETACR'])*(1.+math.exp(-post['VNU']/pre['XKT']))
 close('SUI',post['SUI'],sui)
 eq('SP',post['SP'],post['SUI']*(1.+post['GI']*pre['PAVP2']))
 eq('SPPI',post['SPPI'],post['SUI']*post['YI']*pre['PAVP0']);eq('SPPSP',post['SPPSP'],post['SPPI']/post['SP'])
 for a,b in [('SP','SP'),('RECALF','RECALF'),('ZETA','ZETA'),('IZM','IZETA'),('VNU','VNU')]:eq('CN_join_'+a,cn[a],post[b])
 eq('DEPTHI',cn['DEPTHI'],cn['SP']*cn['RECALF'])
 eq('CN_ZETDIF',cn['ZETDIF'],100.*cn['ZETA']-(cn['IZM']-1.))
 eq('baseline_STRF3',cn['BASE'],cn['DEPTHI']*(cn['CF0']+cn['ZETDIF']*(cn['CF1']-cn['CF0'])))
 eq('CLC3',cn['CLC3'],64./(cn['NX3']-1.));eq('DPTRAT',cn['DPTRAT'],post['SPPSP'])
 eq('coupling_STRF3',cn['STRF3'],cn['BASE']*cn['CLC3']*cn['DPTRAT'])
 eq('WAVDXF',cn['WAVDXF'],pre['DV']/cn['DXF1']);eq('ZSLOPE',cn['ZSLOPE'],cn['RECALF']*cn['WAVDXF'])
 require(first['destination']==170 and first['line_slot']==124 and first['phase']==2 and first['source_index']==493,'first-negative join identity')
 vals=first['values'];require(len(vals)==8 and first['layer']==21 and first['panel']==13,'first-negative owner');require(all(bits(a)==bits(b) for a,b in zip([cn['STRF3'],cn['F3'],cn['ZF3L'],cn['VNU'],cn['SP'],cn['DPTRAT']],vals[2:])),'first-negative operand join')
 z=(cn['JMIN3']-2.-cn['ZINT']*cn['CONF3'])*cn['ZSLOPE']
 steps=int(first['destination']+cn['J3SHFT']-cn['JMIN1']+1)
 require(steps==51,'ZF increment support')
 for _ in range(steps):z=z+cn['ZSLOPE']
 eq('ZF3L',cn['ZF3L'],z);require(int(abs(z)+1.5)==cn['IZ3']==493,'F3 lookup index')
 x=(cn['IZ3']-1.)*cn['DXF3'];require(2<=cn['IZ3']<=int(cn['HWF2']/cn['DXF3']+1.001),'selected Q2-Q3 shape branch')
 def a(h):return (1.+2.*h*h)/(1.+h*h)**2
 def b(h):return -1./(1.+h*h)**2
 f3=(1./(2.*math.asin(1.)))*((a(cn['HWF2'])+b(cn['HWF2'])*(x*x))-(a(cn['HWF3'])+b(cn['HWF3'])*(x*x)))
 close('SHAPEL_F3',cn['F3'],f3)
 eq('first_negative_after',vals[1],vals[0]+cn['STRF3']*cn['F3']*cn['ZF3L'])
 return {'status':'PASS_SCOPED_TAPE3_LINE_TO_COUPLING_OPERANDS','line_identity':{'file_record':521,'block':260,'slot':124,'molecule_code':2,'molecule_name_from_header':'CO2','isotopologue_code':1,'original_VNU':raw[0],'shifted_VNU':post['VNU'],'IFLG':1,'sidecar_slot':125},'TAVE':pre['TAVE'],'temperature_coefficient_A':side[0:8:2],'YI':post['YI'],'SP':post['SP'],'SPPI':post['SPPI'],'SPPSP':post['SPPSP'],'baseline_STRF3':cn['BASE'],'coupling_STRF3':cn['STRF3'],'F3':cn['F3'],'ZF3L':cn['ZF3L'],'first_negative_after':vals[1],'bitwise_checks':exact,'transcendental_checks':near,'upstream_database_line_identity_authenticated':False,'WK_SCOR_ALFD1_AVRAT_CF3_generation_independently_validated':False,'complete_physical_operand_ancestry':False,'final_spectral_cancellation_accepted':False,'physical_reference_accepted':False,'production_accepted':False}
