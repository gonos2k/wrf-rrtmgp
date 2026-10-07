import collections, math, struct

def f32(x):
    return struct.unpack("!f",struct.pack("!f",x))[0]

def parse(path):
    events = {}
    for line in path.read_text(errors='replace').splitlines():
        if not line.startswith('HOST_JOIN_V1 '):
            continue
        tokens = line.split()
        if len(tokens) != 14:
            raise ValueError(f'malformed observer row: {line[:120]}')
        key = (tokens[1], *map(int, tokens[2:6]))
        if key in events:
            raise ValueError(f'duplicate event identity: {key}')
        bits = tuple(int(x, 16) for x in tokens[6:])
        vals = tuple(struct.unpack('!f', struct.pack('!I', x))[0] for x in bits)
        if not all(map(math.isfinite,vals)):
            raise ValueError(f'nonfinite {key}')
        events[key] = (bits, vals)
    if not events:
        raise ValueError('no actual full-host observer rows')
    return events

def verify_join(events, restart=False):
    counts = collections.Counter(k[0] for k in events)
    required = {'START_PRE','START_POST','RK_PRE','RK_POST','UDM_ENTRY','UDM_RETURN','HELPER_IN','HELPER_OUT'}
    if not required <= counts.keys():
        raise ValueError(f'missing actual stages: {required-counts.keys()}')
    pre = {k[4]: v for k,v in events.items() if k[0]=='START_PRE'}
    post = {k[4]: v for k,v in events.items() if k[0]=='START_POST'}
    if pre.keys()!=post.keys():
        raise ValueError('startup level roster mismatch')
    if set(pre) != set(range(1,60)):
        raise ValueError('expected actual 59-layer input roster')
    steps=sorted({k[1] for k in events if k[0]=='UDM_ENTRY'})
    if steps != list(range(7,13) if restart else range(1,7)):
        raise ValueError(f'expected six consecutive actual model steps: {steps}')
    slot_nn,slot_nc=map(int,next(iter(pre.values()))[1][6:8])
    if slot_nn==slot_nc or slot_nn<=0 or slot_nc<=0:
        raise ValueError('invalid actual Registry QNN/QNC slot mapping')
    levels=range(1,60)
    expected={(stage,steps[0]-1,0,0,k) for stage in ('START_PRE','START_POST') for k in levels}
    expected|={(stage,step,rk,slot,k) for stage in ('RK_PRE','RK_POST') for step in steps
               for rk in (1,2,3) for slot in (slot_nn,slot_nc) for k in levels}
    expected|={(stage,step,0,0,k) for stage in ('UDM_ENTRY','UDM_RETURN','HELPER_IN','HELPER_OUT')
               for step in steps for k in levels}
    if not restart:
        expected|={(stage,1,0,0,k) for stage in ('RESET_PRE','RESET_POST') for k in levels}
    if events.keys()!=expected:
        raise ValueError(f'exact event roster mismatch missing={len(expected-events.keys())} extra={len(events.keys()-expected)}')
    for step in steps:
        for k in levels:
            before=events.get(('RESET_PRE',step,0,0,k),events[('UDM_ENTRY',step,0,0,k)])
            for field,slot in ((0,slot_nn),(1,slot_nc)):
                if events[('RK_POST',step,3,slot,k)][0][0]!=before[0][field]:
                    raise ValueError('final actual RK update does not join actual UDM consumer')
                initial=post[k] if step==steps[0] else events[('UDM_RETURN',step-1,0,0,k)]
                if events[('RK_PRE',step,1,slot,k)][0][0]!=initial[0][field]:
                    raise ValueError('actual returned/input number does not join next transport step')
    if any(pre[k][0][:3]!=post[k][0][:3] for k in pre) and restart:
        raise ValueError('restart start_em changed supplied numbers')
    residuals = []
    nonzero_tendencies = 0
    rk_stages = set()
    for key, (bits, vals) in events.items():
        stage, step, rk, slot, level = key
        if stage == 'RK_PRE':
            other = events.get(('RK_POST',step,rk,slot,level))
            if other is None:
                raise ValueError('missing actual RK update pair')
            if rk<3:
                following=events[('RK_PRE',step,rk+1,slot,level)]
                if other[0][:2]!=following[0][:2]:
                    raise ValueError('actual inter-RK scalar/old-buffer join mismatch')
            value, old, adv, source, pold, pnew, dt, mapy = map(f32,vals)
            base = value if rk==1 else old
            # Same source order; roundoff bound allows compiler contraction,
            # not a physical acceptance tolerance or archived-output fit.
            expected = f32(f32(f32(pold*base) + f32(dt*f32(f32(adv*mapy)+source)))/pnew)
            got = f32(other[1][0])
            rel = abs(float(got)-float(expected))/max(abs(float(expected)),1.)
            if rel > 8*(2.**-23):
                raise ValueError(f'actual RK identity mismatch {key}: {got}, {expected}, {rel}')
            residuals.append(rel)
            nonzero_tendencies += int(adv != 0)
            rk_stages.add(rk)
        elif stage=='UDM_ENTRY':
            reset = events.get(('RESET_POST',step,0,0,level))
            if reset is not None and bits[:3]!=reset[0][:3]:
                raise ValueError('reset post and actual UDM entry do not join')
        elif stage=='HELPER_IN':
            out = events.get(('HELPER_OUT',step,0,0,level))
            ret = events.get(('UDM_RETURN',step,0,0,level))
            if out is None or ret is None:
                raise ValueError('missing actual helper/UDM return join')
            if bits[:5]+bits[6:] != out[0][:5]+out[0][6:]:
                raise ValueError('radius helper changed input tuple')
            # Same NN/NC/NR/QC/density, then native radius and temperature.
            if out[0][:7] != ret[0][:7]:
                raise ValueError('helper output does not join actual driver return')
    if rk_stages != {1,2,3} or not residuals:
        raise ValueError(f'full RK stages absent: {rk_stages}')
    if not nonzero_tendencies:
        raise ValueError('connected transport requires a nonzero actual advection tendency')
    if restart and ('RESET_PRE' in counts or 'RESET_POST' in counts):
        raise ValueError('unexpected first-step constant reset on restart')
    return {'stage_rows':dict(counts), 'actual_RK_stages':sorted(rk_stages),
            'RK_update_pairs':len(residuals), 'nonzero_advection_tendency_rows':nonzero_tendencies,
            'max_RK_relative_residual':max(residuals),
            'exact_stage_step_slot_layer_roster':True,
            'actual_Registry_number_slots':{'QNN':slot_nn,'QNC':slot_nc},
            'input_return_transport_consumer_join_bitwise':True,
            'inter_RK_scalar_old_buffer_join_bitwise':True,
            'same_cell_helper_to_driver_return_bitwise':True,
            'restart_without_first_step_reset':restart}
