#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
case_name=${1:?case required}
case "$case_name" in
  restart12-fixed-mpi1) ranks=1 ;;
  restart12-fixed-mpi4) ranks=4 ;;
  *) echo "unsupported case $case_name" >&2; exit 64 ;;
esac
RUN="$ROOT/$case_name"
SRC="$(cd "$ROOT/../source/WRF" && pwd)"
DEPS=/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP/build/deps
EXPECTED_EXE=176f589d657ca87df670cef3429d7474e674f3e44445eb7886aed871e36bef8f
EXPECTED_SOURCE=7564be3e5ad7b26ffc00c2680eb632745850baeac01529d48d6bc8393cb9e53d
EXPECTED_NML=330147a57cbd26506e4a9553b53b9f024542d2e5f1ede7c290ebef3ae27b0599
EXPECTED_RST=943a53db058f2d9560c6f0d571f3ff9bb8efb407010c5eea2026922a6eeee7b8
exec 9>"$ROOT/run.lock"
flock -n 9 || { echo "another fixed-source case holds run.lock" >&2; exit 73; }
sha() { sha256sum "$1" | awk '{print $1}'; }
verify_assets() {
  python3 - "$ROOT/prepared-assets.json" "$case_name" <<'PY'
import hashlib,json,sys
from pathlib import Path
obj=json.loads(Path(sys.argv[1]).read_text()); case=sys.argv[2]
rows=[r for r in obj['rows'] if r['case']==case]
if len(rows)!=88: raise SystemExit(f'expected 88 verified input links, got {len(rows)}')
for r in rows:
 h=hashlib.sha256()
 with open(r['target'],'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 if h.hexdigest()!=r['sha256']: raise SystemExit('asset changed: '+r['name'])
PY
}
[[ "$(sha "$SRC/main/wrf.exe")" == "$EXPECTED_EXE" ]]
[[ "$(sha "$SRC/phys/module_mp_udm.F")" == "$EXPECTED_SOURCE" ]]
[[ "$(sha "$RUN/namelist.input")" == "$EXPECTED_NML" ]]
[[ "$(sha "$RUN/wrfrst_d01_2010-06-11_12:00:00")" == "$EXPECTED_RST" ]]
verify_assets
[[ -x "$RUN/wrf.exe" ]]
for f in "$RUN"/wrfout_d01_* "$RUN"/rsl.error.* "$RUN"/rsl.out.*; do
  [[ ! -e "$f" ]] || { echo "refusing existing output $f" >&2; exit 73; }
done
export PATH="/home/korea_keun/.local/bin:$DEPS/mpich-sock/bin:$DEPS/netcdf/bin:$PATH"
export LD_LIBRARY_PATH="$DEPS/netcdf/lib:$DEPS/mpich-sock/lib:$DEPS/root/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export OMP_NUM_THREADS=1
export MPICH_INTERFACE_HOSTNAME=127.0.0.1
while IFS='=' read -r name _; do
  case "$name" in WRF_RRTMGP_*) unset "$name";; esac
done < <(env)
cd "$RUN"
start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf 'start=%s\ncase=%s\nranks=%s\ncommand=mpiexec -launcher fork -iface lo -n %s ./wrf.exe\n' "$start" "$case_name" "$ranks" "$ranks" | tee run-start.txt
set +e
timeout 900 mpiexec -launcher fork -iface lo -n "$ranks" ./wrf.exe 2>&1 | tee run.log
status=${PIPESTATUS[0]}
set -e
end=$(date -u +%Y-%m-%dT%H:%M:%SZ)
verify_assets
python3 - "$ROOT" "$case_name" "$ranks" "$status" "$start" "$end" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]); case=sys.argv[2]; run=root/case
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
 return h.hexdigest()
logs=sorted(run.glob('rsl.error.*'))
success={p.name:('SUCCESS COMPLETE WRF' in p.read_text(errors='replace')) for p in logs}
outputs=sorted(run.glob('wrfout_d01_*'))
obj={'case':case,'ranks':int(sys.argv[3]),'exit_code':int(sys.argv[4]),'start_utc':sys.argv[5],'end_utc':sys.argv[6],
 'source_commit':'e7c97ed661403b3922fcf752300c052611ef89cd','source_file_sha256':sha(root.parent/'source/WRF/phys/module_mp_udm.F'),
 'binary_sha256':sha(run/'wrf.exe'),'namelist_sha256':sha(run/'namelist.input'),'checkpoint_sha256':sha(run/'wrfrst_d01_2010-06-11_12:00:00'),
 'command':f'mpiexec -launcher fork -iface lo -n {sys.argv[3]} ./wrf.exe','omp_num_threads':1,'mpich_interface_hostname':'127.0.0.1',
 'per_rank_success':success,'all_ranks_success':len(logs)==int(sys.argv[3]) and all(success.values()),
 'outputs':[{'path':p.name,'sha256':sha(p),'bytes':p.stat().st_size} for p in outputs],
 'rsl_error_files':[p.name for p in logs],'log':'run.log'}
(root/f'{case}-receipt.json').write_text(json.dumps(obj,indent=2)+'\n')
if not obj['all_ranks_success'] or int(sys.argv[4])!=0 or len(outputs)!=1: sys.exit(2)
PY
[[ "$status" == 0 ]]
[[ "$(sha "$SRC/main/wrf.exe")" == "$EXPECTED_EXE" ]]
[[ "$(sha "$SRC/phys/module_mp_udm.F")" == "$EXPECTED_SOURCE" ]]
[[ -e "$RUN/wrfout_d01_2010-06-11_12:01:00" ]]
printf 'RUN_PASS case=%s output_sha256=%s\n' "$case_name" "$(sha "$RUN/wrfout_d01_2010-06-11_12:01:00")"
