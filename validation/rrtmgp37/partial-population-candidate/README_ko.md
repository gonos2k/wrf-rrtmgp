# 실제 UDM의 고정 CF population 후보 판별

PR171 main `5f7ac64a442d823cc5be2c6189f7b3e6d3f1280f`의 생산 소스를 변경하지 않고 실제 전체 UDM을 컴파일했다. 이번 산출물은 정의표의 재작성보다, **조건부 집단·과정률·반환의 실제 채택/기각 근거**다.

## 결정

`fixed-footprint-warm-LR-v1`을 **명시한 조건의 연구 formulation으로 채택**한다. 같은 구름내 PSD를 다른 CF로 표현한다는 가정에서는 현재 혼합 경로를 기각한다. 생산 namelist·공식 정책 옵션에 추가하지 않았으며, 기존 일곱 물리/최종 조건과 `production_accepted=false`를 유지한다.

가정은 고정 CF, cloud/rain의 같은 점유영역, host의 grid-mean dry-mass number다. 입구 number bridge를 재작성하지 않는다. Phase 구간에서는 이미 조건화된 질량과 함께 NC/NR을 조건화하고 복원한다. Warm-rain 구간에서는 QC/QR/NC/NR을 국소 상태로 함께 조건화해 원래 과정식을 계산하고, 상태와 8개 warm 경향을 CF로 격자평균에 복원한 뒤 원래 donor/update를 수행한다. Free CCN은 나누거나 곱하지 않으며, 이후 활성화 전에 grid 표현을 복원한다.

이 후보는 cloud/rain이 다른 영역을 차지하거나, CF가 substep에서 변하거나, 완전 rain evaporation이 free CCN으로 number를 반환하는 일반 경우를 구현하지 않는다. Warm 전후 cold 배열과 snow/graupel/hail은 이 실험에서 0이며, 융해 사례의 ice는 warm 시작 전에 모두 녹는다. 모든 과정에 일괄 CF 배율을 넣은 후보가 아니다.

## 적격 실제 계산

- 두 밀도 약 0.7/1.1, CF=1/0.5/0.25, warm/융해의 **12개 제조 초기 상태**.
- Cloud in-cloud qc=0.008 kg/kg, rain qr=0.004 kg/kg, cloud N=5e8, rain N=1e5 m^-3, T=285 K, substep=0.01s. Melt에서는 in-cloud qi=1e-5를 추가한다. Host NC/NR은 명시한 grid η로 입력한다. 입자크기·number·donor·embryo 제한을 비활성으로 확인한 상태다.
- 원본 native, 현재 경로의 fixed-CF ON/OFF, 후보 ON/OFF를 O0/O2로 실행했다. **최종 적격 120개 UDM 호출**이며 독립 예보 120개가 아니다. 세 active 층을 관측하고 네 번째 padding 층은 원본과 같은 처리를 유지한다.
- CF는 실제 `cldf_diag` 뒤 test-only snapshot에서 강제로 고정했다. 특히 CF=0.25는 현재 진단의 positive-CF 하한 0.5보다 낮은 제조 조건이다. 세 CF는 모두 dyadic 값이므로 exact 결과를 임의 CF의 bitwise 약속으로 확대하지 않는다. 실제 WRF가 해당 CF를 진단했다는 주장이 아니다. 모든 marked block을 제거하면 원본 생산 bytes로 복원된다.

CF=1의 전체 반환은 두 밀도/두 시나리오에서 원본 native와 비트 동일하다. 관측 ON/OFF 반환과 O0/O2 결과도 일치한다. 후보 warm 구간의 국소 slope·Gamma shape·8개 과정률은 CF와 무관하고, 실제 grid 경향은 CF 배다. 뒤의 donor/update에서 경향이 변하지 않았으며 물의 합도 roundoff 범위에서 폐합한다.

| 실제 비교 | CF=0.5 | CF=0.25 |
|---|---:|---:|
| 현재 phase cloud radius / 후보 | 약 1.25992 | 약 1.58740 |
| 현재 grid cloud self-collection / 후보 | 1/2 | 1/4 |
| 후보 melt grid NC 증가 / CF=1 증가 | 1/2 | 1/4 |

밀도 약0.7의 후보 melt NC grid 증분은 7,328 / 3,664 / 1,832이다. 이는 큰 기존 NC에 Ni를 더한 binary32 결과이며 Ni fit=7,321.596 자체와 구분한다. 현재 경로는 CF 가중 없이 Ni를 더하므로 증분이 이 영역비를 따르지 않는다. 기존 수농도의 ULP가 CF에 따라 달라지기 때문에 현재 경로의 *반올림된* 증분끼리 엄밀히 같은 값일 필요는 없다.

Warm 사례의 최종 QC/QR/NC/NR은 CF 배, 최종 native radius는 불변인 **80개 exact join**을 추가로 재생했다. 24개 최종 층값에서는 같은 밀도의 η 반환과 native mean-volume radius 식을 확인한다. Melt에서는 latent cooling이 CF에 따라 grid T를 다르게 하므로 이후 결과를 강제로 같은 국소 상태로 판정하지 않는다. 블록 직후와 최종 NC·반경은 따로 저장했다. 플럭스가 같아야 한다는 시험은 아니다.

## PSD/LUT 판단

`PSD_DECISION_KO.md`에 실제 Gamma 모멘트와 종별 판정을 연결했다. LW/SW band cloud LUT 두 파일은 pinned official publisher와 실제 bytes·Git blob이 같음을 확인했다. 이는 원파일 계보의 확인이며 생성 PSD·입자 habit의 인증은 아니다. Native liquid volume radius=optical effective radius, 종 공통 Gamma 배율, rain number→cloud LUT 직접 연결은 채택하지 않는다.

## 증거 및 CI 범위

`saved/`는 실제 Fortran 소스 snapshot, 입력 fixture, 당시 실행 script, compile/link/실행 journal과 stdout이다. `verify_saved.py`는 원본→snapshot 복원·원 입력 생성·로그 파싱·과정률·grid 증분·최종 join을 재계산한다. 결과 JSON의 PASS만 읽지 않는다. 기존 CTest에는 **현재 source에서 새 후보를 컴파일/실행하는 시험**을 추가한다. 저장 재생 CI와 fresh CTest의 모델 실행을 구분한다. WRF/RTE/LBLRTM은 새로 실행하지 않았다.

기존 생산 파일·물리 정책·광학계수·경계 보호·융해 수정은 그대로다. CMake 시험 추가로 바뀐 과거 test configuration만 snapshot에 보존했고, PR170/171의 실제 과학 결과와 source hashes는 다시 쓰지 않았다.

## 제외한 개발 시도

두 O0 초기 시도(각 60 UDM 호출)는 최종 적격 통계에 포함하지 않는다. 첫 분석기의 stage 총계가 두 stage를 과다 집계했고, 초기 qc=.004 일부 현재 경로에는 embryo 제한도 작동했다. 세 fixture probe(qc=.008/.016/.032, 총18호출)로 제한이 없는 최초 입력 .008을 선택했다. 두 번째 분석기의 현재 melt 증분에 대한 exact 동일성 요구는 binary32 ULP 차이를 무시한 것이어서 수정했다. 최종 v3는 수정된 분석기를 동결해 O0/O2를 새로 수행했다. 이는 제조 입력/검사기 조정이며 새로운 생산 결함이나 실패한 모델 프로세스로 분류하지 않는다. 시도 receipt/종료 로그와 fixture 선정값은 `attempts/`에 보존한다.

다음 통합은 이 formulation의 실제 발생영역·CF 시간 변화·PSD/광학 정의를 선택한 범위에 연결한 뒤 수행한다. 독립 reference FAIL과 최종 예보 NOT_RUN을 이 numerical self-consistency 결과로 대체하지 않는다.
