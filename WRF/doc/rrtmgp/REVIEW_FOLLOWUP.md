# 구름 입력 분리 이후 검토 반영

> **역사적 상태 스냅샷.** 이 문서의 열린 항목과 “계속 ncol=1” 문장은 기준 커밋 `c705c4474d965db1b1cb78066e8c07d3c31a518d` 당시의 기록이다. 아래 실패·수치·시험 이력은 보존한다. 현재 코드는 opt-in 컬럼 packing을 포함하며, 후속 실행 범위는 아래의 현재 상태 절에서 별도로 연결한다.

기준 main은 `c705c4474d965db1b1cb78066e8c07d3c31a518d`이다. 이번 변경은 작은 구름분율의 표본 시험, 미세물리 분류 계약, 실제 WRF 기둥의 독립 재생에 집중한다. 이전 SWDOWN 직접 반환, 정확한 양의 cf 질량 변환과 기존 4번 경로는 유지한다.

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
- 음수 qc/qi/qs의 예보 전체 분포 측정; 현재 저장은 선택한 기둥·호출의 값만 보여주며 허용 오차를 정하지 않는다.
- cf=0 제외 질량·LUT clipping의 수상별·질량가중 예보 통계, 눈 반경 proxy 민감도.
- delta-scaled solver direct와 비산란 direct/DNI 비교.
- 실제 누적 에너지 시간적분, 공식 원본 4/4 회귀, 24–48시간·restart·둥지·MPI/OpenMP 및 집단 오류 종료.
- WRF tile packing 32–256컬럼, 실행시간·할당량 측정. WRF는 계속 ncol=1이다.

현재 상태와 역사 기록을 구분한다. 옵션 37 래퍼에는 `WRF_RRTMGP_BATCH_SIZE` 기반의 opt-in 32/64/128 컬럼 packing이 구현되었고 기본값은 batch 1이다. source-matched B1/B32/64/128 회귀와 제한된 40분 성능 측정은 [batch regression](../../../validation/rrtmgp37/column-batching-regression/README.md) 및 [성능 기록](../../../validation/rrtmgp37/column-batching-performance/README.md)을 따른다. 이 결과는 모든 설정의 scaling 또는 accuracy를 뜻하지 않는다.

후속 자료에는 [누적 flux recurrence 검사](../../../validation/rrtmgp37/runtime-contracts/accumulation-final.json), [짧은 공식 RA4 보존 사례](../../../validation/rrtmgp37/reference-residual-audit/serial-ra4/README.md), [24시간 및 own-restart 실행](../../../validation/rrtmgp37/domain-calendar-seeds/fresh-restart/README.md), [1시간 nested MPI4/OMP2 pilot](../../../validation/rrtmgp37/nested-batching-restart/README.md)가 있다. 각각 고정된 실행·사례의 범위로 해석한다. 48시간 예보, 일반 분해 불변성, 전체 운용 안정성·물리 정확도는 이들 시험으로 확정하지 않는다.
