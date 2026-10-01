#!/usr/bin/env python3
"""One-time exact migration of 15 prior numerical source files; no code execution."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

ROOT = Path(__file__).resolve().parents[1]
SHA256 = '26921448eaf9a573964bd9abdc48ddd87ea65953b0d21e4da44a4e8f663fe8a9'
PARTS = ['00', '01', '02', '03', '04', '05a', '05b']

def main():
    receipt = ROOT / 'config/numerical-seed.json'
    if receipt.exists():
        print('Numerical seed already imported; existing code is not overwritten.')
        return
    packed = b''.join((ROOT / ('migration/seed.' + part)).read_bytes() for part in PARTS)
    if len(packed) != 22314 or hashlib.sha256(packed).hexdigest() != SHA256:
        raise ValueError('MIGRATION_ARCHIVE_INTEGRITY_FAILURE')
    staged = {}
    with tarfile.open(fileobj=io.BytesIO(packed), mode='r:gz') as archive:
        members = archive.getmembers()
        if len(members) != 15 or sum(m.size for m in members) != 91270:
            raise ValueError('MIGRATION_FILE_COUNT_OR_SIZE')
        for member in members:
            p = PurePosixPath(member.name)
            if not member.isfile() or len(p.parts) != 3 or p.parts[0] != 'port' or p.parts[1] not in ('src', 'integration', 'tests'):
                raise ValueError('UNSAFE_MIGRATION_MEMBER')
            if '..' in p.parts or p.is_absolute() or member.name in staged:
                raise ValueError('INVALID_MIGRATION_PATH')
            destination = ROOT / member.name
            if destination.exists() or destination.is_symlink():
                raise ValueError('REFUSING_EXISTING_SOURCE: ' + member.name)
            data = archive.extractfile(member).read()
            data.decode('utf-8')
            staged[member.name] = data
    manifest = []
    for name, data in staged.items():
        p = ROOT / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        manifest.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({'archive_sha256': SHA256, 'origin': 'wrf_rrtmgp37_allocation_20261001 prior numerical sources', 'files': manifest, 'scope': 'Previous unit-tested components and previously uncompiled real-core candidates; NOT WRF forecast approval'}, indent=2) + '\n')
    print('MIGRATED_NUMERICAL_SOURCE_FILES=15')

if __name__ == '__main__':
    main()
