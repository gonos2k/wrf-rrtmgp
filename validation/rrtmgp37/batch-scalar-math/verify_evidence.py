#!/usr/bin/env python3
"""Offline integrity checker. Does not build or invoke WRF/RRTMGP."""
from pathlib import Path
import hashlib, json, struct, sys
ROOT=Path(__file__).resolve().parent

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''): h.update(chunk)
    return h.hexdigest()
def load(rel): return json.loads((ROOT/rel).read_text())
def check(ok,msg):
    if not ok: raise SystemExit('FAIL: '+msg)
index=load('artifact-index.json')
for rel,entry in index['artifacts'].items():
    p=ROOT/rel
    check(p.is_file(),f'missing artifact {rel}')
    check(p.stat().st_size==entry['bytes'],f'byte length differs: {rel}')
    check(sha(p)==entry['sha256'],f'SHA256 differs: {rel}')
summary=load('summary.json')
check(summary['base_commit']=='de312b7a53cefc2f69024e8b96de4bd586f00816','base commit changed')
check(summary['inputs']['all_64_original_capture_rows_inputs_and_headers_match'],'64-capture fixture readback not PASS')
check(summary['inputs']['independent_input_checks']==1856,'fixture check count')
check(summary['default_math_wp_comparison']['first_differing_stage']=='GAS_TAU','default math first stage')
check(summary['log_only_counterfactual']['first_remaining_stage']=='CLEAR_FU','log-only remaining stage')
check(summary['joint_log_exp_counterfactual']['all_12_WP_sections_bitwise_equal'],'joint WP equality')
check(summary['coupled_forecast_history']['first_nonheating_field_difference']=='W at 12:06','coupled timing interpretation')
# Verify original oracle payloads independently, including exact one-ULP location.
b= (ROOT/'fixtures/expected-batch32.bin').read_bytes(); s=(ROOT/'fixtures/expected-scalar32.bin').read_bytes()
check(len(b)==36608 and len(s)==36608,'output oracle lengths')
check(sha(ROOT/'fixtures/expected-batch32.bin')=='a9fd0da25b9b41de77a6e9724d50ea38f3681fd1b275371f05290c1bf75617ad','batch oracle SHA')
check(sha(ROOT/'fixtures/expected-scalar32.bin')=='a29c335dd9d24dffdadc0d2f8cc63ff4d7829fd6542a92ce03240e1dff6df0f2','scalar oracle SHA')
words_b=struct.unpack('>'+('I'*(len(b)//4)),b); words_s=struct.unpack('>'+('I'*(len(s)//4)),s)
# Fortran stream: UP(32x48), DN(32x48), HR(32x47), UPC, DNC, HRC.
hr=32*48*2; hrc=hr+32*47+32*48*2
idx=32*38
check(words_b[hr+idx]==0xbf91ab9c and words_s[hr+idx]==0xbf91ab9b,'HR target bits')
check(words_b[hrc+idx]==0xbf91ab9c and words_s[hrc+idx]==0xbf91ab9b,'HRC target bits')
changed=[i for i,(x,y) in enumerate(zip(words_b,words_s)) if x!=y]
check(changed==[hr+idx,hrc+idx],f'expected only HR/HRC bit differences, got {changed}')
# Recheck experiment receipts without rerunning either engine.
log=load('receipts/log-only-run.json'); joint=load('receipts/joint-shim-run.json')
check(log['status']=='PASS_ANALYZED' and log['pins_unchanged'],'log-only receipt')
check(joint['status']=='PASS_ANALYZED' and joint['pins_unchanged'],'joint receipt')
check(joint['wp_comparison']['first_differing_stage'] is None,'joint first stage should be none')
check(all(x['returncode']==0 and not x['timed_out'] for x in joint['runs'].values()),'joint process status')
for rel in ('receipts/fixture-v1-ordering-failure.json','receipts/log-only-ldd-preflight-failure.json','receipts/joint-shim-initial-preflight-failure.json'):
    check((ROOT/rel).is_file(),f'preserved failure receipt missing: {rel}')
# Disallow bulky/ephemeral raw solver outputs, libraries and model files.
for p in ROOT.rglob('*'):
    if not p.is_file(): continue
    check(p.suffix.lower() not in {'.nc','.exe','.o','.mod','.hex'},f'ephemeral/bulky file present: {p.relative_to(ROOT)}')
print(f"PASS: {len(index['artifacts'])} indexed files; exact fixtures/oracles, receipts and scope markers verified; no engine calls")
