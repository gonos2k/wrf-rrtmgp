# 구름 입력 분리 이후 검토 반영

기준 main은 `c705c4474d965db1b1cb78066e8c07d3c31a518d`이다. 이번 변경은 작은 구름분율의 표본 시험, 미세물리 분류 계약, 실제 WRF 기둥의 독립 재생에 집중한다. 이전 SWDOWN 직접 반환, 정확한 양의 cf 질량 변환과 기존 4번 경로는 유지한다.

## 이후 공개된 실행 범위 (2026-10-03)

아래 결과는 PR head와 artifact에 연결된 증거다. 일부 PR의 코드는 이번 문서 작업의 소스 기준인 PR #32 head (`de312b7a53cefc2f69024e8b96de4bd586f00816`)의 조상에 포함되어 있으므로, 인용만으로 현재 main의 병합 상태를 단정하지 않는다. PR #31 (`360cbf6668c84ef7d00c163fdce0d8dd54daca44`)은 PR #26의 `sr(ims,j)` 수정 소스에서 24시간 RA4 legacy/RA37 mode-1 쌍과 자기 arm별 12→13시 재시작 배열 일치를 기록한다. 이전 strict-negative mode-0 QI 실패, SR 수정 전 coupled pair, 그리고 corrected pair는 서로 다른 시도다. 과거 실패는 보존하되 서로 원인으로 귀속하지 않는다. PR #34 (`958cf46b074b3927e9ca939ad9d7c371ac11e17b`)는 Fort Peck/Desert Rock 두 지점에서 하루의 hourly snapshot과 누적 복사를 비교했으며 지표별 오차는 혼합됐다. 관측자료는 20 km 모델 격자와 10–12 km 떨어진 점 관측이므로 예보/구름 정확도나 scheme 우열은 결론내리지 않는다.

병렬 결과도 scope를 나눠 읽는다. PR #30 (`bb56ec0ad5a0fbd2ef2027a291554fc40d6c7291`)은 GNU 같은 layout reference/candidate의 byte parity이고, PR #27 (`f7f0ad164b50684bb170b729f0836c0e8404a8e0`)은 pristine WRF 한 스텝 MPI1/MPI4 차이가 남아 원인이 미확정임을 기록한다. PR #33 (`0f1ae2967281df3cfa4d8ec5c0f6764fe025158d`)은 부모 보간 initial state의 2시간 nested smoke만 다룬다. PR #35 (`7ea36677ae085e8edc61b9161c075bdeda8441d2`)는 Intel serial 1분 run이다; 이 케이스에서 512 MiB master stack은 실패하고 1 GiB 설정은 통과했다. 이는 보편적인 stack 하한이나 Intel MPI/OpenMP 장기 지원 주장이 아니다.

## 작은 cf와 McICA

한 구름층의 grid LWP=1 g/m²를 고정하고 cf=1e-6부터 0.1까지 10개 분율·2,048개 시드를 계산했다. 평균·분산과 ICA 가중 계산은 배정도를 사용한다. LW/SW의 실제 표본 수, 구름 없는 기둥 비율, 지면/TOA 플럭스 및 3개 층의 가열률 평균·SD·SE를 기록했다. 동일 시드 반복은 정확히 일치했다.

cf=1e-6와 1e-5에서는 두 복사 대역 모두 구름 g-point를 한 번도 선택하지 않았다. cf=0.001에서는 구름 없는 기둥 비율이 SW 89.69727%, LW 88.28125%였다. cf>=0.001의 10개 복사 지표는 청천·완전 구름의 두 상태 ICA 기대값과 6 SE+4 float32 ULP 범위 안에서 일치했다. 희박한 분율에서 0회 표본과 SD=0은 정확성의 증거가 아니다. 새 cf 하한이나 시드 시간 정책은 도입하지 않았다. [CSV](../../../validation/rrtmgp37/small-cf-sampling.csv)와 [그림](../../../validation/rrtmgp37/small-cf-sampling.svg)을 함께 제공한다.

## 미세물리 분류와 실제 재생

Registry에서 WSM5는 4번, Ferrier/Aligo는 5번, ETAMPNEW는 95번이다. 오래된 “MP option 5” 주석의 10/90 분할은 실제로 종 플래그로 선택되며 37번에서는 적용하지 않는다. ETAMPNEW의 37번 분기는 공통 no-QI 온도 처리 이후 원래 QC/QS를 복원하고 QI=0으로 둔다. 따라서 과냉각 액체가 그 공통 분기 때문에 얼음으로 옮겨지지 않는다. Ferrier의 통합 frozen QI는 한 번 IWP에 넣고 QS=0으로 둔다. [분류 계약](MICROPHYSICS_MAPPING.md)에 번호·단위·proxy를 명시했다.

실제 WRF 실행에서 원래 상태, 엔진 입력, 광학 배열·mask, 플럭스·가열률과 WRF 온위 경향을 저장한다. 독립 실행 파일은 WRF adapter/builder/stub을 링크하지 않고 같은 고정 라이브러리·계수로 직접 계산하며 난수·중첩 구현도 별도로 작성했다. 따라서 연결·변환 계층의 비교이며 독립적인 분광 정확도 평가를 뜻하지 않는다. [재생 방법](COLUMN_REPLAY.md)에 파일 형식과 허용오차가 있다.

MP2/4/5의 5분 SCM 청천 시작 제어 사례가 통과했다. 약 248.865 K의 원래 WRF 층에 등록된 수상체를 넣은 제어 사례에서도 MP4/5의 5분 SCM과 LW/SW 재생이 통과했다. cloud τ와 실제 cloudy mask가 양수인 상태를 검사하므로 0 질량의 자명한 비교가 아니다. MP95의 초기 과냉각 QC/QS 기둥은 같은 재생·분류·질량 계약을 통과했으나 최종 후속 SCM 적분은 `RRTMGP_INPUT_PATH_OVERFLOW layer=1`로 실패했다. 다른 반복에서는 압력 계수 범위 오류와 0인 압력두께도 관측했으며, 이 실패들의 원인은 미확정이다. 이를 `PASS_COLUMN_REPLAY`와 `FAILED_AFTER_CAPTURE`로 분리해 기록한다. 같은 SCM의 4/4 MP95 탐색 실행도 segmentation fault로 종료됐으며 두 실패의 원인은 아직 확정하지 않았다. MP95 예보가 통과했다는 주장은 하지 않는다.

## 검증 범위와 남은 작업

GNU serial 표준 `compile -j 12 em_scm_xy` 경로로 실행 파일을 다시 빌드했다. CTest 29/29, 기존 회색 알베도·보간 거부·청천 제외 진단 시험이 통과했다. 직전 포팅본과 새 4/4 출력 공통 변수 204개는 비트 단위로 일치했다. 공식 원본 WRF와의 회귀 비교는 아니다. 현재 결과는 [sampling-replay.json](../../../validation/rrtmgp37/sampling-replay.json)에 있다.

- MP95 SCM의 경로 overflow·압력 오류와 원인 규명, Thompson/P3의 실제 분류·반경 경로 검증.
- 음수 qc/qi/qs 허용 정책을 다른 사례·예보 분포로 일반화하고 물리적 영향을 평가한다. 현재 magnitude-based 보정 정책은 구현됐지만, 이는 보편적인 안전성·물리 타당성의 증거가 아니다.
- PR32의 cf=0 제외 질량·LUT clipping 진단을 추가 사례의 질량가중 통계와 복사 영향으로 확장하고, 눈 반경 proxy 민감도를 정량화한다.
- PR23에서 구현한 delta-scaled solver direct의 의미를 관측 DNI/비산란 direct와 대조 검증한다.
- PR31의 corrected 24시간 pair와 자기 arm 재시작 연속성을 더 긴 24–48시간 사례와 일반적인 forecast skill 검증으로 확장한다.
- 여러 MPI 분해 사이의 동등성 및 PR27 pristine baseline 차이의 원인. PR30의 같은 layout끼리 parity와 구분한다.
- 고해상도 nested 입력, nested restart, 장기 child skill. PR33은 parent-interpolated 단기 smoke다.
- 다양한 사례·기간의 RA4 회귀와 MPI/OMP 구성의 장기 안정성, 전체 입력범위/계수 외삽, 현장 관측을 통한 구름·강수·가열률 검증. PR26은 corrected source의 matched-layout RA4 회귀 근거를, PR31은 corrected source의 24시간 RA4/RA37 pair를 제공한다. PR34는 두 점/하루의 surface radiation 결과만 제공한다.
- production WRF tile/column packing 32–256 columns과 batching 성능·할당량 측정. 현재 WRF radiative call은 `ncol=1`이며, 전체 CMake/CI integration 검증은 진행 중이다.

현재 재생 진단은 GNU 직렬 개발 실행에 한정한다. 전체 예보의 안정성·정확도·병렬 운용 적합성은 이 시험으로 확정하지 않는다.
