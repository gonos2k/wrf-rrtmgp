#!/usr/bin/env python3
"""Import immutable upstream source snapshots; never overwrite an existing import.

This tool writes files locally. It neither commits nor pushes. Upstream license
files and executable bits are retained. Git submodules are materialized, not
replaced with empty directories. Coefficient data is limited to the listed files.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

SPECS = [
    {"path": "WRF", "repository": "wrf-model/WRF", "commit": "06d4240ae989cc3e50af412bb472df3d9048783c", "recursive": True},
    {"path": "external/rte-rrtmgp", "repository": "NCAR/rte-rrtmgp", "commit": "41c5fcd950fed09b8afe186dede266824eca7fd3", "recursive": True},
    {"path": "external/rrtmgp-data", "repository": "earth-system-radiation/rrtmgp-data", "commit": "aafa333a60c06fca2fbf219fbd17e7f432b43e3f", "recursive": False,
     "include": ["rrtmgp-gas-lw-g128.nc", "rrtmgp-gas-lw-g256.nc", "rrtmgp-gas-sw-g112.nc", "rrtmgp-gas-sw-g224.nc", "rrtmgp-clouds-lw.nc", "rrtmgp-clouds-sw.nc", "rrtmgp-aerosols-merra-lw.nc", "rrtmgp-aerosols-merra-sw.nc"]},
]

def run(args: list[str], cwd: Path | None = None) -> str:
    print("+", " ".join(args), flush=True)
    return subprocess.check_output(args, cwd=cwd, text=True, stderr=None).strip()

def inventory(root: Path) -> dict:
    records = []
    total = 0
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            records.append({"path": rel, "symlink": os.readlink(p)})
        elif p.is_file():
            size = p.stat().st_size
            if size >= 100 * 1024 * 1024:
                raise RuntimeError(f"FILE_EXCEEDS_GITHUB_LIMIT: {p} ({size})")
            digest = hashlib.sha256()
            with p.open("rb") as f:
                for block in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(block)
            records.append({"path": rel, "bytes": size, "sha256": digest.hexdigest(), "executable": bool(p.stat().st_mode & 0o111)})
            total += size
    return {"entries": records, "file_count": len(records), "bytes": total}

def main() -> None:
    root = Path(__file__).resolve().parents[1]
    receipt = root / "config/imported-sources.json"
    if receipt.exists():
        print("Existing import receipt found; source files are not overwritten.")
        return
    for spec in SPECS:
        if (root / spec["path"]).exists():
            raise RuntimeError(f"REFUSING_EXISTING_DESTINATION: {spec['path']}")
    manifests = []
    # Complete acquisition in a temporary staging area before publishing paths.
    with tempfile.TemporaryDirectory(prefix="wrf-rrtmgp-import-") as td:
        tmp = Path(td)
        for index, spec in enumerate(SPECS):
            checkout = tmp / f"checkout-{index}"
            staged = tmp / f"staged-{index}"
            run(["git", "init", str(checkout)])
            run(["git", "remote", "add", "origin", f"https://github.com/{spec['repository']}.git"], checkout)
            run(["git", "fetch", "--depth=1", "origin", spec["commit"]], checkout)
            run(["git", "checkout", "--detach", "FETCH_HEAD"], checkout)
            if run(["git", "rev-parse", "HEAD"], checkout) != spec["commit"]:
                raise RuntimeError("UPSTREAM_COMMIT_MISMATCH")
            if spec["recursive"]:
                run(["git", "-c", "protocol.file.allow=never", "submodule", "update", "--init", "--recursive", "--depth=1"], checkout)
            submodules = run(["git", "submodule", "status", "--recursive"], checkout)
            if any(line.startswith(("-", "+", "U")) for line in submodules.splitlines()):
                raise RuntimeError("UNINITIALIZED_OR_MISMATCHED_SUBMODULE")
            if "include" not in spec:
                shutil.copytree(checkout, staged, symlinks=True, ignore=shutil.ignore_patterns(".git"))
            else:
                staged.mkdir()
                names = set(spec["include"])
                names.update(p.name for p in checkout.iterdir() if p.is_file() and (p.name.lower().startswith(("license", "copying", "readme"))))
                for name in sorted(names):
                    src = checkout / name
                    if not src.is_file() or src.is_symlink():
                        raise RuntimeError(f"MISSING_REQUIRED_DATA_FILE: {name}")
                    shutil.copy2(src, staged / name)
            inv = inventory(staged)
            manifests.append({**spec, "tree": run(["git", "rev-parse", "HEAD^{tree}"], checkout), "submodules": submodules.splitlines(), **inv})
        for index, spec in enumerate(SPECS):
            destination = root / spec["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(tmp / f"staged-{index}"), destination)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"schema": 1, "sources": manifests, "wrf_option_37_enabled": False}, indent=2) + "\n")
    for source in manifests:
        print(f"IMPORTED {source['path']}: {source['file_count']} entries, {source['bytes']} bytes, {source['commit']}")
    print("UPSTREAM_IMPORT_COMPLETE__BACKEND_NOT_ENABLED")

if __name__ == "__main__":
    main()
