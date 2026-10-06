#!/usr/bin/env python3
"""Cross-check the RealK-adapted SOCRATES Mie bridge against miepython.

This is a numerical regression check for weak-absorption Mie efficiencies. It
does not validate the frozen-hydrometeor optical model or generated band table.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import sys

# Choose the independent pure-Python implementation before importing it.
os.environ['MIEPYTHON_USE_JIT'] = '0'

import miepython

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPECTED_MIEPYTHON_VERSION = '3.0.2'
EXPECTED_MIE_NOJIT_SHA256 = '9ba345cb42e5385b8f6ae6866f7291919ce5f8a32a7e4f05949ec0a05f31665f'
ATOL = 2.0e-9
RTOL = 2.0e-9
MAX_TERMS = 32_000_000

# The 16 fixtures are the largest absolute Qsca-Qext violations from the
# original default-COMPLEX SOCRATES bridge during the all-SW GL32 scan at
# lambda=20000 m-1. Their original outputs are retained for provenance.
# Tuple: label, band, wavenumber, Laguerre u, n, k, x, original Qext, Qsca.
WEAK_ABSORPTION_FIXTURES = [
    ('orig_worst_01', 12, 26250.0, .044489365833267014, 1.3212977752683328, 2.000000000000001e-11, 18.344479763486675, 2.627687923899289, 2.627687989623038),
    ('orig_worst_02', 12, 25600.0, .044489365833267014, 1.3202430774879417, 2.0213171793268426e-11, 17.89023550267653, 2.6065031142443793, 2.6065031786044552),
    ('orig_worst_03', 13, 33100.0, .044489365833267014, 1.3334898718416064, 2.000000000000001e-11, 23.131515435101296, 2.188714642667646, 2.1887147066224117),
    ('orig_worst_04', 14, 41200.0, .044489365833267014, 1.3558503886307434, 2.000000000000001e-11, 28.792097762120044, 1.935690455042163, 1.9356905145492485),
    ('orig_worst_05', 14, 43300.0, .044489365833267014, 1.3641763516673038, 2.000000000000001e-11, 30.259656143198978, 2.2196124223988485, 2.219612481050473),
    ('orig_worst_06', 13, 32100.0, .044489365833267014, 1.3316987978707824, 2.000000000000001e-11, 22.432678110777996, 2.1585927814472674, 2.158592837255549),
    ('orig_worst_07', 12, 26700.0, .044489365833267014, 1.3220203171890663, 2.000000000000001e-11, 18.658956559432163, 2.427843096493493, 2.427843152025161),
    ('orig_worst_08', 13, 33500.0, .044489365833267014, 1.3343650476179485, 2.000000000000001e-11, 23.411050364830615, 2.213896480686111, 2.21389653503785),
    ('orig_worst_09', 13, 35650.0, .044489365833267014, 1.3401650366872218, 2.000000000000001e-11, 24.913550612125714, 2.520795768705988, 2.5207958230567904),
    ('orig_worst_10', 14, 40250.0, .044489365833267014, 1.3519434672689639, 2.000000000000001e-11, 28.128202304012905, 1.9818540753467675, 1.9818541293585397),
    ('orig_worst_11', 12, 25250.0, .044489365833267014, 1.3197537153679895, 2.2142112358734384e-11, 17.645642439163375, 2.813618174514836, 2.81361822831942),
    ('orig_worst_12', 12, 23900.0, .044489365833267014, 1.3178259148084404, 3.0565920176795446e-11, 16.702212051326917, 2.8542812211073576, 2.8542812738745),
    ('orig_worst_13', 14, 38700.0, .044489365833267014, 1.3478193027461687, 2.000000000000001e-11, 27.045004451311787, 2.371707337126647, 2.371707389273413),
    ('orig_worst_14', 14, 39100.0, .044489365833267014, 1.348778096326691, 2.000000000000001e-11, 27.324539381041106, 2.1145690417133847, 2.114569093011925),
    ('orig_worst_15', 12, 27300.0, .044489365833267014, 1.3229649899817617, 2.000000000000001e-11, 19.078258954026143, 2.372960782569174, 2.372960833771439),
    ('orig_worst_16', 13, 30150.0, .044489365833267014, 1.328039780840841, 2.000000000000001e-11, 21.069945328347554, 1.841945579361134, 1.8419456296675065),
]

# The first is the generator failure that triggered the investigation. The
# general fixtures below span absorption, refractive index and size.
ADDITIONAL_FIXTURES = [
    ('reported_generator_failure', 12, 22650.0, .044489365833267014,
     1.3162090691501627, 6.647598667764746e-11, 15.82866539592279,
     2.745629741719146, 2.74562975138284),
]
GENERAL_FIXTURES = [
    ('general_absorbing_x100', 1.5, 1.0, 100.0),
    ('general_large_index_x1', 10.0, 10.0, 1.0),
    ('general_weak_absorption_x1e5', 1.31, 1.e-8, 1.e5),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_generator():
    sys.path.insert(0, str(HERE))
    import generate
    return generate


def bind_library(path: Path):
    library = ctypes.CDLL(str(path))
    library.mie_checked.argtypes = [ctypes.c_double] * 3 + [ctypes.c_int] + \
        [ctypes.POINTER(ctypes.c_double)] * 3 + [ctypes.POINTER(ctypes.c_int)] * 2
    return library


def evaluate(library, n: float, k: float, x: float) -> dict:
    qext, qsca, asym = ctypes.c_double(), ctypes.c_double(), ctypes.c_double()
    needed, status = ctypes.c_int(), ctypes.c_int()
    library.mie_checked(n, k, x, MAX_TERMS, ctypes.byref(qext), ctypes.byref(qsca),
                        ctypes.byref(asym), ctypes.byref(needed), ctypes.byref(status))
    if status.value != 0:
        raise RuntimeError(f'SOCRATES Mie status={status.value}; needed={needed.value}; x={x}')
    return {'Qext': qext.value, 'Qsca': qsca.value, 'g': asym.value,
            'needed_terms': needed.value}


def compare(label: str, n: float, k: float, x: float, library,
            source_context: dict | None = None) -> dict:
    # SOCRATES takes positive k; miepython documents m=n-ik.
    actual = evaluate(library, n, k, x)
    reference = miepython.efficiencies_mx(complex(n, -k), x)
    expected = {'Qext': float(reference[0]), 'Qsca': float(reference[1]),
                'g': float(reference[3])}
    errors = {key: actual[key] - expected[key] for key in expected}
    limits = {key: ATOL + RTOL * abs(expected[key]) for key in expected}
    for key in expected:
        if not math.isfinite(actual[key]) or not math.isfinite(expected[key]):
            raise AssertionError(f'{label}: nonfinite {key}')
        if abs(errors[key]) > limits[key]:
            raise AssertionError(f'{label}: {key} error {errors[key]} exceeds {limits[key]}')
    if not actual['Qext'] >= actual['Qsca']:
        raise AssertionError(f'{label}: Qsca exceeds Qext: {actual}')
    if not actual['Qext'] >= 0 or not actual['Qsca'] >= 0 or not -1 <= actual['g'] <= 1:
        raise AssertionError(f'{label}: nonphysical output: {actual}')
    return {'label': label, 'n': n, 'k': k, 'x': x,
            'source_context': source_context or {}, 'socrates': actual,
            'miepython': expected, 'socrates_minus_miepython': errors,
            'component_tolerance': limits}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True,
                        help='new isolated directory for compiled library and result receipt')
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists():
        parser.error(f'output directory already exists; preserve evidence and choose a new path: {output}')
    if miepython.__version__ != EXPECTED_MIEPYTHON_VERSION:
        parser.error(f'requires miepython=={EXPECTED_MIEPYTHON_VERSION}, found {miepython.__version__}')
    independent_module = Path(miepython.__file__).resolve().parent / 'mie_nojit.py'
    if sha256(independent_module) != EXPECTED_MIE_NOJIT_SHA256:
        parser.error(f'pinned miepython mie_nojit.py hash mismatch: {independent_module}')
    if miepython.USE_JIT:
        parser.error('MIEPYTHON_USE_JIT=0 must select the pure-Python reference implementation')

    output.mkdir(parents=True)
    generator = load_generator()
    script_hash_before = sha256(Path(__file__).resolve())
    generator_hash_before = sha256(HERE / 'generate.py')
    independent_hashes_before = {str(p): sha256(p) for p in sorted(independent_module.parent.rglob('*.py'))}
    library_path, pinned_hashes = generator.build_kernel(output / 'kernel')
    library = bind_library(library_path)
    results = []
    for row in WEAK_ABSORPTION_FIXTURES + ADDITIONAL_FIXTURES:
        label, band, wn, u, n, k, x, original_qext, original_qsca = row
        results.append(compare(label, n, k, x, library,
            {'band_1based': band, 'wavenumber_cm-1': wn, 'laguerre_u': u,
             'original_default_complex_Qext': original_qext,
             'original_default_complex_Qsca': original_qsca,
             'original_Qsca_minus_Qext': original_qsca-original_qext}))
    for label, n, k, x in GENERAL_FIXTURES:
        results.append(compare(label, n, k, x, library))

    script_path = Path(__file__).resolve()
    generator_path = HERE / 'generate.py'
    adapted_path = output / 'kernel/mie_scatter_realK.f'
    adaptation_path = output / 'kernel/source-adaptation.json'
    if sha256(script_path) != script_hash_before:
        raise RuntimeError('independent check script changed while executing')
    if sha256(generator_path) != generator_hash_before or any(
            sha256(ROOT / p) != value for p,value in pinned_hashes.items()):
        raise RuntimeError('Generator or kernel source changed while executing')
    if any(sha256(Path(p)) != value for p,value in independent_hashes_before.items()):
        raise RuntimeError('Independent implementation source changed while executing')
    receipt = {
        'status': 'PASS',
        'scope': 'SOCRATES RealK Mie C-API cross-checked at fixed weak-absorption and general fixtures; no PSD/band-table/model validation',
        'independent_implementation': {
            'package': 'miepython', 'version': miepython.__version__,
            'MIEPYTHON_USE_JIT': os.environ.get('MIEPYTHON_USE_JIT'),
            'USE_JIT': bool(miepython.USE_JIT),
            'reference_convention': 'miepython uses m=n-ik; SOCRATES bridge accepts positive k and constructs n+ik',
            'mie_nojit_py_sha256': sha256(independent_module),
            'core_py_sha256': sha256(independent_module.with_name('core.py')),
            'source_tree_sha256': {str(p.relative_to(independent_module.parent)): sha256(p)
                                   for p in sorted(independent_module.parent.rglob('*.py'))}},
        'SOCRATES': {
            'source_commit': json.loads((HERE / 'SOURCE.json').read_text())['commit'],
            'source_manifest_sha256': sha256(HERE / 'SOURCE.json'),
            'generator_sha256': sha256(generator_path),
            'independent_check_sha256': script_hash_before,
            'pinned_sources_sha256': pinned_hashes,
            'local_compiled_adaptation': json.loads(adaptation_path.read_text()),
            'compiled_adapted_source_sha256': sha256(adapted_path),
            'library_sha256': sha256(library_path),
            'adaptation_policy': 'Only four CMPLX constructors explicitly specify KIND=RealK; original pinned vendored source remains byte-identical.'},
        'comparison_tolerances': {'atol': ATOL, 'rtol': RTOL,
                                  'formula': 'abs(SOCRATES-reference) <= atol + rtol*abs(reference)'},
        'fixture_counts': {'original_weak_absorption_violators': len(WEAK_ABSORPTION_FIXTURES),
                           'additional_weak_absorption_failure': len(ADDITIONAL_FIXTURES),
                           'general_regressions': len(GENERAL_FIXTURES)},
        'results': results,
        'max_abs_error': {key: max(abs(row['socrates_minus_miepython'][key]) for row in results)
                          for key in ('Qext', 'Qsca', 'g')},
        'limits': ['Fixed fixtures reproduce representative near-transparent failures and independent Mie comparisons; they do not constitute a broad precision proof.',
                   'miepython and SOCRATES are distinct implementations of the same Mie theory; agreement is not physical validation of the selected ice material or PSD.',
                   'No frozen optical coefficient table is generated by this check.']}
    result_path = output / 'independent_mie_check.json'
    result_path.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'status': receipt['status'], 'fixtures': len(results),
                      'max_abs_error': receipt['max_abs_error'],
                      'result': str(result_path), 'library_sha256': receipt['SOCRATES']['library_sha256']},
                     indent=2))


if __name__ == '__main__':
    main()
