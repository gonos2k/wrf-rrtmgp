"""Compare saved actual public-column records; stdlib, no fresh solver."""
import importlib.util, json, math, struct
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]

def load_parser():
    spec = importlib.util.spec_from_file_location('trace_parser', ROOT / 'validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def require(ok, message):
    if not ok: raise ValueError(message)

def bits(values):
    return b''.join(struct.pack('<f', x) for x in values)

def analyze(read):
    parser = load_parser(); output = {'production_accepted': False, 'physical_gate_closed': False, 'phases': {}}
    for phase in ('lw', 'sw'):
        _, raw = parser.trace(read(f'capture/{phase}.raw'), 'raw')
        header, original = parser.trace(read(f'capture/{phase}.input'), 'input')
        _, captured = parser.trace(read(f'capture/{phase}.result'), 'result')
        results, inputs = {}, {}
        for mode in ('native', 'volume_sync', 'gamma_v01', 'zero_uniform'):
            _, results[mode] = parser.trace(read(f'columns/{phase}-{mode}/{phase}.result'), 'result')
            _, inputs[mode] = parser.trace(read(f'columns/{phase}-{mode}/input'), 'input')
        require(raw['SOURCE_TIME_SECONDS']['values'] == [50.], 'wrong radiation source time')
        for name, row in original.items():
            require(bits(row['values']) == bits(inputs['native'][name]['values']), 'native replay input changed ' + name)
        for mode in inputs:
            for name in original:
                if name != 'REL': require(inputs[mode][name] == inputs['native'][name], 'held component changed ' + name)
        for name in ('UP', 'DN', 'HR'):
            require(bits(captured[name]['values']) == bits(results['native'][name]['values']), 'public-column baseline differs ' + name)
        lwp = raw['UNIFORM_CF0_LWP']['values']; rwp = raw['UNIFORM_CF0_RWP']['values']; cf = original['CF']['values']
        require(sum(rwp) > 0. and all(f == 0. for f, l, r in zip(cf, lwp, rwp) if l > 0. or r > 0.), 'CF0 component not separate')
        tau = results['native']['UNIFORM_CF0_TAU']['values']
        require(all(math.isfinite(x) and x >= 0. for x in tau) and sum(tau) > 0., 'uniform component not consumed')
        require('UNIFORM_CF0_TAU' not in results['zero_uniform'], 'zero diagnostic still adds uniform component')
        for name in ('MASK', 'GAS_TAU', 'CLOUD_TAU', 'PRECIP_TAU', 'PREPARED_TAU', 'UPC', 'DNC', 'HRC'):
            require(results['native'][name] == results['zero_uniform'][name], 'uniform experiment changed existing component ' + name)
        if phase == 'sw':
            _, diagnostic = parser.trace(read('columns/sw-native/sw.input'), 'input')
            require(sum(diagnostic['RAW_UNIFORM_TAU']['values']) > 0., 'raw direct-beam extinction missing')
        comparisons = {}
        for label, old, new in (
                ('uniform_CF0_direct_effect', 'zero_uniform', 'native'),
                ('consumed_vs_synchronous_volume', 'native', 'volume_sync'),
                ('explicit_PSD_shape_only', 'volume_sync', 'gamma_v01')):
            rows = {}
            for name in ('UP', 'DN', 'HR'):
                a = results[old][name]['values']; b = results[new][name]['values']; delta = [y-x for x,y in zip(a,b)]
                index = max(range(len(delta)), key=lambda i: abs(delta[i]))
                rows[name] = {'max_abs': abs(delta[index]), 'signed_at_max': delta[index], 'index_from_1': index+1,
                              'surface_difference': delta[0] if name != 'HR' else None,
                              'TOA_difference': delta[-1] if name != 'HR' else None}
            comparisons[label] = rows
        output['phases'][phase.upper()] = {'source_time_seconds': 50., 'uniform_lwp_g_m2': sum(lwp),
            'uniform_rwp_g_m2': sum(rwp), 'native_replay_flux_heating_bitwise_equal': True,
            'held_original_inputs_and_cloud_CF': True, 'comparisons': comparisons}
    return output

if __name__ == '__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('saved',type=Path);a=ap.parse_args()
    print(json.dumps(analyze(lambda name:(a.saved/name).read_bytes()), indent=2))
