# PR151 병합 상태와 scalar order0 회귀

기준 main은 `430776b5a0d9c899a067a64e682d90fed8c065e6`, 전체 tree는 `9bfa1ebc25cb3ebaf5f6637b4b9afca958f75f76`이다. PR151 head `07b6d2519b702889b76002300e3ddf2e2d55427b`와 main의 전체 tree가 같다. 원격 readback은 PR151 MERGED와 11개 check SUCCESS를 확인했다. 일반 Make run37576670253의 8개 job, CMake run37576670227 및 두 integrity job을 함께 보존한다. 이 기록은 이전 CI 종료 상태를 조회한 것이며 새 CI/model 실행이 아니다.

현재 상태표는 후속22개 중 main의 제한적 완료15, 물리·최종 미완료7로 갱신했다. 15/22를 프로젝트 정확도나 완성도 비율로 해석하지 않는다. 원래 acceptance19/current12, 물리7항목과 이전 proof127payload를 변경하지 않았다. `production_accepted=false`이다.

## 새로 실행한 scalar 회귀

제안된 보강은 실제 `wrf_io.F90` 전체와 `field_routines.F90`를 사용하는 기존 backend fixture에 추가했다. 생산 backend/Registry/UDM/module_io 소스는 모두 변경하지 않았다. GNU13.3 REAL32 serial, O0/O2 bounds 및 integer-init 진단으로 각1compile/link와 각1fixture를 실행했다. nf-config/cpp/m4를 포함한 직접child8개가 모두 actual RC0으로 종료됐다. WRF 전체 빌드·예보, MPI, RTE, LBLRTM 실행은 없다.

최적화별 scalar파일2개는 public write와 direct FieldIO write를 분리한다. scalar order는 `0`, 사용하지 않는 길이는 `[0,-1,0,-9]`이며 활성 slice는 비어 있다. 두 Times는 00:00/01:00, 값은 -17/2033이다. 실제 Time 길이·handle TimeIndex·Times 문자열·저장 값, close/reopen 뒤 public read, 선택한 public var-info wrapper의 rank0/order0를 확인했다. wrapper는 이전처럼 원문 본문+직렬 routing shim으로 연결한다. 전체 module_io/MPI dispatch 실행이 아니다.

독립 SciPy reader는 최종36개 파일을 읽었다: scalar4개, 기존 write-recovery24개, 정상 ZZ2개, malformed-attribute6개. scalar는 오직 Time 축, `MemoryOrder=b'0  '` 3바이트, 서로 다른 두 정수값을 정확히 검사했다. 나머지32개는 기존 각 레코드 값·기하·속성·오류 후복구 기대값을 그대로 유지했다. 이전 source pins·FAIL 기록은 고치지 않았다.

작은 패키지는 command journal·소스와 dependency pin·reader 결과 및 검토를 담는다. 실행파일/원본36개 NetCDF는 외부 build 경로에 남으며 작은 패키지에 포함하지 않는다. `backend-v1/plan.json`과 result는 실제 절대경로/working파일 source를 기록한다. result의 netcdf pin은 기존 zz2개이고 전체36파일 hash roster는 독립 reader 결과에 있다. manifest 검증과 원본파일 재판독은 구분한다.

## 물리 다음 경계

팀의 `next-physical-review.json`은 기존 stage/activation/partialCF 증거를 읽고 다음 구분 가능한 상태를 제안한다: 같은 population 규약에서 두 건조밀도, 부분CF와 부분activation, 관련 cap/floor 비활성인 과정별 QNN/QNC 관측. 이 파일은 계획이며 새로운 물리실험 결과가 아니다. 기록된 checklist hash는 이번 metadata갱신 전 main의 bytes이며 root-postflight에서 과거Git bytes와 일치함을 확인했다.

이 조건의 actual host→transport→UDM→radius 실행과 producer단위 권위는 아직 확보하지 않았다. 밀도/CF 보정이나 물리PASS를 적용하지 않는다. REF-RFMIP strict21FAIL, REF-LBL negativeOD FAIL, PHY-NC/PHY-SIZE/occurrence/finalidentity/finalforecast 상태는 유지한다.
