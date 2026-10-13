# 실제 warm population 연구 경로 통합

`udm_population_policy=1`은 `fixed-footprint-warm-LR-v1`의 실제 UDM/WRF opt-in 통합이다. 기본값 0은 기존 population 경로를 유지한다. Number 표현은 기존 `udm_number_policy=1` (`dry-number-grid-v1`)을 사용한다. 연구용 통합이며 생산 물리 승인이 아니다. 기존 일곱 종료 조건과 `production_accepted=false`를 유지한다.

## 지원 범위와 입력

- UDM27/LW37/SW37, scalar_adv_opt=0, 단일 domain 1, x/y 주기 경계. 기존 number-policy 경계 보호를 사용한다.
- 첫 통합은 전체 활성 기주가 freezing point보다 따뜻하고 ice/snow/graupel/hail이 없는 warm liquid/rain 범위이다. PR172의 사전 융해 제조 비교는 당시 근거로 유지하며, 이번 실행 옵션의 mixed-phase 지원을 뜻하지 않는다.
- Cloud/rain에 공통 발생영역을 가정한다. CF는 기존 진단을 사용하며 한 substep 동안 고정한다. 다음 substep은 복원된 grid 상태에서 새 CF를 진단한다. Free CCN은 ambient grid reservoir로 남긴다.
- CF=0의 양의 QC 또는 QR은 거부한다. 작은 CF나 응결물 floor로 상태를 숨기지 않는다. 입력 및 완료 substep의 warm 범위도 검사한다.
- 입력/checkpoint의 정수 `UDM_POPULATION_POLICY`와 namelist가 일치해야 한다. 누락은 기존 population 0만 의미한다. 파일 표기만으로 기존 raw number를 eta로 재해석하지 않는다. 일반 real/ideal/boundary eta producer는 계속 미지원이다.

## 실제 계산과 제한 기준

Phase의 질량과 NC/NR을 같은 진단 CF로 조건화·복원한다. Warm 구간의 QC/QR/NC/NR을 같은 저장 footprint로 조건화하고, 기존 과정식 계산 후 상태와 `praut/pracw/prevp/ncaut/nraut/nccol/nracw/nrcol`을 grid 기준으로 복원한다. 기존 donor/update와 activation/sedimentation은 grid 상태를 소비한다. 하나의 local 상태가 다음 CF 진단까지 살아남지 않는다.

완전 비 증발에서는 local NR의 이동량에 footprint를 먼저 곱한다. 이 grid 이동량을 ambient CCN에 더한 뒤 기존 CCN cap을 적용하며 반환량과 cap에 잘린 양을 별도 계산한다. 이것은 응집·분열 등까지 포함한 보편적인 입자 수 보존식이 아니다.

이번 연구 구현은 기존 제한값을 새로 조정하지 않는다. 입구 `adjust_number_concent`와 bulk/activation의 절대 NC/NR 제한은 **grid volume 기준**으로 유지한다. Warm 식 내부의 PSD/embryo/size 제한은 **local 계산 기준**이고, 해당 결과를 CF로 복원한다. Free CCN cap은 **grid volume 기준**이다. 질량/number donor는 복원된 grid 상태·grid 과정률을 소비한다. 이러한 혼합 단계의 제한 정책을 일반 대기 물리로 승인한 것은 아니다. 제한이 비활성인 PR172 일관성 결과와 제한이 활성인 이번 실행 결과를 구분한다.

## 실제 실행 근거

- 새 GNU serial REAL32 WRF/ideal 빌드. 첫 build의 driver trace 호출에 잘못 붙인 keyword는 컴파일 단계에서 발견·수정했다. `build.log`와 성공한 `build-retry.log`를 모두 보존했다.
- 최종 module v3: O0/O2 실제 전체 UDM **120회 정상 호출**, 별도 **4회 의도한 scope 거부**. 두 밀도·CF=1/0.5/0.7, warm/complete-evaporation/two-substeps의 제조 상태를 사용한다. 실제 dt=10초와 두 substep인 dt=360초를 구분한다.
- Observer는 기록과 제조 CF만 삽입한다. 채택 계산식은 unmodified production module에 있다. Observer 제거 시 정확한 production bytes가 복원된다. ON/OFF 반환값 동일, CF=1의 원래 진단 경로 환원, 864개 상태/과정률 복원 비교, O0/O2 동일을 검사한다.
- O0/O2 각각 완전 증발 기록 18개, donor 제한 기록 48개. Local NR→grid CCN을 raw 기록에서 별도로 검사한다. Actual production helper의 cap-free/cap-active 8개 제조 교환과 no-process CF=0.5→0.8→0.7 표현 복원을 확인한다. 비이진 CF에는 REAL32 16u 상대 허용규약을 사용하며 임의 CF의 비트 일치를 주장하지 않는다.
- 최종 host v8: 제조한 all-warm 2×2×59 입력, dt=10초. 20초 연속 실행과 10초 checkpoint에서 10초 재개가 정상 종료하고 **211개 terminal 변수 arrays가 비트 동일**하다. History/checkpoint의 population 표기도 검사한다. 별도 두 실행은 missing population 표기 및 ice 입력을 거부한다. Physics 거부에서는 time 0 history가 생성될 수 있지만 완료된 physics 시각으로 진행하지 않는다.
- 이 20초 창은 장시간 예보 승인 범위가 아니다. 더 긴 제조 시험은 CF0 양의 응결물 전환을 만나 거부됐다. 해당 기록을 지우거나 성공으로 승격하지 않았다. `attempts.json`에 초기 입력/검사기 문제와 최종 적격 실행을 구분했다.

CI의 saved replay는 실제 module stdout과 한번 NetCDF에서 추출한 211개 terminal array payload를 재검산한다. CI에서 원 NetCDF의 변수 선택/해석을 독립 수행하거나 WRF를 새 실행한 것으로 집계하지 않는다. 새 CTest는 실제 current full UDM 계산을 수행한다. Host runner는 외부 executable/seed를 명시적으로 받는다.

## 최종 액체 PSD 판정

`final-liquid-moments.json`은 최종 실제 O2 warm 후보의 활성 18층에서 host eta와 동일 호출 밀도로 M0를, QC로 M3를 연결한다. Native 최종 helper는 평균체적 반경이며, 광학 유효반경 M3/M2의 M2를 저장하지 않는다.

두 제조 PSD(단분산과 두 반경의 동일 입자수 혼합)는 같은 최종 M0/M3를 가지지만 서로 다른 M2를 갖는다. 두 번째 유효반경은 첫 번째보다 약 **12.96%** 크다. 이 차이는 관측 오차나 기존 LUT 오차가 아니라 M2가 미확정이라는 식별성 결과이다. Warm 자동전환의 Gamma shape를 최종 PSD로 자동 적용하거나 1.17767을 생산 반경에 곱하지 않았다. 최종 liquid PSD 가정과 고정 LUT 생성 집단의 연결은 PHY-SIZE OPEN으로 남는다.

## 검증 재사용과 완료 상태

PR171/172의 과학 bytes·원래 hashes는 그대로 보존한다. 변경된 현재 소스와 당시 실행을 섞지 않도록 `historical-source/snapshot-39780e19.json`에 원 소스를 보존하고 saved verifier를 당시 snapshot에 연결했다. 새 통합 근거는 이 폴더의 current source/actual executable/library/input/coefficient identity를 사용한다.

Number bridge와 연구 population 실행 연결은 하위 완료이다. 부분영역 가정·제한 정책의 물리 정확도, 최종 PSD/LUT, 발생분율, RFMIP/LBLRTM의 기존 FAIL, 최종 identity/장시간 관측 평가는 별도 미완료이다. 기존 최상위 gate나 허용오차를 변경하지 않았다.
