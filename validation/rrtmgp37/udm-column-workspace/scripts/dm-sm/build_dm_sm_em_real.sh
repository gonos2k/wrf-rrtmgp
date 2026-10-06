#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP"
SOURCE_ROOT="$REPO_ROOT/build/udm-workspace-dm-sm-candidate"
WRF_ROOT="$SOURCE_ROOT/WRF"
NETCDF_PREFIX="$REPO_ROOT/build/deps/netcdf"
MPI_PREFIX="$REPO_ROOT/build/deps/mpich-sock"
LOCK_FILE="$TASK_ROOT/build.lock"
CONFIGURE_LOG="$TASK_ROOT/configure-dm-sm35.log"
BUILD_LOG="$TASK_ROOT/build-em_real.log"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then echo "another build holds $LOCK_FILE" >&2; exit 99; fi
if [[ ! -f "$TASK_ROOT/stage-receipt.json" || ! -f "$TASK_ROOT/source-manifest.json" ]]; then
  echo "staging receipt/source manifest missing" >&2; exit 2
fi
python3 - "$TASK_ROOT/source-manifest.json" "$SOURCE_ROOT" <<'PY'
import hashlib,json,sys
from pathlib import Path
manifest=json.loads(Path(sys.argv[1]).read_text()); root=Path(sys.argv[2])
for e in manifest['files']:
    p=root/e['path']
    if e['kind']=='symlink':
        if not p.is_symlink() or p.readlink().as_posix()!=e['target']:
            raise SystemExit(f"staged symlink changed: {e['path']}")
        h=hashlib.sha256(e['target'].encode()).hexdigest()
    else:
        if not p.is_file() or p.stat().st_size!=e['bytes']:
            raise SystemExit(f"staged file missing/size changed: {e['path']}")
        d=hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda:f.read(1<<20),b''): d.update(block)
        h=d.hexdigest()
    if h!=e['sha256']: raise SystemExit(f"staged bytes changed: {e['path']}")
PY
cd "$WRF_ROOT"
rm -f configure.wrf
set +e
printf '35\n1\n' | env PATH="$MPI_PREFIX/bin:/home/korea_keun/.local/bin:/usr/bin:/bin:$PATH" NETCDF="$NETCDF_PREFIX" NETCDF_classic=1 LD_LIBRARY_PATH="$NETCDF_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ./configure >"$CONFIGURE_LOG" 2>&1
configure_rc=$?
set -e
if [[ $configure_rc -ne 0 ]]; then
  echo "configure failed with $configure_rc; see $CONFIGURE_LOG" >&2
  exit "$configure_rc"
fi
if ! grep -q '# Compiler choice: 35' configure.wrf || ! grep -q '# Nesting option: 1' configure.wrf || ! grep -qE '^DMPARALLEL[[:space:]]*=[[:space:]]*1' configure.wrf || ! grep -qE '^OMP[[:space:]]*=[[:space:]]*-fopenmp' configure.wrf; then
  echo "configure.wrf does not show GNU dm+sm, nesting 1 settings" >&2
  exit 3
fi
python3 - <<'PYCONFIG'
from pathlib import Path
p=Path('configure.wrf');s=p.read_text();s=s.replace('DM_CC           =       mpicc -cc=$(SCC)', 'DM_CC           =       mpicc ');p.write_text(s)
PYCONFIG
cmp configure.wrf "$REPO_ROOT/build/udm-selected-dm-sm-baseline/WRF/configure.wrf"
set +e
env PATH="$MPI_PREFIX/bin:/home/korea_keun/.local/bin:/usr/bin:/bin:$PATH" NETCDF="$NETCDF_PREFIX" NETCDF_classic=1 LD_LIBRARY_PATH="$NETCDF_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" OMP_NUM_THREADS=1 csh -f ./compile -j 12 em_real >"$BUILD_LOG" 2>&1
build_rc=$?
set -e
python3 - "$TASK_ROOT" "$configure_rc" "$build_rc" <<'PY'
import hashlib,json,sys,subprocess
from pathlib import Path
task=Path(sys.argv[1]); cfg_rc=int(sys.argv[2]); build_rc=int(sys.argv[3])
source=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/udm-workspace-dm-sm-candidate'); wrf=source/'WRF'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
manifest=json.loads((task/'source-manifest.json').read_text())
changed=[]
for e in manifest['files']:
 p=source/e['path']
 if e['kind']=='symlink':
  actual=hashlib.sha256(p.readlink().as_posix().encode()).hexdigest() if p.is_symlink() else None
 else:
  actual=sha(p) if p.is_file() else None
 if actual!=e['sha256']: changed.append({'path':e['path'],'expected':e['sha256'],'actual':actual})
configs=wrf/'configure.wrf'
exes={}
for name in ('wrf.exe','real.exe'):
 p=wrf/'main'/name
 exes[name]={'exists':p.is_file(),'sha256':sha(p) if p.is_file() else None,'bytes':p.stat().st_size if p.is_file() else None}
log=task/'build-em_real.log'; clog=task/'configure-dm-sm35.log'
obj={'status':'BUILD_PASS' if cfg_rc==0 and build_rc==0 and exes['wrf.exe']['exists'] and not changed else 'BUILD_FAIL','configure_exit_code':cfg_rc,'build_exit_code':build_rc,'base_commit':json.loads((task/'stage-receipt.json').read_text())['base_commit'],'stage_receipt_sha256':sha(task/'stage-receipt.json'),'source_manifest_sha256':sha(task/'source-manifest.json'),'source_files_modified_or_missing_during_build':changed,'configure_sha256':sha(configs) if configs.is_file() else None,'configure_log_sha256':sha(clog) if clog.is_file() else None,'build_log_sha256':sha(log) if log.is_file() else None,'compiler':subprocess.run(['gfortran','--version'],text=True,capture_output=True).stdout.splitlines()[0],'netcdf_prefix':'/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps/netcdf','configure_choice':'35 (GNU dm+sm), nesting 1','build_command':'csh -f ./compile -j 12 em_real','executables':exes}
(task/'build-receipt.json').write_text(json.dumps(obj,indent=2)+'\n')
print(json.dumps(obj,indent=2))
if obj['status']!='BUILD_PASS': raise SystemExit(1)
PY
