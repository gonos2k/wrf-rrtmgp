# WRF RRTMGP radiation option 37

WRF v4.8.0에 RTE+RRTMGP CPU 복사 계산을 장파 및 단파 옵션 37로 연결한 개발 이식본이다. WRF의 기존 전처리로 압력·온도·기체와 구름 분율을 준비하고, RRTMGP 전용 입력 함수에서 수상별 수분 경로를 만든 뒤 `phys/module_ra_rrtmgp.F`에서 RRTMGP 기체 광학과 RTE 해법을 호출한다. 계산한 플럭스와 가열률은 기존 WRF 진단 및 온위 경향 배열로 전달된다.

## 사용 설정

```fortran
&physics
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

CPU double precision 내부 계산, H2O/CO2/O3/N2O/CH4/O2 여섯 기체, LW 128 및 SW 112 g점, 장파 흡수·방출과 단파 2 stream 해법을 사용한다. 장파 산란은 포함하지 않는다. 액체·빙정·눈의 밴드 광학을 구한 뒤 McICA로 g점에 표본화한다. `cldovrlp=0`은 맑은 하늘, 1은 random, 2는 maximum random, 3은 maximum이다. 표본은 수평 격자 위치와 날짜에 따른 재현 가능한 시드로 만든다.

장파와 단파는 모두 37로 선택해야 한다. 기존 옵션 4는 원래 RRTMG 호출 경로를 사용한다. 37의 all sky 및 clear sky 플럭스, K/day 가열률, 단파 직달·산란과 가시광·근적외 분할을 기존 출력에 연결했다. WRF 래퍼가 K/day를 온위 경향으로 변환한다. 현재 WRF 호출은 기존 scalar seed 정책을 유지한다. 독립 backend API에는 선택적 `column_seeds(:)`가 있어 각 컬럼에 시드를 고정하면 컬럼 재배열에도 표본이 유지되지만, WRF의 실제 컬럼 packing 연동은 아직 구현되지 않았다.

| WRF 입력 | RRTMGP 처리 |
| --- | --- |
| hPa 압력, 지면부터 위로 배열 | Pa로 변환, `top_at_1=.false.` |
| 기체 체적혼합비 | 그대로 전달, 내부 double precision 변환 |
| 구름 수분량 kg/kg와 층 압력 | 일반 경로에서 입력 builder가 `dp × 100 / g × 1000 × q / cf`로 구름 안 경로 g/m²를 구성 |
| 구름 분율과 경로 | 유한한 `cf`는 0–1이어야 함; 직접 builder/adapter API는 `cf=0`과 응축수를 거부. WRF wrapper는 명시적 예외로 clear optical path 0을 허용하고 누락된 원래 grid-box 경로를 기록 |
| 액체 유효반경 µm | 반경 그대로 전달; 광학 lookup은 LUT 축 범위로 제한 |
| 빙정·눈 유효반경 µm | adapter에서 유효직경으로 한 번 변환; WRF 경로는 Fu 1.0315 특수 배율을 적용하지 않음 |
| 눈 유효반경 누락 | 진단 빙정 반경을 대리값으로 사용(임시 근사) |
| 지면 장파 방사율 | 회색 또는 16 밴드 입력 |
| 태양상수 및 천정각 | WRF 계절·일식 보정값 사용 |

SW 밴드 하한 12850 cm⁻¹ 이상을 가시광 출력에, 나머지를 근적외 출력에 누적한다. 이는 계수 밴드 경계에 맞춘 분할이며 정밀한 파장 0.7 µm 절단과 차이가 있다. 에어로졸은 밴드 경계와 순서가 RRTMG와 달라 직접 전달할 수 없다. `aer_opt!=0`, 화학 에어로졸 피드백 및 CMAQ 피드백, `cldovrlp=4,5`를 거부한다. CFC11/12/22 및 CCl4는 이 6 기체 구현에 포함하지 않는다.

구름 입력 검증은 배열 모양, 유한성, 범위, 압력층 순서, 음수 수분량·경로, 활성 수상의 반경을 검사한다. 반경은 비활성 수상에서 유한한 0을 허용하지만 수분량이 양수이면 양수여야 한다. 직접 builder와 adapter는 `cf=0`인데 응축수 경로가 양수인 입력을 엄격히 거부한다. WRF 전처리는 `QCLDMIN` 또는 cloud-fraction cutoff 아래의 trace condensate를 cf=0으로 만들 수 있으므로 WRF wrapper만 이를 허용한다. 해당 층의 광학 경로는 0으로 두며 debug level 100에서 생략된 원래 grid-box 경로와 reason code 6을 층별 진단한다. 양의 cf에서는 경로 builder가 수상별 질량을 보존한다. cf=0 예외에서는 해당 trace condensate가 복사 광학 입력에서 생략되므로 이를 질량 보존 사례로 세지 않는다. 6개 출력 시각을 포함한 5분 적분 로그에서 LW/SW 각각 reason code 6이 793회 기록됐고 최대 생략량은 층·호출당 0.1037024 g/m²였다.

미세물리 종 플래그의 분류 계약은 [MICROPHYSICS_MAPPING.md](MICROPHYSICS_MAPPING.md)에 정의한다. WSM5는 option 4, Ferrier/Aligo는 option 5이며, 오래된 “MP option 5” 주석의 10% ice/90% snow 재분류는 37번에서 수행하지 않는다. ETAMPNEW는 QC/QS를 보존하고 Ferrier는 통합 frozen QI를 한 번 IWP에 넣는다. Legacy flag 5의 snow 0.99 factor 및 130 µm 초과 질량 감소도 37번에는 적용하지 않으며, P3의 qi→snow 변경도 legacy RRTMG 경로에만 둔다. WRF 경로는 일반 유효반경을 전달한다. adapter는 액체 반경을 반경으로 유지하고 ice/snow 반경만 직경으로 변환한다. Fu 특수 크기 변환은 직접 backend API의 flag 3 호환 경로에만 해당한다. 눈 반경 누락 시 빙정 반경 대리값은 잠정 선택으로 남아 있어 실제 WRF 기둥 재생과 광학 민감도 검토가 필요하다.

이 구현은 HAFS 전체 복사 suite의 재현을 목표로 한 결과가 아니다. HAFS의 최적화된 LW 78/SW 75 g점 및 장파 산란, 에어로졸 경로는 추가 이식 대상이다. GPU, 실제 예보 사례, MPI/OpenMP 확장성 및 관측 비교는 별도 검증이 필요하다.

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

[미세물리별 분류 계약](MICROPHYSICS_MAPPING.md)과 [기둥 저장·독립 재생 방법](COLUMN_REPLAY.md)을 제공한다. WSM5는 4번이고 Ferrier/Aligo는 5번이며, QS에 frozen water를 저장하는 ETAMPNEW는 95번이다. 37번의 ETAMPNEW 입력은 QC를 액체로 보존하고 QS 전체를 snow 경로에 넣는다. 기존 4번의 10/90 분할은 변경하지 않는다.

현재 독립 재생은 동일한 고정 RTE+RRTMGP 라이브러리와 계수로 실제 엔진 입력·광학·출력과 WRF 변환을 비교한다. 독립 분광모델 정확도 검증은 아니다. 작은 cf의 2,048개 시드 시험 결과도 제공한다. ETAMPNEW 초기 기둥 재생 통과와 후속 SCM 입력 오류를 구분하며, 해당 SCM 예보 성공이나 운용 지원을 주장하지 않는다. 자세한 범위는 [검토 후속 기록](REVIEW_FOLLOWUP.md)에 있다.
