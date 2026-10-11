from run_common import *
import struct
case,rows=prepare_case('case-probe',4.,-1.)
env=ENV.copy();env['UDM37_MIN_R3_TRACE']='0'
exe=ROOT/'build/udm37-layer-line-use-v1/stage-v3/lblrtm_v12.17_linux_gnu_dbl'
run('solver-probe',[str(exe)],case,env)
check_inputs(case,rows)
p=case/'ODexact_021'
with p.open('rb') as f:
    n=struct.unpack('<i',f.read(4))[0];f.seek(n+4,1)
    n=struct.unpack('<i',f.read(4))[0];header=f.read(n)
    if struct.unpack('<i',f.read(4))[0]!=n or n!=32:raise ValueError('panel header marker/layout')
v1,v2,dv,npts,pad=struct.unpack('<dddii',header)
old=618.6144711111115;nu=v1+round((old-v1)/(16*dv))*16*dv
write('probe.json',{'executable_sha256':sha(exe),'OD_file':str(p),'first_panel_start':v1,'actual_layer21_DV':dv,
  'original_target_cm1':old,'nested_R3_target_cm1':nu,'offset_from_original_target':nu-old,
  'purpose':'Official IOD2 exact layer grid eliminates default interlayer DV rounding; defines nearby shared physical grid point, not historical target replacement',
  'physical_reference_accepted':False})
print('Probe actual DV',dv,'shared target',nu,'shift',nu-old)
