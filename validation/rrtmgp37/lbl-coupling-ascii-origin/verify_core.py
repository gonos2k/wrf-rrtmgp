"""Join root-decoded AER ASCII scalar fields to included PR161 TAPE3 record.
This does not authenticate the original physical mixing calculation.
"""
import math,struct

def require(ok,message):
    if not ok:raise ValueError(message)
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def number(x):
    require(isinstance(x,str) and x.strip()==x,'decimal representation')
    n=float(x.replace('D','E'));require(math.isfinite(n),'finite number');return n

def verify(fields,readback,data):
    require(len(data)==39000,'TAPE3 block width')
    require(fields['molecule']==fields['sidecar_molecule']==2 and fields['isotopologue']==1,'species')
    require(fields['IFLGSV']==fields['sidecar_IFLAG']==-1,'foreign coupling flag')
    require(fields['IVUP']==3 and fields['IVLO']==2 and fields['CUP']==' '*9 and fields['CLO']=='    Q  2f','literal F100 labels')
    require(readback['actual_ascii_reopened_by_root'] is True and readback['full_ascii_reopened_by_saved_CI'] is False,'ASCII readback scope')
    require(readback['record_pair_bytes_equal_between_files'] is True and readback['upstream_original_generator_authenticated'] is False and readback['full_spectral_reference_accepted'] is False and readback['production_accepted'] is False,'provenance scope')
    archive=readback['archive'];require(archive['version_DOI']=='10.5281/zenodo.4019178' and archive['md5']==archive['publisher_md5']=='12e29cc828b36f78145f6ee874af552b' and archive['actual_hash_rechecked'] is True,'versioned publisher checksum')
    files=readback['files'];require(len(files)==2,'ASCII roster')
    require(files[0]['bytes']==908403720 and files[0]['sha256']=='d0ec800cfaeaaa7ab7af7b8168f45b205e383272e147373df6d0eed2677f2bd3','held input file')
    expected=[(2651493,267925552),(49207,4969806)]
    for d,(line,offset) in zip(files,expected):
        require(len(d['matches'])==1,'unique line')
        a=d['matches'][0];b=a['sidecar']
        require(a['line_1based']==line and a['offset0']==offset and a['bytes']==101 and b['line_1based']==line+1 and b['offset0']==offset+101 and b['bytes']==101,'adjacent physical source record')
        require(a['sha256']=='c33da0b0eb2a3565cd69b4bb3e895fddd1920f92bbd6017e63e1bb34b4aa6a22' and b['sha256']=='aed61e73537de2f48676febc0a759fc18fb1c43cbec4b26d630c0a80f1135f62','record hash agreement')
        require(d['CO2_source_headers'] and all(h['source_label']=='CO2 line mixing database of Lamouroux et al., 2015' for h in d['CO2_source_headers']),'publisher header attribution')
    settings=readback['LNFL_TAPE5']
    require(settings['VMIN']==475 and settings['VMAX']==2275 and settings['physical_output_union']==[500,2250] and settings['margin_each_side_cm1']==25,'selection margin')
    require(settings['HOLIND']=='' and settings['F160'] is False and settings['NOCPL'] is False and settings['molecule_numbers']==[1,2,3,4,6,7,22] and settings['strength_rejection_controls_are_NOT_waived'] is True,'actual F100 options')
    j=123;checks=[]
    def check(label,a,b):
        require(struct.pack('<d',a)==struct.pack('<d',b),'ASCII/TAPE3 '+label);checks.append(label)
    check('VNU',number(fields['VNU_decimal']),struct.unpack_from('<d',data,8*j)[0])
    check('encoded_MOL',fields['molecule']+100*fields['isotopologue'],struct.unpack_from('<i',data,5000+4*j)[0])
    check('IFLG',abs(fields['IFLGSV']),struct.unpack_from('<i',data,9000+4*j)[0])
    for label,key,start in [('HWHMF','HWHMF_decimal',3000),('HWHMS','HWHMS_decimal',6000),('ENERGY','ENERGY_decimal',4000),('SHIFT','SHIFT_decimal',8000)]:
        check(label,f32(number(fields[key])),struct.unpack_from('<f',data,start+4*j)[0])
    check('TMPALF=1-TDEP',f32(1-f32(number(fields['TDEP_decimal']))),struct.unpack_from('<f',data,7000+4*j)[0])
    require(len(fields['Y_decimals'])==len(fields['G_decimals'])==4,'temperature coefficient width')
    k=124
    # Sidecar uses VNU:Y200 SP:G200 ALFA:Y250 EPP:G250 MOL(real bits):Y296 HWHM:G296 TMPAL:Y340 SHIFT:G340.
    offsetsY=[8*k,3000+4*k,5000+4*k,7000+4*k];offsetsG=[2000+4*k,4000+4*k,6000+4*k,8000+4*k]
    for i,t in enumerate([200,250,296,340]):
        y=f32(number(fields['Y_decimals'][i]));g=f32(number(fields['G_decimals'][i]));readY=struct.unpack_from('<d' if i==0 else '<f',data,offsetsY[i])[0];readG=struct.unpack_from('<f',data,offsetsG[i])[0]
        check('Y'+str(t),y,readY);check('G'+str(t),g,readG)
    require(struct.unpack_from('<i',data,9000+4*k)[0]==fields['sidecar_IFLAG'],'sidecar flag')
    return {'schema':'UDM37_SELECTED_ASCII_TO_TAPE3_COUPLING_V1','status':'PASS_SCOPED_PUBLISHER_ASCII_TO_TAPE3_FIELDS','exact_scalar_joins':len(checks),'checks':checks,'normal_record_locations':[[n,o] for n,o in expected],'selected_line_cm1':number(fields['VNU_decimal']),'publisher_version_DOI':'10.5281/zenodo.4019178','publisher_header_mixing_attribution':'Lamouroux et al., 2015','source_reader_mode':'F100','strength_normalization_replayed':False,'upstream_YG_generation_reproduced':False,'full_band_cutoff_and_cancellation_validated':False,'physical_reference_accepted':False,'production_accepted':False}
