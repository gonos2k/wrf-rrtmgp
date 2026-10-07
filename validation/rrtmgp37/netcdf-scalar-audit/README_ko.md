# PR152 자체 재감사와 정정

감사 대상 head는 `eaae0f57ddc00010b6633c3b0917731dffbd1820`이며 당시 PR152는 OPEN이었다. 원격11개 check는 모두 SUCCESS였고 main은 `430776b5a0d9c899a067a64e682d90fed8c065e6`이었다. 이 PASS는 감사 전 head의 결과다. 이번 추가 commit의 원격 결과는 새 head에서 따로 판정한다.

## 확인한 두 항목

1. 최종 metadata 영수증의 `checklist.sha256`는 부모 체크리스트의 `a530…`이었는데 갱신된15/7판정과 연결돼 있었다. 갱신된 eaae0f57 체크리스트의 정확한 해시는 `57a38f7a666c07c679c43763d754033da20d51991f3e6446e707942fdb33bcfe`다. 완료수와 물리7항목 내용은 맞았지만 digest labeling은 잘못됐다. 원래 영수증/manifest를 고치지 않고 `review-erratum.json`과 정확한 별도 snapshot으로 정정했다. 원래 source/metadata 감사와 정정은 서로 구분한다.

2. 보존 reader는 glob과 총36개만 검사했다. 원본을 건드리지 않은 사본에서 O0의 scalar-2.nc를 제거하고 preflight-1-1.nc 사본을 preflight-7-1.nc로 넣자, 기존 reader는 RC0과36파일을 보고하면서 scalar는3개뿐이었다. 이는 file coverage를 강제하지 않는 검증 공백이며 원래36파일/4scalar PASS를 무효화하지 않는다. 실제 원본36개 hash는 재판독 후 모두 유지됐다.

## 수정·검증

새 `WRF/test/rrtmgp/verify_netcdf_zz_outputs.py`는 O0/O2마다 정확한18개 이름을 배열읽기 전에 검사한다. scalar4, recovery24, ZZ2, malformed6 로스터가 빠지거나 다른 정상 파일로 대체될 수 없다. 이후 Times/값/축/속성을 독립 SciPy로 읽는다. INTEGER32 dtype검사는 scalar에 한정하며 모든 변수의 dtype나 symlink배제를 승인하지 않는다. exact names/content 검사는 파일 생성권위나 실제 MPI dispatch의 증명이 아니다.

새 checker CLI7회: 정상36files는 RC0; replacement, Python-O replacement, missing, extra, wrong scalar value, wrong scalar dtype의6개 음성 사례는 각각 RC1이다. 이 기대 FAIL들은 원본 수정이나 생산회귀가 아니다. 기존 reader의 사본 반례1회까지 총Pythonreader subprocess8회다. Backend compile/fixture, WRF, MPI, RTE, LBLRTM 새실행은0회다. 입력/검사기는 실행 도중 변경되지 않았으며 새 출력은 입력 디렉터리 밖의 새 파일만 허용한다.

GitHub standalone job에 새 independent read 단계를 actual backend 시험 뒤로 연결했다. 기존 설치단계가 numpy/scipy를 제공한다. always artifact에는 판독JSON과36개작은manufacturedNetCDF도 추가해 원격자료를 재확인할 수 있게 했다. 새 backend testcase나 physics 변경은 없다.

기존 sealed4패키지157payload, 실제36개 정상원본, acceptance19/current12, 후속22항목의15/7상태와 물리7항목을 보존했다. `production_accepted=false`다. 현재 패키지는 작은JSON/source/log만 포함하며 localdummy NetCDF와 실행파일은 포함하지 않는다. localabsoluteinput경로를 담은 과거 reader는 실행용 portable검사기로 재제공하지 않는다. 새CLI의 사용법은 다음과 같다.

```sh
python3 WRF/test/rrtmgp/verify_netcdf_zz_outputs.py build/netcdf-zz --output build/netcdf-zz-independent.json
```

출력은 새 경로여야 하며 기존 결과를 덮어쓰지 않는다. 원래 archive source/hash를 현재 소스에 맞춰 갱신하지 않았다.
