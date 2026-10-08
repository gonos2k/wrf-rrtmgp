from run_common import *
import re,difflib
parent=ROOT/'build/udm37-layer-line-use-v1/oprop.observer.f90';old=parent.read_text();s=old
probe=json.loads((BASE/'probe.json').read_text());target=probe['nested_R3_target_cm1'];changes=[]
def replace(a,b):
    global s
    if s.count(a)!=1:raise ValueError('unique observer anchor')
    s=s.replace(a,b);changes.append({'before':a,'after':b})
replace('target_nu=618.6144711111115D0','target_nu='+repr(target)+'D0')
replace('use_selected=min_active.AND.(min_panel==13.OR.min_panel==14).AND.ABS(use_nu(i)-target_nu)<=25D0.AND.use_flag(i)>=0',
        'use_selected=min_active.AND.ABS(use_nu(i)-target_nu)<=5D0.AND.use_flag(i)>=0')
replace('final_active=min_active.AND.min_layer==21.AND.min_panel==14','final_active=.FALSE. ! Old grid-specific final stencils are not used for this experiment')
oldout='! UDM37_USE_BEGIN\n CALL use_emit("OUTCOME",I,[REAL(use_reason,8),REAL(use_stage,8),SP(I),SPPSP(I)])\n! UDM37_USE_END\n      SPPSP(I) = 0.\n'
replace(oldout,'      SPPSP(I) = 0.\n! UDM37_USE_BEGIN\n CALL use_emit("OUTCOME",I,[REAL(use_reason,8),REAL(use_stage,8),SP(I),SPPSP(I)])\n! UDM37_USE_END\n')
back=s
for r in reversed(changes):
    if back.count(r['after'])!=1:raise ValueError('inverse anchor')
    back=back.replace(r['after'],r['before'])
if back!=old:raise ValueError('exact parent restoration')
(BASE/'oprop.observer.f90').write_text(s)
(BASE/'observer.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='PR164/oprop.observer.f90',tofile='grid-threshold/oprop.observer.f90')))
shutil.copytree(ROOT/'build/udm37-layer-line-use-v1/stage-v3',BASE/'stage',symlinks=True)
shutil.copyfile(BASE/'oprop.observer.f90',BASE/'stage/src/oprop.f90')
write('preparation.json',{'parent_sha256':sha(parent),'source_sha256':sha(BASE/'oprop.observer.f90'),'observer_only_changes':changes,
  'inverse_observer_changes_restore_parent_bytes':True,'actual_target_cm1':target,'line_centre_window_cm1':5,
  'physical_grid_IOD':2,'production_changed':False,'old_FINAL_OD_stencils_used':False})
print('Prepared coordinate-based observer; exact inverse restores PR164 bytes')
