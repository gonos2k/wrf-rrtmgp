#!/usr/bin/env python3
"""Authenticate saved source-extracted UDM contract evidence without execution."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[2]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pin(path):
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def checked_path(root, name):
    require(isinstance(name, str) and name and not Path(name).is_absolute()
            and ".." not in Path(name).parts, f"unsafe path: {name!r}")
    path = root / name
    require(path.is_file() and not path.is_symlink(), f"missing/nonregular file: {name}")
    require(path.resolve().is_relative_to(root.resolve()), f"escaped root: {name}")
    return path


def authenticate(root, rows):
    names = [r["path"] for r in rows]
    require(len(names) == len(set(names)), "duplicate pin")
    for row in rows:
        require(set(row) == {"path", "sha256", "size_bytes"}, "pin fields")
        require(pin(checked_path(root, row["path"])) ==
                {k: row[k] for k in ("sha256", "size_bytes")},
                f"pin changed: {row['path']}")
    return set(names)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-root", type=Path, default=REPO)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    require(manifest["schema"] == "UDM_ACTIVATION_DENSITY_EVIDENCE_V1", "schema")
    names = authenticate(PACKAGE, manifest["payload"])
    roster = {p.relative_to(PACKAGE).as_posix() for p in PACKAGE.rglob("*")
              if p.is_file() and p != PACKAGE / "manifest.json"
              and "__pycache__" not in p.parts}
    require(names == roster, "payload roster changed")
    authenticate(args.source_root, manifest["sources"])
    archives = manifest['text_archives']
    require(len(archives) == len(set(archives)) and set(archives) <= names,
            'invalid text archive roster')
    archived_files = 0
    for name in archives:
        archive = json.loads(gzip.decompress(checked_path(PACKAGE, name).read_bytes()))
        require(archive['schema'] == 'UDM_CONTRACT_TEXT_ARTIFACT_ARCHIVE_V1',
                'text archive schema')
        file_names = [row['path'] for row in archive['files']]
        require(len(file_names) == len(set(file_names)), 'duplicate archive file')
        for row in archive['files']:
            require(set(row) == {'path', 'sha256', 'size_bytes', 'content_utf8'},
                    'archive row format')
            rel = row['path']
            require(isinstance(rel, str) and rel and not Path(rel).is_absolute()
                    and '..' not in Path(rel).parts, 'unsafe archive path')
            data = row['content_utf8'].encode('utf-8')
            require(len(data) == row['size_bytes']
                    and hashlib.sha256(data).hexdigest() == row['sha256'],
                    f'archive content changed: {rel}')
        archived_files += len(file_names)
    result = {
        "schema": "UDM_ACTIVATION_DENSITY_ARCHIVE_RECEIPT_V1",
        "status": "PASS_SCOPED_ARCHIVE_AUTHENTICATION",
        "manifest_sha256": pin(PACKAGE / "manifest.json")["sha256"],
        "authenticated_payloads": len(names),
        "authenticated_sources": len(manifest["sources"]),
        "authenticated_archived_text_files": archived_files,
        "execution_counts": {"compiler": 0, "WRF": 0, "RTE": 0},
        "scope": "Authentication of saved evidence. No observed density-error magnitude, incoming-number authority or physical correction is established.",
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
