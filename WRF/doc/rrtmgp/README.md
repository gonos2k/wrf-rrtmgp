# WRF RRTMGP radiation option 37

WRF v4.8.0에 RTE+RRTMGP CPU 복사 계산을 장파 및 단파 옵션 37로 연결한 개발 이식본이다. WRF의 기존 전처리로 압력·온도·기체와 구름 분율을 준비하고, RRTMGP 전용 입력 함수에서 수상별 수분 경로를 만든 뒤 `phys/module_ra_rrtmgp.F`에서 RRTMGP 기체 광학과 RTE 해법을 호출한다. 계산한 플럭스와 가열률은 기존 WRF 진단 및 온위 경향 배열로 전달된다.

현재 production 개발·평가 범위는 **UDM(option 27) 전용**이다. `37/37 + mp_physics=27 + use_mp_re=1`만 허용한다. UDM 밀도 배열을 수정하고 native radii 및 rain/snow precipitation optics를 연결했다. 수상체별 지원과 검증 한계는 [UDM_ONLY.md](UDM_ONLY.md)에 정의한다. 아래의 과거 범용 미세물리 시험 결과는 역사적 기록이며 현재 지원 선언이 아니다.

## 사용 설정

```fortran
&physics
 mp_physics = 27,
 use_mp_re = 1,
 ra_lw_physics = 37,
 ra_sw_physics = 37,
 aer_opt = 0,
 swint_opt = 0,
 cldovrlp = 2,
 rrtmgp_data_path = '.',
 rrtmgp_ice_roughness = 1,
/
```

`rrtmgp_ice_roughness`는 1=smooth, 2=medium, 3=high이며 LW/SW ice LUT에 명시적으로 적용한다. 기본 1은 이전 포팅 결과를 보존한다. 이 설정과 `rrtmgp_data_path`는 초기화 후 변경할 수 없는 전역 설정이다. 고정 UFSATM의 기본은 3이지만, 그것만으로 이 WRF 구현의 snow 광학까지 NOAA와 같아지는 것은 아니다. [광학 비교](OPTICS_COMPARISON.md)를 참고한다.

`rrtmgp_data_path`는 모든 도메인이 공유하는 계수 디렉터리다. `run/`에 다음 파일이 포함되어 있다. 실행 디렉터리로 복사하거나 이 디렉터리의 경로를 지정한다. 기존 WRF 복사 전처리에 필요한 `RRTMG_LW_DATA`, `RRTMG_SW_DATA`, 오존 및 온실기체 자료도 기존 방식으로 배치한다.

- `rrtmgp-gas-lw-g128.nc`
- `rrtmgp-gas-sw-g112.nc`
- `rrtmgp-clouds-lw-bnd.nc`
- `rrtmgp-clouds-sw-bnd.nc`

## 코드와 자료 버전

WRF 기준은 태그 v4.8.0, 커밋 `06d4240ae989cc3e50af412bb472df3d9048783c`이다.

`external/rte_rrtmgp/`는 UFS CCPP 커밋 `3e6660c6df54e95a0871e990c2294dd397ae3860`이 고정한 NCAR RTE+RRTMGP 커밋 `41c5fcd950fed09b8afe186dede266824eca7fd3`의 소스다. 최신 upstream과 API를 섞지 않고 실제 UFS 코드 경로에 맞췄다. 출처 및 로컬 변경은 `external/rte_rrtmgp/SOURCE.json`에 기록했다.

계수는 earth-system-radiation/rrtmgp-data 커밋 `ea788bb39876948fa8d2c235665ccff19b4686b5`에서 가져왔다. 파일 URL, 크기 및 SHA256은 `external/rte_rrtmgp/DATA.json`에 있다. 현재 공개 자료의 구름 필드 이름 및 빙정 유효직경 좌표를 읽도록 예제 로더를 수정했다. 자료 라이선스는 `external/rte_rrtmgp/DATA_LICENSE`에 보존한다.

## 구현 범위

CPU double precision 내부 계산, SW 6기체·LW 10기체, LW 128 및 SW 112 g점, 장파 흡수·방출과 단파 2 stream 해법을 사용한다. 기본 H2O/CO2/O3/N2O/CH4/O2 외에 장파는 기존 WRF의 CFC11/CFC12/CFC22/CCl4 프로필을 받는다. 장파 산란은 포함하지 않는다. 액체·빙정 LUT와 rain/snow 강수 광학을 합성해 McICA로 g점에 표본화한다. `cldovrlp=0`은 cloud/rain/snow 광학을 제외하고, 1은 random, 2는 maximum random, 3은 maximum이다. 명시적 frozen 실험 모드의 graupel/hail은 구름 mask와 별개로 occurrence=1을 유지한다. 표본은 도메인 ID, 전역 수평 격자 위치, 현재 연도·일자와 LW/SW 구분으로 만든 재현 가능한 시드를 사용한다. 같은 날짜의 복사 호출에서는 고정된 표본을 유지한다. [seed 계약](DOMAIN_CALENDAR_SEEDS.md)을 따른다.

장파와 단파는 모두 37로 선택해야 한다. 기존 옵션 4는 원래 RRTMG 호출 경로를 사용한다. 37의 all sky 및 clear sky 플럭스, K/day 가열률, 단파 직달·산란과 가시광·근적외 분할을 기존 출력에 연결했다. WRF 래퍼가 K/day를 온위 경향으로 변환한다. WRF 래퍼에는 선택적 column packing이 구현되어 있으며 `WRF_RRTMGP_BATCH_SIZE`를 설정하지 않으면 batch 1(scalar)이고, `32`, `64`, `128`을 명시하면 해당 상한으로 컬럼을 모아 호출한다. 각 컬럼의 전역 위치·날짜·LW/SW 구분에서 만든 seed를 buffer와 함께 전달하므로 packing 순서가 seed key를 바꾸지는 않는다. 비어 있지 않은 `WRF_RRTMGP_CAPTURE_DIR` 또는 `WRF_RRTMGP_AUDIT_DIR`, 또는 nonnegative `mcica_seed_override`가 있으면 scalar 경로를 유지한다. 허용되지 않은 batch 값은 오류로 종료한다. 이 코드는 opt-in 경로의 존재를 설명하며, 설정 전반의 성능이나 예보 정확도를 뜻하지 않는다. [구현 및 시험 범위](../../../validation/rrtmgp37/column-batching-source/README.md)

| WRF 입력 | RRTMGP 처리 |
| --- | --- |
| hPa 압력, 지면부터 위로 배열 | Pa로 변환, `top_at_1=.false.` |
| 기체 체적혼합비 | 그대로 전달, 내부 double precision 변환 |
| UDM 수분량 kg/kg dry air와 native 건조층 질량 | 37번 builder가 `Mdry × 1000 × q / cf`로 구름 안 경로 g/m²를 구성; [분모 및 독립 검사](NATIVE_DRY_MASS.md) |
| 구름 분율과 경로 | 유한한 `cf`는 0–1이어야 함; 직접 builder/adapter API는 `cf=0`과 응축수를 거부. WRF wrapper는 명시적 예외로 clear optical path 0을 허용하고 누락된 원래 grid-box 경로를 기록 |
| 액체 유효반경 µm | 반경 그대로 전달; 광학 lookup은 LUT 축 범위로 제한 |
| UDM 빙정 반경 µm | adapter에서 유효직경으로 한 번 변환; Fu 배율 없음 |
| UDM 눈 반경 µm | CCPP snow precipitation 식에 반경 그대로 전달; ice LUT 미사용 |
| 지면 장파 방사율 | 회색 또는 16 밴드 입력 |
| 태양상수 및 천정각 | WRF 계절·일식 보정값 사용 |

SW는 고정 UFS/CCPP의 밴드 규약을 사용한다. 상한이 12850 cm⁻¹ 이하인 밴드는 NIR, 하한이 16000 cm⁻¹ 이상인 밴드는 VIS이며, 12850–16000 cm⁻¹ 전이 밴드는 VIS/NIR에 각각 절반씩 배분한다. 해당 밴드의 직달·산란 알베도도 두 입력의 산술평균을 사용한다. 이는 정밀한 파장 0.7 µm 절단이 아니며, 기존 RRTMG 4번이 전이 밴드를 모두 NIR로 처리하는 규약과도 다르다. 이 규약으로 처리할 수 없는 전이 밴드 경계는 오류로 거부한다. 에어로졸은 밴드 경계와 순서가 RRTMG와 달라 직접 전달할 수 없다. `aer_opt!=0`, 화학 에어로졸 피드백 및 CMAQ 피드백, `cldovrlp=4,5`를 거부한다. 장파는 기존 WRF 래퍼의 CFC11/12/22 및 CCl4 VMR을 추가로 전달하며, 단파는 해당 흡수 구간이 없는 고정 자료의 6기체 구성을 유지한다. 실제 시간변화 기체값과 동일 상태 A/B 검증 규약은 [LW_TRACE_GASES.md](LW_TRACE_GASES.md)에 기록한다.

기본 모드의 수상체 광학은 UDM qc/qi cloud LUT 및 qr/qs precipitation optics다. 이 모드에서는 qg의 제외 질량을 진단하고 양의 qh를 거부한다. 아래의 명시적 frozen 실험 모드는 별도 계약이다. 다른 미세물리는 초기화에서 거부한다. SSiB+37은 전체 예보 검증이 완료되지 않은 개발 조합이다.

`rrtmgp_udm_frozen_optics=1`과 명시적 조회표 경로를 지정하면 별도 [frozen 실험](UDM_FROZEN_EXPERIMENT.md)을 사용하며, 이 광학은 실험적이다. [Fresh restart 기록](../../../validation/rrtmgp37/domain-calendar-seeds/fresh-restart/README.md)은 로컬 실자료 short/24-hour own-restart 비교와 진단 없는 이전 checkpoint 호환성을 기록한다. [Nested batching pilot](../../../validation/rrtmgp37/nested-batching-restart/README.md)은 한 시간, MPI4/OMP2의 B1/B32 및 자체 checkpoint restart 비교다. 두 로컬 캠페인은 같은 고정 GNU 실행파일(`6088620a…163fca5`, 컴파일 소스 `d05c97b`)을 사용했지만 사례·설정·비교 범위가 다르다. 현재 문서·검증 head와 실제 컴파일 소스는 각 manifest로 구분한다. strict invocation metadata failures와 별도로 통과한 배열·metadata 계약의 범위는 각 receipt에 남아 있다. 이 결과를 일반적인 예보 정확도나 frozen 광학의 승인으로 해석하지 않는다.

구름 입력 검증은 배열 모양, 유한성, 범위, 압력층 순서, 음수 수분량·경로, 활성 수상의 반경을 검사한다. 반경은 비활성 수상에서 유한한 0을 허용하지만 수분량이 양수이면 양수여야 한다. 직접 builder와 adapter는 `cf=0`인데 응축수 경로가 양수인 입력을 엄격히 거부한다. WRF 전처리는 `QCLDMIN` 또는 cloud-fraction cutoff 아래의 trace condensate를 cf=0으로 만들 수 있으므로 WRF wrapper만 이를 허용한다. 해당 층의 광학 경로는 0으로 두며 debug level 100에서 생략된 원래 grid-box 경로와 reason code 6을 층별 진단한다. 양의 cf에서는 경로 builder가 수상별 질량을 보존한다. cf=0 예외에서는 해당 trace condensate가 복사 광학 입력에서 생략되므로 이를 질량 보존 사례로 세지 않는다. UDM 전용화 이전의 WSM5 시험에서 6개 출력 시각을 포함한 5분 적분 로그에 LW/SW 각각 reason code 6이 793회 기록됐고 최대 생략량은 층·호출당 0.1037024 g/m²였다.

UDM 원래 qc/qi/qr/qs 범주를 보존한다. 37 전용 native-radius 활성화는 기존 4/4를 변경하지 않는다. 초기 배경 반경 보완, 질량 및 광학 합성 계약은 [UDM_ONLY.md](UDM_ONLY.md)를 따른다. 과거 범용 mapping 기록은 [MICROPHYSICS_MAPPING.md](MICROPHYSICS_MAPPING.md)에 남긴다.

이 구현은 HAFS 전체 복사 suite의 재현을 목표로 한 결과가 아니다. HAFS의 최적화된 LW 78/SW 75 g점 및 장파 산란, 에어로졸 경로는 추가 이식 대상이다. 실제 WRF 실행 근거는 위에 링크한 제한된 실자료 사례와 [column-batching 성능 기록](../../../validation/rrtmgp37/column-batching-performance/README.md)에 한정된다. 성능 기록은 고정 GNU CPU build·case·MPI4/OMP2의 세 interleaved block에서 40분 B1/32/64/128 실행을 비교하고 numerical gate를 통과했지만, 세 paired sample의 기술 통계일 뿐 보편적 speedup이나 MPI/OpenMP 확장성의 증명은 아니다. 이 자료는 GPU, 관측 정확도 또는 일반적인 장기 예보 정확도를 검증하지 않는다.

37번의 `SWDOWN`은 RRTMGP가 계산한 `SWDNB`를 그대로 사용하며 `GSW`는 하향−상향 순흡수 플럭스다. 알베도 역산을 사용하지 않는다. `swint_opt=0`만 지원한다. 기존 1번 보간은 회색 알베도로 순흡수를 다시 계산하고 2번은 FARMS 결과로 덮어쓸 수 있으므로 37번에서는 명시적으로 거부한다. 기존 4번 보간 경로는 유지한다. 분광 지면의 시간 보간은 후속 구현·검증 대상이다. 기존 WRF 래퍼는 `PRESENT(SWUPT)` 그룹 안에서 `SWDNB`를 채우므로, 37번 driver는 두 진단 인자의 제공을 요구한다. 37번 Registry package가 이 그룹을 할당하며, 생략한 직접 호출은 미계산 `SWDNB`를 사용하지 않고 오류로 종료한다. 지형·경사면의 플럭스 기준면 검증과 SSiB 전체 결합 검증은 이번 시험에 포함하지 않는다.

구름·눈 변환과 검증 공백은 [검토 후속 항목](REVIEW_FOLLOWUP.md)에 기록한다.

## 빌드 및 독립 시험

WRF의 기존 Make 빌드와 CMake 소스 목록에 라이브러리를 연결했다. NetCDF C 및 Fortran 개발 파일이 필요하다. 전통적인 빌드는 `NETCDF` 아래 `include/`와 `lib/`를 사용한다. 본 환경에서는 로컬 추출 의존성으로 빌드하며 시스템 패키지는 설치하지 않았다.

독립 컬럼 시험은 WRF 전체 빌드 없이 다음과 같이 실행한다.

```bash
cmake -S WRF/test/rrtmgp -B build/rrtmgp-test \
  -DNETCDF_INCLUDE_DIR="$NETCDF/include" \
  -DNETCDF_LIBRARY_DIR="$NETCDF/lib"
cmake --build build/rrtmgp-test -j 8
LD_LIBRARY_PATH="$NETCDF/lib:${LD_LIBRARY_PATH:-}" \
  ctest --test-dir build/rrtmgp-test --output-on-failure
```

이 명령은 상위 작업 디렉터리에서 실행한다. 시험은 맑은 하늘 all/clear 일치, 흐린 하늘의 clear sky 보존, 구름에 의한 지면 단파 감소, 플럭스와 가열률의 에너지 일관성, 직달·산란 및 가시광·근적외 합계, 시드 재현성 및 야간 영값을 확인한다. 구름 builder는 작은 양의 구름분율과 큰 눈 입자 사례를 포함하며, 64컬럼 batch와 단일 컬럼·역순 실행을 비교하고 전체 야간 batch 및 잘못된 입력 거부도 확인한다. 비교 허용치는 `1e-3 + 1e-5 × max(1, |reference|)`이며 bitwise 일치 주장은 아니다. 최종 standalone suite는 28/28 통과했고 64컬럼 batch aggregate max difference는 0이었다. full GNU serial build 후 수정된 4개 backend 모듈을 incremental relink했으며, 37/4 SCM과 6-time cloud diagnostics SCM이 통과했다. 회색 표면 4개 및 `swint_opt=1,2` 거부 시험도 통과했다. 기존 SWDOWN 수정본의 4/4 출력과 최종 4/4 출력의 공통 변수 204개는 bitwise identical였다. `test/rrtmgp/standalone_wrf_error.f90`는 독립 시험에만 쓰는 오류 처리 대체 함수다.

독립 upstream 실행 비교, 공개 SW reference 잔차 및 UDM graupel/hail 지원 근거는 [독립 기준 검증](INDEPENDENT_REFERENCE.md)에 정리했다.

NOAA 사례 및 직접 코드 근거는 [NOAA 적용 사례](NOAA.md)에 정리했다. 실행 검증 결과는 [검증 기록](VALIDATION.md)에 기록한다.

## WRF 단일 컬럼 실행

기존 WRF configure 메뉴의 GNU serial 구성에서 `em_scm_xy`를 빌드한다. GNU serial full build 후 cloud-input 정책 변경 모듈 4개를 다시 컴파일·연결했다. 최종 `run_scm.sh` 37 및 4가 통과했다. 본 환경은 `/bin/csh`가 없어 PATH의 csh로 compile을 호출했다.

```bash
export NETCDF="$PWD/build/deps/netcdf"
export NETCDF_classic=1
export LD_LIBRARY_PATH="$NETCDF/lib:${LD_LIBRARY_PATH:-}"
cd WRF
printf '32\n0\n' | ./configure
csh -f ./compile -j 12 em_scm_xy
cd ..
WRF/test/rrtmgp/run_scm.sh build/scm37 37
WRF/test/rrtmgp/run_scm.sh build/scm4 4
```

GNU serial 메뉴 번호는 이 플랫폼의 v4.8.0 configure 기준이다. 다른 플랫폼에서는 메뉴를 확인해 선택한다. 실행 스크립트는 새 작업 디렉터리에 WRF SCM 원본 초기 자료와 계수·테이블 링크를 배치하고 1999년 10월 22일 19 UTC부터 시간 간격 10초로 5분을 실행한다. 위의 의존성 경로는 이 작업 공간에서 준비한 로컬 경로이며 다른 환경에서는 설치한 NetCDF 경로를 지정한다.

## 실제 기둥 재생과 미세물리 계약

현재 실행 계약은 [UDM 전용 입력 계약](UDM_ONLY.md)과 [실제 기둥 독립 재생 방법](COLUMN_REPLAY.md)에 정의한다. qc/qi는 native radii를 사용하는 cloud LUT, qr/qs는 고정 CCPP 강수 광학으로 처리한다. qg는 제외량을 진단하고 양의 qh는 거부한다. [과거 미세물리별 분류 기록](MICROPHYSICS_MAPPING.md)은 현재 허용 목록이 아니다.

독립 재생은 같은 고정 RTE+RRTMGP 코어와 계수로 실제 엔진 입력·광학·출력과 WRF 변환을 비교한다. 독립 분광모델 또는 관측 정확도 검증은 아니다. 현재 UDM 검증 결과는 [검증 기록](../../../validation/rrtmgp37/udm-only/REPORT_ko.md)을 참조한다.

## UDM 물리 감사

[PHYSICS_AUDIT.md](PHYSICS_AUDIT.md)는 실제 UDM 내부 CF와 호출 시점 재계산 CF를 구별하고, 같은 상태의 4/37 paired-seed 계산과 CF·graupel·SW delta 정책의 독립 재생을 설명한다. 새 진단은 운영 CLDFRA 및 수상체 처리 정책을 변경하지 않는다. 실제 결과는 [UDM 물리 감사 보고서](../../../validation/rrtmgp37/udm-physics-audit/REPORT_ko.md)에 기록한다.

[RUNTIME_CONTRACTS.md](RUNTIME_CONTRACTS.md)는 WRF 상수 연결, V5 상수 재생, 계수 로더의 WRF fatal callback 및 실제 RRTMG cloud optics를 교체하는 원인 분리 시험을 설명한다. 새 독립 시험 54개가 통과했으며, 앞 절의 28개 기록은 이전 구름 입력 분리 단계의 검증이다. 실제 병렬·원본 회귀·장시간 실행 상태는 해당 실행 근거로 별도 확인한다.

[현재 정책 감사](../../../validation/rrtmgp37/current-policy-audit/README.md)는 기존 5개 overcast 빙정 컬럼의 광학 교체 산술과 최신 고정 실행파일의 24시간 로그를 다시 분석한다. 큰 4/37 차이의 광학모델 기여와 native/CU LUT clipping·CF=0 강수 제외를 구분해 기록했다. clipping 경로 비율은 플럭스 오차율이 아니며, 진단 성공·배열 회귀 성공을 물리 정확도 판정으로 바꾸지 않는다.

An explicit research-only G/H table path is described in
[UDM_FROZEN_EXPERIMENT.md](UDM_FROZEN_EXPERIMENT.md). It extends the opt-in UDM37
state space without asserting forecast accuracy or changing default mode.
