# UDM 싸락눈·우박 광학: 오프라인 조회와 보간 검증

PR #18의 동질 얼음 구·지수형 PSD 기준에 대한 후속 수치 검사입니다.
실제 WRF 광학 경로, 기본 graupel 제외 및 양의 hail 거부는 변경하지 않았습니다.
이 자료는 실험적 모델의 조회·단위·범위 계약을 검사하며 예보 정확도나
NOAA 내부 UDM 복사 구현과의 동일성을 입증하지 않습니다.

## 조회 계약

`tools/udm_frozen_optics/lookup.py`는 전체 표와 task receipt를 검증한 뒤
`κρ_bulk/λ`를 `log(λ)`에서 선형 보간하고 실제 조회 λ를 다시 곱합니다.
LW의 source 온도는 선형 보간합니다. 이 방법은 상수 Q 한계의
`κρ_bulk ∝ λ`를 정확히 보존합니다. 소광·산란·산란×비대칭·흡수 모멘트를
각각 보간하므로 표의 소광=산란+흡수 관계와 산란 범위를 유지합니다.
SSA와 g를 먼저 보간하는 방식은 사용하지 않습니다.

표 범위 밖의 λ/T, masked/nonfinite 입력, 음의 경로, 비양의 밀도,
암묵적 shape broadcasting은 거부합니다. 표의 단일 노드는 그 값만 허용합니다.
모멘트×`WP[g/m²]×1e-3/ρ_bulk[kg/m³]`로 광학두께를 얻습니다.
작은 양의 경로도 소비하며 UDM process cutoff 아래라는 이유로 버리지 않습니다.
Grid mean / in-occurrence 경로, 강수 존재분율, McICA mask와 delta scaling은
이 API에서 선택하지 않습니다.

재구성 λ는 공개 UDM의 N0/입자밀도/cutoff/cap을 사용합니다. 현재 소스의
일곱 상수를 대조하고 source SHA를 기록합니다. 입력은 반환된 dry mixing
ratio와 UDM에 전달하는 moist-air density입니다. 계산은 double precision의
대수적 상태 진단이며, 침강 전의 UDM process slope나 single precision 작업배열의
bitwise 재현이 아닙니다. Snow radius를 graupel/hail 크기로 사용하지 않습니다.

## 직접 계산과의 비교

모든 비교는 동일한 물질 자료, 커널, quadrature order=128,
분광 최대간격=50 cm⁻¹을 사용했습니다. 서로 다른 numerical controls의
오차가 보간 차이에 섞이지 않도록 검증기가 해당 계약을 검사합니다.

| 비교 | 최대 소광 정규화 차이 |
|---|---:|
| 기존 3개 λ 노드 → 새 중간점 (λ 보간만) | 4.3775% |
| 5개 λ 노드 → 별도의 4개 중간점, 온도 중간점 포함 | 1.5369% |
| 9개 λ 노드 → 별도의 8개 중간점, 온도 중간점 포함 | 0.4399% |
| 온도 보간만: 4개 T 노드 → 3개 중간점 | 0.02008% |

기존 λ=[300,2000,20000] m⁻¹ 사이에 기하 중간점을 추가해 5개,
다시 같은 방식으로 9개 노드를 구성했습니다. T 노드는 [180,233,250,300] K,
중간점은 [206.5,241.5,275] K입니다. 각 표의 정확한 축은 receipt에 있습니다.
정규화 분모는 같은 직접 계산 위치의 소광 모멘트입니다. 4개 광학 모멘트,
SW 14/LW 16 band 전체의 최댓값을 표시합니다.

세밀화 단계마다 새로운 중간점 집합을 검사했으므로 이 표를 동일 표본의
엄밀한 수렴률로 해석하면 안 됩니다. 주어진 표본의 보간 차이이며 전체
영역 오차 상한이 아닙니다. PR #18에서 남은 quadrature/분광 적분 차이와
물질·입자 모양·공극·젖은 hail의 물리 불확실성도 별도로 남습니다.
검증기는 기본 과학적 PASS를 부여하지 않습니다.

## 검증과 provenance

- `lookup-contract.json`: 표의 모든 knot, 상수 Q/선형 T 해석해, 질량/밀도/단위,
  UDM cutoff/cap, 빈 배열/단일 노드 및 29종 입력 거부. 정상 계약 8개 PASS.
- `artifact-controls.json`: 기존 artifact 검사와 함께 receipt의 order/step/workspace/
  workers/chunk/flags/quadrature/pruning 제어를 포함해 30종 거부.
- `report-contract.json`: 기본 과학적 승인 없음, 명시적 수치 기준의 성공/실패,
  잘못된 기준·기존 출력 덮어쓰기·비교 제어 불일치 거부를 검사.
- `*-final.json`: 같은 수치 제어 아래 직접 계산과의 보간 차이.
- 다섯 주검사와 두 CI rehearsal generation: 총 930개의 완성 band task와 table/receipt,
  SOCRATES precision adaptation 기록. 컴파일된 `.so`는 저장하지 않습니다.
- `provenance.json`, `manifest.json`: 도구·원본·표·검증 파일의 SHA256.
  Portable artifact는 로컬 binary 바이트를 검증했다고 표시하지 않습니다.

CI는 작은 완성 표와 별도의 중간점을 생성해 계약·보간 비교를 재실행합니다.
기존 WRF/SCM 검사도 유지합니다. 실제 모델에서 G/H를 소비하는 시험은 아닙니다.

## 실제 UDM 상태의 표 범위 조사

`actual-state-coverage.json`은 기존 RRTMG4 24시간 실제 사례의 25개 hourly
출력을 조사했습니다. 소스·입력·출력·실행파일의 실행 전후 SHA가 일치합니다.
P+PB, theta_m/Exner, `(1+qv)/ALT` 관계로 history의 밀도와 온도를 재구성했습니다.
P_HYD는 P+PB와 최대 약 294.97 Pa 달라 밀도 계산에 대체 사용하지 않았습니다.

| 성분 | 양의 질량에서 재구성 λ [m⁻¹] | T [K] | 음의 값 수 |
|---|---:|---:|---:|
| Graupel | 1458.14–20000 | 195.855–288.992 | 208 |
| Hail | 470.648–20000 | 195.855–288.992 | 90 |

관측된 양의 G/H 값은 λ=[300,20000], T=[180,300] 범위 안에 있었습니다.
음의 최솟값은 G −1.77e−20, H −8.92e−24 kg/kg이며 이 조사는 clip하지 않고
별도로 셉니다. 원시 상태를 조회 API에 전달하려면 기존 WRF 입력 정책을
명시적으로 적용해야 합니다. 작은 양의 질량은 process cutoff 여부와
독립적으로 기록합니다. T≥273.15 K인 양의 hail은 159843개의 cell-time
표본에서 나타났습니다. 표의 Planck 온도 범위가 이를 포함한다고 해서
동질 얼음의 물질 모형이 녹는 우박에 적절하다고 입증되지는 않습니다.

도메인의 DX/DY는 20 km입니다. 현재 UDM 소스의 `dxmeter(:)=10000.`은
내부 CF 진단에 10 km를 고정합니다. 별도 CF 재계산 진단은 이 소스 값을
따르며 실제 도메인 간격과 구분해 기록합니다. 이 구현 가정을 변경하지 않았습니다.

```bash
python3 validation/rrtmgp37/frozen-optics-lookup/audit_actual_state.py \
  --workspace /path/to/preserved/workspace \
  --output build/new-hourly-coverage.json
```

재현에는 기록된 실제 파일들이 필요하며 이 PR에 대용량 history는 포함하지
않습니다. float32 history에서 재구성한 반환 grid-q 상태이며 native bitwise
밀도, 침강 전 process slope, hourly 사이의 모든 미세물리 상태를 대변하지
않습니다. RRTMGP37의 24시간 실행 성공 또는 전체 runtime 범위 검증도 아닙니다.

## 남은 연결 조건

더 많은 실제 UDM 상태의 λ/T 범위, off-grid 표본 및 별도의 적분 수렴,
강수 존재분율·cloud fraction 계약, immutable table initialization,
실험적 selector, WRF trace/replay, 양의 qg/qh 소비와 범위 오류 처리,
실제 hail 생성 사례·restart·MPI/OpenMP·24–48시간 검증이 필요합니다.
현재 자료를 production table 또는 완성된 UDM hail optics로 선언하지 않습니다.
