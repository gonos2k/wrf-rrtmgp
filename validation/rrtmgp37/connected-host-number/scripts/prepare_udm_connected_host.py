#!/usr/bin/env python3
"""Prepare a reversible, serial REAL32 full-WRF host observer snapshot.

No production file is edited. Every injected block is removable byte-for-byte.
The snapshot must be built as a full WRF SCM; this is not a procedure fixture.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

BEGIN = '! HOST_CONNECTED_OBSERVER_BEGIN\n'
END = '! HOST_CONNECTED_OBSERVER_END\n'


def marked(text):
    return BEGIN + text.rstrip() + '\n' + END


def inject(text, anchor, addition, after=False):
    if text.count(anchor) != 1:
        raise ValueError(f'anchor count {text.count(anchor)}: {anchor[:100]!r}')
    return text.replace(anchor, anchor + marked(addition) if after else marked(addition) + anchor)


def emit(stage, step, rk, slot, lo, values):
    if len(values) != 8:
        raise ValueError('eight fields required')
    return f"CALL host_connected_state('{stage}',{step},{rk},{slot},{lo}, &\n" + ', &\n'.join(values) + ')'


def patch(relative, text):
    use = '   USE module_ra_rrtmgp_trace, ONLY: host_connected_enabled, host_connected_state\n'
    if relative == 'phys/module_ra_rrtmgp_trace.F':
        text = inject(text, '  INTERFACE trace_result\n', '  PUBLIC :: host_connected_enabled, host_connected_state\n')
        text = inject(text, 'CONTAINS\n', '''
  LOGICAL FUNCTION host_connected_enabled()
    CHARACTER(8) :: value
    INTEGER :: status
    CALL GET_ENVIRONMENT_VARIABLE('WRF_UDM_HOST_TRACE',value,STATUS=status)
    host_connected_enabled = status == 0 .AND. TRIM(value) == '1'
  END FUNCTION

  SUBROUTINE host_connected_state(stage,step,rk,slot,klo,a,b,c,d,e,f,g,h)
    CHARACTER(*), INTENT(IN) :: stage
    INTEGER, INTENT(IN) :: step,rk,slot,klo
    REAL, INTENT(IN) :: a(:),b(:),c(:),d(:),e(:),f(:),g(:),h(:)
    INTEGER :: k
    IF (STORAGE_SIZE(a) /= 32) ERROR STOP 'host observer requires REAL32'
    DO k=1,SIZE(a)
      WRITE(*,'(A,1X,A,4(1X,I0),8(1X,Z8.8))') 'HOST_JOIN_V1',TRIM(stage), &
        step,rk,slot,klo+k-1,TRANSFER(a(k),0),TRANSFER(b(k),0),TRANSFER(c(k),0), &
        TRANSFER(d(k),0),TRANSFER(e(k),0),TRANSFER(f(k),0),TRANSFER(g(k),0),TRANSFER(h(k),0)
    ENDDO
  END SUBROUTINE
''', after=True)
    elif relative == 'dyn_em/start_em.F':
        text = inject(text, '   USE module_state_description\n   USE module_driver_constants\n', use)
        v = ['scalar(1,kts:kte-1,1,p_qnn)', 'scalar(1,kts:kte-1,1,p_qnc)',
             'scalar(1,kts:kte-1,1,p_qnr)']
        z = '0.*scalar(1,kts:kte-1,1,p_qnn)'
        v += [z + '+grid%ccn_conc', z + '+MERGE(1.,0.,config_flags%restart)', z, z+'+REAL(P_QNN)', z+'+REAL(P_QNC)']
        guard = 'IF (host_connected_enabled() .AND. f_qnn .AND. f_qnc .AND. f_qnr) THEN\n'
        anchor = '      ccn_max_val = MAXVAL(scalar(its:MIN(ite,ide-1),kts:kte-1,jts:MIN(jte,jde-1),p_qnn))\n'
        text = inject(text, anchor, guard + emit('START_PRE','grid%itimestep','0','0','kts',v) + '\nENDIF')
        anchor = '   IF (num_scalar > 0) THEN\n\n! use of (:,:,:,loop)'
        text = inject(text, anchor, guard + emit('START_POST','grid%itimestep','0','0','kts',v) + '\nENDIF')
    elif relative == 'dyn_em/solve_em.F':
        text = inject(text, '   USE module_state_description\n', use)
        ks = 'k_start:MIN(k_end,kde-1)'
        s = f'scalar(1,{ks},1,is)'
        z = '0.*' + s
        vals = [s, f'scalar_old(1,{ks},1,is)', f'advect_tend(1,{ks},1)',
                f'scalar_tend(1,{ks},1,is)',
                f'grid%c1h({ks})*(grid%mu_1(1,1)+grid%mub(1,1))+grid%c2h({ks})',
                f'grid%c1h({ks})*(grid%mu_2(1,1)+grid%mub(1,1))+grid%c2h({ks})',
                z + '+dt_rk', z + '+grid%msfty(1,1)']
        guard = '''IF (host_connected_enabled() .AND. (is==P_QNN .OR. is==P_QNC)) THEN
 IF (grid%i_start(ij)<=1 .AND. grid%i_end(ij)>=1 .AND. &
     grid%j_start(ij)<=1 .AND. grid%j_end(ij)>=1) THEN
'''
        first = list(vals)
        first[1] = s
        pre = ('IF (rk_step==1) THEN\n' + emit('RK_PRE','grid%itimestep','rk_step','is','k_start',first)
               + '\nELSE\n' + emit('RK_PRE','grid%itimestep','rk_step','is','k_start',vals) + '\nENDIF')
        text = inject(text, '           CALL rk_update_scalar( scs=is, sce=is,', guard + pre + '\n ENDIF\nENDIF')
        anchor = '! bound the aerosol fields (greater than 0) when using first guess aerosol\n'
        text = inject(text, anchor, guard + emit('RK_POST','grid%itimestep','rk_step','is','k_start',vals) + '\n ENDIF\nENDIF')
    elif relative == 'phys/module_microphysics_driver.F':
        text = inject(text, '   USE module_mp_udm\n', use)
        ks = 'kds:MIN(kde-1,kme)'
        q = f'qnn_curr(1,{ks},1)'
        vals = [q, f'qnc_curr(1,{ks},1)', f'qnr_curr(1,{ks},1)']
        z = '0.*' + q
        vals += [z+'+ccn_conc',z,z,z,z]
        guard = 'IF (host_connected_enabled()) THEN\n'
        anchor = '       QNN_CURR(ims:ime,kms:kme,jms:jme) = ccn_conc\n'
        text = inject(text, anchor, guard + emit('RESET_PRE','itimestep','0','0','kds',vals) + '\nENDIF')
        text = inject(text, anchor, guard + emit('RESET_POST','itimestep','0','0','kds',vals) + '\nENDIF',after=True)
        ks = 'kts:kte'
        vals = [f'{name}(1,{ks},1)' for name in ('qnn_curr','qnc_curr','qnr_curr','qc_curr','rho','re_cloud')]
        vals += [f'th(1,{ks},1)*pi_phy(1,{ks},1)', f'0.*qnn_curr(1,{ks},1)+ccn_conc']
        guard = '''IF (host_connected_enabled() .AND. its<=1 .AND. ite>=1 .AND. jts<=1 .AND. jte>=1) THEN
'''
        anchor = '             ! Capture the producer tuple before any later physics or dynamics\n'
        text = inject(text, anchor, guard + emit('UDM_RETURN','itimestep','0','0','kts',vals) + '\nENDIF')
        # The actual entry observer already selects exactly this option-37 call.
        anchor = '             ! Capture the actual UDM call inputs before it can update TH/Q.\n'
        text = inject(text, anchor, guard + emit('UDM_ENTRY','itimestep','0','0','kts',vals) + '\nENDIF')
    elif relative == 'phys/module_mp_udm.F':
        text = inject(text, '   use module_mp_radar\n', use)
        vals = ['nn(i,kts:kte,j)', 'nc1d(kts:kte)', 'nr(i,kts:kte,j)', 'qc1d(kts:kte)',
                'den1d(kts:kte)', 're_qc(kts:kte)', 't1d(kts:kte)', '0.*nc1d(kts:kte)+ccn0']
        guard = 'IF (host_connected_enabled() .AND. i==1 .AND. j==1) THEN\n'
        anchor = '            call udm_mp_effective_radius(t1d,qc1d,qi1d,qs1d,den1d,qmin, t0c    &\n'
        text = inject(text, anchor, guard + emit('HELPER_IN','itimestep','0','0','kts',vals) + '\nENDIF')
        anchor = '                               ,re_qc, re_qi, re_qs, kts, kte, i, j)\n'
        text = inject(text, anchor, guard + emit('HELPER_OUT','itimestep','0','0','kts',vals) + '\nENDIF',after=True)
    else:
        raise ValueError(relative)
    return text


FILES = ('phys/module_ra_rrtmgp_trace.F', 'dyn_em/start_em.F', 'dyn_em/solve_em.F',
         'phys/module_microphysics_driver.F', 'phys/module_mp_udm.F')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('wrf', type=Path)
    p.add_argument('--snapshot', type=Path, required=True)
    a = p.parse_args()
    if a.snapshot.exists():
        raise ValueError('fresh snapshot required')
    shutil.copytree(a.wrf, a.snapshot, symlinks=True)
    records = {}
    for rel in FILES:
        raw = (a.wrf / rel).read_bytes()
        changed = patch(rel, raw.decode())
        stripped = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END), '', changed, flags=re.S).encode()
        if stripped != raw:
            raise AssertionError(f'not reversible: {rel}')
        (a.snapshot / rel).write_text(changed)
        records[rel] = {'production_sha256': hashlib.sha256(raw).hexdigest(),
                        'snapshot_sha256': hashlib.sha256(changed.encode()).hexdigest(),
                        'byte_exact_reverse': True}
    (a.snapshot.parent / 'observer-source-pins.json').write_text(json.dumps(records,indent=2)+'\n')


if __name__ == '__main__':
    main()
