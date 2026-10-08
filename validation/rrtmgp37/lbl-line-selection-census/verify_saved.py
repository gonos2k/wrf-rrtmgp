"""Verify sealed root census and hashed rosters, not private full raw data."""
from pathlib import Path
import gzip, hashlib, importlib.util, json
BASE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('roster_core',BASE/'verify_core.py')
core = importlib.util.module_from_spec(spec); spec.loader.exec_module(core)

def load():
    parent = BASE.parent/'lbl-coupling-generation'
    return (json.loads((BASE/'readback.json').read_text()),json.loads((BASE/'controls.json').read_text()),
            gzip.decompress((BASE/'source-roster.bin.gz').read_bytes()),
            gzip.decompress((BASE/'TAPE3-roster.bin.gz').read_bytes()),
            (BASE/'logs/LNFL_TAPE5').read_bytes(),(BASE/'logs/LNFL_TAPE6').read_bytes(),
            gzip.decompress((parent/'excerpts/line_data.bin.gz').read_bytes()))

def main():
    manifest = json.loads((BASE/'manifest.json').read_text())
    actual = {str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file() and p!=BASE/'manifest.json' and '__pycache__' not in p.parts}
    core.require(len(manifest['files'])==len(actual) and {x['path'] for x in manifest['files']}==actual,'exact package roster')
    core.require(manifest['production_accepted'] is False,'manifest physical gate')
    for row in manifest['files']:
        b = (BASE/row['path']).read_bytes()
        core.require(len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'],'pinned package bytes')
    result = core.verify(*load())
    core.require(result==json.loads((BASE/'result.json').read_text()),'declared result')
    print(json.dumps(result))

if __name__ == '__main__': main()
