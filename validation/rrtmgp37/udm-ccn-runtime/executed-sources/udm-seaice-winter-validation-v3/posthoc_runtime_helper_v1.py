#!/usr/bin/env python3
"""Pinned adapter: original helper plus explicit live posthoc build eligibility."""
import ast as _ast,hashlib as _hashlib,importlib.util as _importlib,json as _json
from pathlib import Path as _Path
_HERE=_Path(__file__).resolve().parent
_COMMON=_HERE.parent/'udm-seaice-winter-validation-v1/winter_validation_v1.py'
_COMMON_SHA='6f66046e785fc5ef69f317daa3ca63a09a4cfab0839a67bea9703ce21691a4e8'
_VERIFIER=_HERE.parent/'udm-seaice-fresh-gnu-dm-sm-v1/posthoc-build-verifier-v1.py'
_VERIFIER_SHA='201d906a1ac31590d4a79ba3a396cda225fa1e269507445d47f830da87b03cc2'
_ATTESTATION={'path':str(_HERE.parent/'udm-seaice-fresh-gnu-dm-sm-v1/posthoc-build-attestation-v1.json'),'size_bytes':6185,'sha256':'6ab254abda1997fe2a4b5e713f59d178e51247859530699a6803c005ff3d9fa5'}


def _load(path,sha,name):
    if _hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError(name+' changed before import')
    spec=_importlib.spec_from_file_location(name,path);module=_importlib.module_from_spec(spec);spec.loader.exec_module(module)
    if _hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError(name+' changed after import')
    return module


_original=_load(_COMMON,_COMMON_SHA,'frozen_seaice_original_common')
# Restore the sole omitted data binding from the pinned, actually executed runner.
_INPUTS_SOURCE=_HERE.parent/'udm-cu-winter24h-v1/prepare_winter24h_ra4_v3.py'
_INPUTS_SOURCE_SHA='7298cb3f1b5902ae84046bcd064c712654d5e8a1080bea3f79ba81da21382a00'
if _hashlib.sha256(_INPUTS_SOURCE.read_bytes()).hexdigest()!=_INPUTS_SOURCE_SHA:raise ValueError('historical INPUTS provenance changed')
_inputs_assignments=[node for node in _ast.parse(_INPUTS_SOURCE.read_text()).body if isinstance(node,_ast.Assign) and any(isinstance(target,_ast.Name) and target.id=='INPUTS' for target in node.targets)]
if len(_inputs_assignments)!=1:raise ValueError('missing or ambiguous historical INPUTS binding')
_inputs_value=_ast.literal_eval(_inputs_assignments[0].value)
if _inputs_value!=('wrfinput_d01','wrfbdy_d01','radiation_iofields.txt'):raise ValueError('historical INPUTS contract differs')
if hasattr(_original,'INPUTS'):raise ValueError('unexpected existing original INPUTS; adapter revision required')
_original.INPUTS=_inputs_value

_posthoc=_load(_VERIFIER,_VERIFIER_SHA,'pinned_seaice_posthoc_verifier')
# Export all original public objects; their functions retain original ROOT/globals.
for _name,_value in vars(_original).items():
    if not _name.startswith('_'):globals()[_name]=_value


def build_integrity(build_pin):
    """Return original metadata/status with explicit separately verified eligibility."""
    if build_pin['path']!=str(_posthoc.ORIGINAL.resolve()) or build_pin['sha256']!=_posthoc.ORIGINAL_SHA:
        raise ValueError('requires exact preserved original FAIL receipt')
    _original.check_pin(build_pin)
    if _original.digest(_VERIFIER)!=_VERIFIER_SHA:raise ValueError('posthoc verifier changed')
    live=_posthoc.verify_attestation(_ATTESTATION)
    b=_json.loads(_posthoc.ORIGINAL.read_text())
    if b['status']!='BUILD_FAIL_PRESERVED' or live['original_receipt']!=build_pin:
        raise ValueError('original failed receipt context differs')
    b['build_attestation_context']={'eligibility_status':'BUILD_PASS_POSTHOC_ATTESTED','original_status':b['status'],
        'original_receipt':build_pin,'attestation':dict(_ATTESTATION),'verifier':_original.pin(_VERIFIER),
        'runtime_adapter':_original.pin(_Path(__file__)),'original_common':_original.pin(_COMMON),
        'live_attestation_recomputed':True}
    return b
