"""Read existing capture records only; never invoke WRF, a build, or reference solver."""
import hashlib
import json
import pathlib
import sys

sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[2]
CURRENT = ROOT / 'build/udm37-phase-diagnostic-contract-pr-work'
SUPPORT = CURRENT / 'WRF/test/rrtmgp'
OUT = pathlib.Path(__file__).resolve().parent / 'inventory.json'

def pin(path):
    path = pathlib.Path(path)
    return {'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def checked(path, expected):
    found = pin(path)
    assert found['sha256'] == expected, (path, 'SHA mismatch')
    return found

def load(path):
    return json.loads(path.read_text())

def main():
    assert not OUT.exists(), 'collision: inventory.json already exists'
    helper_pins = [pin(SUPPORT/n) for n in ['test_column_replay.py',
        'compare_column_replay.py', 'test_cloud_scm.py', 'test_surface_scm.py']]
    sys.path.insert(0, str(SUPPORT))
    import test_column_replay as p
    import compare_column_replay as c
    import numpy as np

    def profile(inp, raw, result, expected=None):
        pins = [pin(x) for x in [inp, raw, result]]
        if expected:
            for field, item in zip(['input_sha256','raw_sha256','result_sha256'], pins):
                assert item['sha256'] == expected[field]
        phase,nc,nl,overlap,seed,iceflag,a = p.read_input(inp)
        _,i,j,r = p.read_raw(raw)
        z = c.read_result(result)
        native = len(r['CF'])
        for records in [a,r,z['sections']]:
            assert all(np.all(np.isfinite(v)) for v in records.values())
        layers = []
        for pop,ip,lp,re,grid in [('native','IWP','LWP','REI','IWP_GRID'),
              ('cu','CU_IWP','CU_LWP','CU_REI','CU_ACCEPTED_GRID_IWP')]:
            if ip not in a: continue
            for k in np.flatnonzero((r[grid]>0)&(r['CF']>0)&(2*a[re][0,:native]>180)):
                layers.append({'population':pop, 'native_k_1based':int(k+1),
                    'diameter_um':float(2*a[re][0,k]), 'grid_iwp_g_m2':float(r[grid][k]),
                    'incloud_iwp_g_m2':float(a[ip][0,k]), 'incloud_lwp_g_m2':float(a[lp][0,k]),
                    'ice_only_population_layer':bool(a[lp][0,k]==0), 'CF':float(r['CF'][k]),
                    'realized_mask_gpoints':int(np.count_nonzero(z['sections']['MASK'][0,k]))})
        return {'phase':phase,'i':i,'j':j,'native_layers':native,'engine_layers':nl,
            'overlap':overlap,'seed':seed,'iceflag':iceflag,
            'input_version':inp.read_text().splitlines()[0],
            'frozen_mode':int(a['FROZEN_MODE'].flat[0]),
            'time_identity':{n:r[n].tolist() for n in r if 'TIME' in n or 'STEP' in n},
            'input_fields':list(a),'raw_fields':list(r),'result_sections':list(z['sections']),
            'cf0_omitted_grid_g_m2':{n:float(np.sum(r[n+'_OMITTED']))
                for n in ['RWP','SWP']},'clipped_ice_layers':layers,'pins':pins}

    post_path = ROOT/'build/udm-cu-corrected-winter-v1/daylight-serial-posthoc-v1.json'
    post = load(post_path)
    capture_dir = ROOT/'build/udm-cu-corrected-winter-v1/staged-daylight-serial-v3-final/ra37-column-serial-daylight/capture'
    winter = []
    for phase in ['lw','sw']:
        for row in post['capture_inventory'][phase]['all_capture_triples']:
            base = capture_dir/row['stem']
            winter.append(profile(base.with_suffix('.input'),base.with_suffix('.raw'),base.with_suffix('.result'),row))
    canonical_dir = ROOT/'build/udm-canonical-six-anchor-pr-work/validation/rrtmgp37/stratified-six-anchor-replay'
    inv = load(canonical_dir/'capture-hash-inventory.json')
    anchors = {}
    for name in ['cf0_rain_low_cloud_proxy','material_cf0_snow_daylight_proxy',
                 'ice_clip_low_cloud_proxy','ice_clip_high_cloud_proxy']:
        anchors[name] = []
        for phase in ['lw','sw']:
            paths = []
            for suffix in ['input','raw','result']:
                record = inv[name][phase+'.'+suffix]
                path = ROOT/record['original_workspace_path']
                checked(path,record['sha256']); assert path.stat().st_size == record['bytes']
                paths.append(path)
            anchors[name].append(profile(*paths))
    sw = load(ROOT/'build/udm-cu-actual-sw-replay-v1/run-20261003T113736Z/execution.json')
    existing_reference = []
    for key in ['reference_executable','reference_source','cloud_lw','cloud_sw','gas_lw','gas_sw','frozen_table']:
        record = sw['hashes'][key]
        existing_reference.append({'role':key,**checked(record['path'],record['sha256'])})
    assert pin(SUPPORT/'reference_column.f90')['sha256'] == sw['hashes']['reference_source']['sha256']
    source_comparison = []
    old = ROOT/'build/udm-cu-fresh-gnu-serial-v1/source'
    for rel in ['WRF/phys/module_ra_rrtmgp.F','WRF/phys/module_ra_rrtmgp_input.F',
      'WRF/phys/module_ra_rrtmgp_trace.F','WRF/phys/module_ra_rrtmgp_precip.F',
      'WRF/phys/module_ra_rrtmgp_frozen.F','WRF/external/rte_rrtmgp/rte-frontend/mo_optical_props.F90',
      'WRF/external/rte_rrtmgp/rte-frontend/mo_rte_scalar_math.F90']:
        now = pin(CURRENT/rel); prior = pin(old/rel) if (old/rel).exists() else None
        source_comparison.append({'file':rel,'current':now,'capture_source':prior,
           'equal':prior is not None and prior['sha256']==now['sha256']})
    evidence = [post_path, canonical_dir/'index.json',canonical_dir/'capture-hash-inventory.json',
      canonical_dir/'production-reference-data-pins.json',
      ROOT/'build/udm-cu-fresh-gnu-serial-v1/build-receipt.json',
      ROOT/'build/udm-cu-fresh-gnu-serial-v1/source-manifest.json',
      ROOT/'build/udm-cu-actual-sw-replay-v1/run-20261003T113736Z/execution.json',
      ROOT/'build/udm-cu-actual-sw-replay-v1/run-20261003T113736Z/duration-scope-erratum.json',
      ROOT/'build/udm-cu-actual-lw-replay-v1/run-20261003T201000Z/executable-generation-reconciliation.json',
      ROOT/'build/udm-cu-focused-v2/cu-population-replay/cu-population-replay-5mvqrwh3/receipt.json']
    # Reconciliation names the actual newer receipt; use its authoritative path.
    reconciliation = load(evidence[-2]); evidence[-1] = pathlib.Path(reconciliation['newer_receipt']['path'])
    evidence += [ROOT/'build/udm-cu-focused-v2/CMakeCache.txt',
       ROOT/'build/udm-cu-focused-v2/CMakeFiles/reference_column.dir/link.txt',
       ROOT/'build/udm-cu-focused-v2/rte_rrtmgp/CMakeFiles/wrf_rrtmgp.dir/flags.make']
    result = {'schema':'occurrence-clipping-held-capture-inventory-v1',
      'calls':{'new_models':0,'new_builds':0,'new_reference_calls':0},
      'current_head':'b66bd3724890c3d3a8d415e221a748309f93597e',
      'helper_pins':helper_pins,'existing_reference_pins':existing_reference,
      'source_compatibility':source_comparison,'external_evidence_pins':[pin(x) for x in evidence],
      'winter_inventory':winter,'winter_triples':{'LW':36,'SW':29},
      'winter_ice_only_clipped_population_layers':sum(y['ice_only_population_layer']
          for x in winter for y in x['clipped_ice_layers']), 'historical_anchors':anchors,
      'scope':'Historical exact-call held inputs, not current PR60 WRF trajectory or an out-of-LUT oracle. '
       'Daylight source run is six hours; reused earlier LW trajectory is separate. '
       'Native/CU result components combine liquid and ice; pure-ice contribution requires same-population LWP=0.'}
    for before in helper_pins:
        assert pin(ROOT/before['path']) == before
    OUT.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':'PASS_READ_ONLY_INVENTORY','inventory':pin(OUT),
       'winter_triples':65,'winter_clipped_ice_only':result['winter_ice_only_clipped_population_layers']}))

if __name__ == '__main__': main()
