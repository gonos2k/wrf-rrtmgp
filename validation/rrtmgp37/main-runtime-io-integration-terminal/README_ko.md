# main 기반 통합의 terminal 검증

PR #146의 실행 head는 `dd7eb1da3a23ca8f21bd4d5bf82f7feecf813fc5`, 전체 tree는 `c51069f89eccf113dca91a6942264194f3bc839e`이다. CI merge-test `2d228d7`도 같은 전체 tree를 사용했다. 이후 이 기록과 체크리스트를 추가하는 문서 commit은 전체 tree가 달라진다. WRF/config/tools의 동일 subtrees를 확인해 생산 소스 내용에 결과를 연결하며, 문서까지 포함한 새 전체 tree를 다시 실행했다고 주장하지 않는다.

| 검사 | 실제 종료 결과 | 범위 |
|---|---|---|
| 원격 Validate WRF | 8/8 SUCCESS | GNU serial Make fresh build/SCM, 등록·컴포넌트·standalone·OpenMP·reference |
| 원격 CMake 설치 | SUCCESS | GNU13.3 serial REAL32 allocatable, fresh build/install/consumer/installed SCM |
| 원격 문서·capsule 검사 | 2/2 SUCCESS | 합계 11개 check SUCCESS |
| 로컬 CMake MPI/OpenMP | configure/build/install 각 RC0 | GNU13 REAL32 allocatable ARW EM_REAL, 새 build/install |
| UDM4/37 control | 두 실행 RC0·회수 | MPI4×OpenMP2, 13h/14 hourly records, RA37 frozen mode1 |
| 12→13h restart | 두 실행 RC0·회수 | 같은 새 실행파일, 복사한 checkpoint의 ordered ZZ sentinel |

Startup SCM CI의 actual artifact에서 선택한 `execution.json`도 보존한다. 현재 실행파일의 capture OFF/ON은 211개 배열 및 전체 history bytes가 동일하다. 초기 BG snow fixture의 134.778076 μm 반경과 양의 SWP에 대해 LW16/SW14 밴드 모두 기여가 있고, 독립 LW 식 및 SW 흡수 불변량 검사가 통과했다. 이것은 runtime-only 구성이며 engine4/pristine 보존 비교는 포함하지 않는다. 과거 3-arm 결과를 새 CI 결과로 바꾸지 않는다.

로컬 restart는 `ISEEDARR_MULT3D`의 `[Time,num_pert_3d,bottom_top]=[1,15,44]` int32 배열에 `−1…−660`을 기록한 복사본을 사용한다. 각 arm에서 660개 값의 읽기·재저장 순서가 유지됐다. endpoint history의 4번 228개·37번 231개 배열 및 변수 속성은 연속 실행과 정확히 일치한다. 전역 속성 `START_DATE`는 연속 시작과 재시작 시작이 달라 별도 기록한다.

`multi_perturb=0`의 inactive I/O 시험이다. 활성 확률물리 난수열·McICA seed physics·48h 관측 정확도·NOAA production 승인으로 확대하지 않는다. 전체 모델 호출은 새 control2+restart2=4이며 모두 실제 RC0, wait/reap 및 종료 후 process group 부재가 확인됐다. 독립 팀은 소스·계획·terminal receipt와 hash 연결을 검토했다. 팀 검토가 원본 NetCDF를 새로 계산한 것은 아니다.

루트 실행의 source/tool/binary/input/namelist/coefficient/checkpoint/PID/RC/결과 기록은 각각의 plan·execution·comparison JSON에 있다. 대형 바이너리와 NetCDF는 원래 local roots에 보존하고 저장소에는 작은 기록만 넣었다. `manifest.json`은 이 기록들의 폐합 roster다. 로컬 경로는 실행 당시 identity이며 범용 실행 스크립트의 설치 경로를 뜻하지 않는다. 보존된 one-use 스크립트를 그대로 재실행하지 않는다.

Nc read-only 조사도 함께 보존한다. `ccn_conc`의 `#m-3` 값이 `#kg(-1)` 표기의 QNN으로 직접 복사되고, generic mu-weighted scalar transport/UDM slope 소비 사이에 단위 bridge가 보이지 않는다. 이는 소스 계약 충돌이며 어느 단위를 의도했는지는 확정하지 못했다. 단위·population·PSD/LUT 의미와 독립 RFMIP/LBLRTM 기준은 OPEN/FAIL로 유지한다.

[최초 focused 기록](../main-runtime-io-integration/README_ko.md)은 당시 pending 상태로 보존한다. [현재 체크리스트](../acceptance/REVIEW_RESOLUTION_ko.md)는 이 terminal 결과를 연결한다. 보존 RFMIP/Nc 증거 통합은 별도 [PR147](https://github.com/gonos2k/wrf-rrtmgp/pull/147) 후보이며 이 tree에 포함됐다는 뜻은 아니다. 두 PR의 main 병합은 아직 이뤄지지 않았다. `production_accepted=false`.
