# 실제 WRF 기둥의 저장과 독립 재생

현재 production 대상은 UDM27 + RRTMGP37/37이다. 아래 V1–V3 및 과거 미세물리 설명은 historical replay 기록이다. 재생 실행 파일은 WRF 어댑터·입력 builder·WRF 오류 stub을 링크하지 않고, 고정된 RTE+RRTMGP 라이브러리와 같은 계수만 사용한다. 독립 작성된 난수·중첩 구현과 직접 gas/cloud optics 및 RTE 호출을 통해 연결부를 검사한다. 다른 복사 모델이나 다른 계수에 대한 정확도 검증은 아니다.

## 재현

GNU serial `em_scm_xy`와 NetCDF C/Fortran 개발 파일, Python NumPy/netCDF4가 필요하다.

```bash
cmake -S WRF/test/rrtmgp -B build/replay-reference
cmake --build build/replay-reference --target reference_column --parallel 2
python3 WRF/test/rrtmgp/test_column_replay.py build/replay-udm27 \
  build/replay-reference/reference_column --mp-physics 27
```

새 작업 디렉터리를 지정한다. 실행기는 5분 SCM을 초기화·실행하고 `.raw`, `.input`, `.result`를 독립 실행 파일에 전달해 비교한다. `--cloud-fixture`는 약 250 K의 WRF 층에 등록된 QC/QI/QS만 제어 입력으로 넣어 양의 광학·질량을 검사한다. `--run-minutes`의 기본값은 5다. `--capture-only` 결과는 전체 적분 성공과 구별한다. ETAMPNEW 등 과거 미세물리 저장본은 재생 형식으로 지원하지만 현재 WRF 실행기는 UDM만 허용한다.

`--capture-call N`은 같은 i=1,j=1의 N번째 복사 호출을 선택한다. SW는 WRF 래퍼의 낮 계산만 저장한다. LW의 대기 상단 확장층과 마지막 모델층 온도 재구성은 원래 층 검사와 구분한다. 이 옵션은 시드나 구름분율 정책을 변경하지 않는다.

수동 저장은 기존 디렉터리를 지정해 `WRF_RRTMGP_CAPTURE_DIR=/absolute/capture`를 설정한다. 저장은 기본적으로 꺼져 있다. `WRF_RRTMGP_CAPTURE_CALL=N`으로 호출을 선택하며 계수 초기화에서 환경을 한 번 읽는다. 이 진단의 상태와 파일명은 프로세스 전체에서 공유되므로 GNU 직렬 개발 시험에만 사용한다. MPI/OpenMP·동시 도메인 저장 계약은 아직 없다.

## 저장 계층과 비교

| 파일/계층 | 내용 | 독립 검사 |
| --- | --- | --- |
| A `.raw` | 원래 수상체와 플래그, 준비된 qc/qi/qs, p/T/qv/cf, 반경·중력·Exner 함수 | 등록된 원래 종→준비된 종, 압력·반경 단위, 수상별 grid/in-cloud 경로, 제외 질량 |
| B `.input` | 실제 엔진에 전달한 기압·기체 VMR·수분경로·반경·지면·태양 입력 | A에서 재계산한 B와 비교; 실제 B를 별도 실행 파일에 입력 |
| C `.result`의 광학 배열 | gas/cloud τ 및 SW ω₀/g, delta scaling 전후 구름 광학, 실제 mask, 합산 광학, 제한 후 rₗ/Dᵢ/Dₛ | 독립 실행의 같은 계층과 비교; mask는 정확히 일치해야 함 |
| D `.result`의 출력 | 청천/전천 플럭스와 K/day 가열률, SW direct/diffuse·분광 분할 | 독립 RTE 출력과 비교; WRF 지면 진단·온위 경향으로 변환도 검사 |

광학 비교는 `2e-13 + 2e-12*abs(reference)`, 어댑터의 단정도 반환값은 `1e-6 + 4 float32 ULP`를 허용한다. 서로 다른 최적화와 반환 정밀도를 구분한다. 저장을 선택한 청천 또는 overlap=0 제어 사례는 비교를 위해 준비 광학까지 추가 계산하되, 구름을 대기에 더하는 조건은 원래대로 유지한다.

`SWDDIR`와 `SWDDIF`는 delta-scaled RTE solver의 분해다. 합계 일치나 이번 재생 성공으로 관측 DNI 또는 비산란 direct beam과 같다고 주장하지 않는다. 이 정의에 대한 별도 광학 시험은 남아 있다.

## 작은 구름분율의 별도 시험

`test_small_cf_sampling.f90`는 한 구름층, grid LWP=1 g/m², 액체 반경 10 µm의 고정 기둥에서 10개 분율과 2,048개 시드를 사용한다. 기준은 각 분율의 같은 in-cloud 경로를 사용한 청천·완전 구름 계산을 `(1-f)*F_clear + f*F_cloudy`로 평균한 정확한 두 상태 ICA 기대값이다. 이 기대값의 엔진은 같은 어댑터이며, 위의 독립 코드 재생과 다른 시험이다.

```bash
build/replay-reference/test_rrtmgp_small_cf_sampling WRF/run build/small-cf-sampling.csv
```

이 실행 파일을 사용하려면 CMake 전체 targets를 빌드한다. CSV에는 LW/SW 실제 구름 g-point 수, 구름 없는 기둥 비율, 지면/TOA 플럭스와 층별 가열률의 평균·표본 SD·SE·ICA 값이 들어 있다. 평균·분산 및 ICA 가중 계산은 배정도다. 같은 시드 반복은 정확히 같은 결과여야 한다. 매우 희박한 구름의 0회 표본을 허용하면서 분율 하한이 잘못 도입되거나 표본화가 전부 사라지는 회귀를 막는 넓은 count 검사도 한다. `f>=0.001`은 평균이 `6 SE + 4 float32 ULP` 안에 있어야 하며, 그보다 작은 분율에서는 정규 근사에 기반한 정확도 주장을 하지 않는다.

이 기둥 시험은 고정된 하루 동안의 표본 오차가 시간 평균으로 사라지지 않을 수 있음을 보여준다. 새로운 분율 하한, 음수 q 허용 오차 또는 시드 시간 정책을 추가하지 않는다. 다양한 구름 중첩·광학 상태와 장시간 실제 예보에서의 물리적 영향은 후속 검증 대상이다.

## 광학 설정 형식

Production capture는 `RRTMGP_REPLAY_V6`이며 native 물리층의 `NATIVE_DRY_LAYER_MASS_KG_M2` 행렬과 `GRAVITY`, `CP_DRY`, `MOL_WEIGHT_DRY` 배정도 scalar를 보존한다. 독립 reference는 저장한 상수를 계수 로드 전에 적용하고 native 질량을 기체 건조분자 기둥으로 변환한다. 모델 상단 위 확장층과 native 질량이 없는 V1–V5 저장본은 기존 pressure/VMR 기둥 계산을 유지한다. 결과의 `GAS_COL_DRY`는 native·확장층 모두의 molecules cm⁻²이다. [NATIVE_GAS_COLUMNS.md](NATIVE_GAS_COLUMNS.md)를 참조한다. UDM capture에는 기존 precipitation policy 및 RWP도 들어 있다. 강수 입력이 없는 fixture는 두 강수 기록을 함께 생략한다. V5/V6에서 하나만 존재하면 거부한다. V4 저장본은 강수 기록을 계속 필수로 요구한다. [UDM_ONLY.md](UDM_ONLY.md)를 참조한다.

`ICE_ROUGHNESS 1 1`은 정수 category를 기록한다. SW의 `SW_BAND_PARTITION 1 1` 값 1은 고정 CCPP의 12850–16000 cm⁻¹ 전이 밴드 50:50 알베도·진단 분할이다. LW에는 SW 설정이 없다. 독립 reference와 입력 검사기는 V3 이상 SW 설정 누락 또는 1 이외의 값을 거부한다.

기존 V1–V4 저장본도 재생하며 당시의 upstream 기본 상수를 유지한다. V1은 당시 암묵적 ice category 1, V2는 저장된 1/2/3을 적용한다. 두 구형 형식의 SW는 당시 전이 밴드 전체 VIS 규약을 유지하며 새로운 정책으로 재해석하지 않는다. 결과 형식은 `RRTMGP_RESULT_V1`이다. 형식 회귀 시험은 V5 독립 재생, 비기본 host 상수의 저장·재생, 기본 상수의 정확한 보존, 구형 형식의 동일성과 SW 정책 차이 및 잘못된 설정 거부를 검사한다.

## 구름 광학 교체 대조

독립 `reference_column`의 선택적 다섯 번째 인자는 `WRF_SW_OPTICS_OVERRIDE_V1` 파일이다. 이미 delta-scaled 상태인 band별 총 구름 광학을 McICA 직전에 넣는다. 기체 광학·표면·난수·중첩·RTE는 바꾸지 않는다. 추가 delta 변환을 적용하지 않는다. 형식은 ncol/nlay/nband, BAND_LIMITS 및 Fortran 순서 TAU/SSA/ASYM 배열이며, 유한성·범위·shape·밴드 정합성을 검사한다.

`rrtmg_sw_optics_bridge.f90`는 실제 빌드한 WRF의 `swcldpr`, `cldprmc_sw`, `reicalc`를 링크한다. RRTMG의 2600 cm⁻¹와 고정 RRTMGP의 2680 cm⁻¹ 경계 차이만 명시적으로 허용하고 경고한다. 이는 같은 순서의 밴드에 광학을 넣는 근사 대조 실험이며, 두 엔진의 완전한 분광 동등성이나 RRTMG RTE 재현을 뜻하지 않는다. 다른 경계 차이는 거부한다. 실행 방법과 판단 범위는 [RUNTIME_CONTRACTS.md](RUNTIME_CONTRACTS.md)에 있다.

## 초기 배경 반경의 입력 계약

새 `.raw`는 `ICLOUD`와 기존 WRF의 `FALLBACK_REL/REI/RES`를 함께 기록한다. 반경 제공 플래그만 참이고 원래 반경이 `RE_*_BG`인 wet/cloudy 층에서는 해당 host 진단 반경을 사용한다. 그 외 정상 반경은 원래 값을 전달한다. A→B 검사기는 두 경우를 분리하여 검사하며 기존 저장본의 직접 전달 계약도 재생한다. 첫 cloudy 호출과 미세물리 진단 이후 호출을 따로 저장해 확인한다. 이번 수정의 인과 분해와 실행 증거는 저장소의 `validation/rrtmgp37/port-audit/REPORT_ko.md`에 기록한다.

## 모든 호출과 UDM 대조 실험

`WRF_RRTMGP_CAPTURE_ALL=1`은 선택한 기둥의 모든 LW/SW 호출을 `lw_000001` 등의 이름으로 저장한다. `test_udm_cf_replay.py`는 같은 raw/V4 묶음에서 A/B/B_now/C 구름분율, graupel 제외/가정적 snow 합산, 세 SW delta 정책을 재생한다. A·graupel 제외·policy 1은 원래 생산 결과와 독립 재생의 일치를 먼저 검사한다. 상단 확장층은 보존한다. B의 실제 미진단 sentinel은 유효한 zero CF로 바꾸지 않는다. 자세한 입력·시점·대조 실험 정의는 [PHYSICS_AUDIT.md](PHYSICS_AUDIT.md)를 따른다.
