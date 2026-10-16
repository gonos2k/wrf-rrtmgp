# PR177 이후: 실제 복사 경향 적용·YSU 기주 계약·보존 PSD 교차차이

기준 main `c7443e7b0bf602cb76e70779629f320bd8fec182`, tree `e8c332723b335a5357d670ea056b0f77aeefe86f`.

**실제 WRF에서 RTE→K/day→건조 온위→THM→채택된 RK3 acoustic source add를 연결했다.** 내부 플럭스/가열률과 압력질량 기준 적용은 닫힌다. 그러나 WRF 건조 층질량×현재 cp로 환산한 온도 등가 에너지는 같은 값이 아니다. 이를 전체 에너지 PASS로 승격하지 않는다. 생산 코드·기본값·반경·계수는 변경하지 않았다.

## 무엇을 실행했는가

- PR176의 정합적인 입력 bytes 그대로, 동일한 2×2×59 all-warm 주기 기주, 60초, dt=10초.
- WRF 프로세스 3회: 진단 OFF, ON(복사 매 step), ON(복사 30초 간격). 세 실행 모두 실제 RC0/SUCCESS COMPLETE WRF.
- OFF/ON/PR176의 7시각×211개 history 변수 배열 bytes 전부 동일. 진단에 따른 물리 변화가 없다.
- 보존된 GNU O2 serial build의 archive를 개인 복사하고 5개 read-only observer 객체만 교체했다. 원 archive와 생산 소스는 그대로다. 새 Fortran 컴파일 5회·archive 갱신·link, 명령별 PID/RC/timeout 기록을 보존한다.
- 이전 observer 준비에서는 2개 객체 컴파일 뒤 진단 인덱스 이름 오류로 3번째 컴파일이 거부됐다. 이 실패는 `saved/excluded-build-v1/`에 남기며 적격 실행에 포함하지 않는다. 당시 WRF 실행은 없었다.
- 새 standalone UDM·RTE·Mie·LBLRTM 실행은 없다. RTE와 YSU는 위 실제 WRF 안에서 실행됐다. PSD 네 출력은 PR177의 보존 자료다.

## 1. 복사 직접 연결: 닫히는 기준과 남는 기준

LW는 121층, SW는 60층 계산 중 **첫 59층과 경계 60까지만** WRF native 영역이다. LW의 확장 TOA를 native top으로 쓰지 않았다. `EI_*`는 RTE 내부 wp(REAL64)의 플럭스·가열률·정확한 입력 압력을 실수 변환 전에 기록한다. native 플럭스 발산과 `cp_dry × Δp/g × heat`의 최대 차이는 LW `7.11e-15`, SW `5.68e-13 W/m²`다.

WRF에서 K/day→K/s→theta/s는 REAL32로 계산한다. radiation driver가 SW 진단을 total−LW로 재구성하는 반올림까지 재생한다. 이어 실제 `conv_t_tendf_to_moist` 입력/출력과 수분 경향 항을 포함한 전체 THM 변환을 비트 단위로 재생한다. 복사 성분은 `(1+Rv/Rd*qv) × coupled dry-theta tendency`다. 수분 경향에 따른 별도 THM 항을 복사열에 중복 포함하지 않는다.

`EA_APPLY`와 `EA_ADD`는 실제 `advance_mu_t`의 source add 전후 값을 짝지운다. 전체 source add의 REAL32 연산 결과가 모두 재생된다. **RK1/2 predictor를 물리 시간으로 합산하지 않고, 채택되는 RK3의 실제 acoustic 간격만 합산**한다. 온위 변수에 들어간 복사 성분은 **그 physics step의 Exner와 qv로 환산한 국소 온도 등가량**으로 기록한다. Acoustic pressure 변화에 따른 압력 일은 이 ledger에 포함하지 않는다. 이 선형 ledger와, 같은 local source add에서 복사 성분만 뺀 read-only 반사실 산술도 분리한다. 후자는 독립적으로 진화시킨 반사실 예보가 아니다.

0–60초, 영역평균 J/m²:

| 현재 실행 내부의 비교 | 복사 매 10초 | 복사 매 30초 |
|---|---:|---:|
| native 경계 순복사 유입 | 4160.176581 | 1271.298414 |
| RTE 내부 압력질량 가열량 | 4160.176581 | 1271.298414 |
| 같은 호출 압력질량으로 환산한 실제 경향 적용량 | 4160.176575 | 1271.309743 |
| 현재 WRF 건조 층질량×cp의 온도 등가 적용량 | 4122.175296 | 1259.674416 |
| 건조질량−호출 압력질량 | **−38.001278** | **−11.635327** |

매 step 호출에서는 K/day·온위·THM·연산 순서까지 연결한 압력질량 적용량과 native 플럭스 차이가 약 `−6.93e-6 J/m²`다. 건조질량 기준 차이를 이 반올림으로 설명할 수는 없다.

현재 `compute_heating_rate`는 **전체 압력차/g와 cp_dry**를 사용한다. 선택적 `NATIVE_DRY_LAYER_MASS_KG_M2`는 가스 column 구성에 쓰이지만 이 가열률 분모를 바꾸지 않는다. WRF 전달 경계는 건조 질량으로 결합된 온위/THM을 사용한다. 따라서 `md*cp_dry*ΔT`라는 명시적인 ledger로 바꾸면 서로 다른 질량이 드러난다. **이는 정의가 고정된 수치 차이의 확인이지, 그 자체로 올바른 습윤 열용량·전체 열역학 에너지의 선택을 완료한 것은 아니다.** 생산 가열률이나 밀도를 임의로 보정하지 않았다.

30초 호출 사이에는 저장된 **theta 경향**이 정확히 유지된다. 실제 온도 등가 경향에는 그 step의 Exner 함수가 들어가므로, 호출 시각의 flux를 단순히 유지한 적분과 `+0.011329 J/m²` 차이가 난다. 이를 가열률 적용 누락이나 dry-mass 차이와 합쳐 설명하지 않는다. 두 실행은 서로 다른 복사 호출로 상태도 달라진다. 최종 차이를 공식 시간 수렴 오차나 정책 정확도라고 부르지 않는다.

진단적인 local source-add 반사실과 선형 복사 ledger의 차이는 매 step/30초에서 각각 `+0.001251/-0.000279 J/m²`다. 이 값은 보존한 피연산자의 보수적인 REAL32 산술 상계 이내다. 상계는 compiler interval 증명이나 물리 수용기준이 아니다.

**판정:** 내부 플럭스/가열률, K/day·theta·THM 연결, 실제 RK source 적용 시간은 해당 사례에서 완료. **건조질량 온도 등가 에너지와 전체 대기 에너지는 OPEN.** 다음에는 총압력질량 기반 가열률과 host 열용량·에너지 정의를 명시적으로 선택해야 한다. 그 결정 없이 density·QFX·UDM number에 보정배율을 넣지 않는다.

## 2. 공통 YSU: 실제 행렬의 작은 계약으로 종료

현재 non-BEP 기주의 수증기 solve 직전에 `al,adv,cu,RHS,qvx,del,dt2,g,QFX`를 기록하고, solve 직후 해와 반환 경향을 기록했다. 실제 12번 j-row 호출×2기주, 59층 행렬이다. `tridin_ysu`의 sequence association에 따라 저장 `al(k)`가 행렬의 **k+1행 lower diagonal**인 점을 반영한다.

현재 `sfk=vlk=1`, BEP source=0에서, 반올림 전 층간 flux 식은 `w=del/g`를 보존하며 지표 계수는 `wᵀb=1`이다. **del은 YSU가 소비한 총압력차다.** 건조 hybrid 층질량으로 같은 보존식이 자동 성립한다는 뜻은 아니다. YSU 내부 `dt2=20초`로 만든 해의 반환 경향을 실제 WRF `dt=10초`만큼 적용한다. 이를 20초의 물리 적용으로 중복 합산하지 않는다.

1. 보존된 계수를 65자리 Decimal에서 독립적으로 solve한다.
2. 원 Thomas solve의 REAL32 연산도 재생하여 실제 해와 전부 비트 일치함을 확인한다.
3. 보존된 REAL32 행렬의 `wᵀM−w`와 해를 곱해 frozen operator의 총량 차이를 직접 재구성한다. RHS 반올림, 계수 반올림, solve, 경향 반환을 분리한다.

매 10초 복사 실행의 60초 kernel-qv 물량 차이, kg/m²:

| 분리한 경계 | 값 |
|---|---:|
| RHS source − QFX | −1.95258e−8 |
| frozen REAL32 행렬 − RHS | **−7.78163e−7** |
| REAL32 solve − Decimal65 solve | +9.79503e−9 |
| 경향 반환 − REAL32 해 | +4.78399e−11 |
| 합계 | **−7.87846e−7** |

즉 이 **kernel 수증기·kernel 압력** 문제에서는 행렬 계수의 유한 정밀도와 solve/반환 기여가 분리됐다. 계수 defect는 국소 산술 상계 안이고, 실제 solve는 정확하게 재생된다. 이 작은 추적은 이 범위에서 끝낸다. 경험적 source 배율이나 YSU 전면 재작성 근거는 없다.

**PR177의 post-PBL qv+qc를 이후 p8w로 평가한 잔차 전체를 위 숫자로 대체하지 않는다.** 이 분석은 kernel qv solve 한 경계이며, host dry-mass source의 물리적 승인·cloud/temperature 방정식의 전수 인증은 아니다. 공통 PBL 미승인 상태는 그대로 두되 복사 포팅의 직접 검증을 기다리게 하지 않는다.

## 3. PSD: 저장된 네 출력의 signed 상호작용

`(Gamma16_hybrid−Gamma8_hybrid)−(Gamma16_LUT−Gamma8_LUT)`를 같은 층/경계에서 계산했다. Gamma8 연구 기준을 유지하고 Gamma16은 불확실성 대조로 둔다.

| 교차차이 | 최대 절대값 | 해당 위치의 부호·위치 |
|---|---:|---|
| UP | 0.0542603 W/m² | −, 경계 31 |
| DN | 0.0132065 W/m² | +, 경계 30 |
| HR | 0.0311203 K/day | +, native 30층 |

새 solver 계산은 없다. 이 사례에서는 우연히 가열률 최대값 차이도 위 값과 같지만, 분석은 최댓값을 빼지 않고 **61개 경계·60개 층의 signed 배열**에서 수행한다. 원 진단은 별도 실제 UDM 종료 상태로 만든 양의 cloud 한 층이며, WRF 50/60초의 cloud-free 상태를 양의 구름 검증으로 재명명하지 않는다. Hybrid의 독립 Mie는 SW6/8만 해당한다. 전체 밴드·관측 승인이나 원 LUT 생성 PSD 인증이 아니다.

## 다음 결과와 종료 범위

- 연구 기준은 policy2/Gamma8로 유지한다. 새 policy3·경험적 반경 배율을 추가하지 않았다.
- 복사 에너지에는 **압력질량·건조질량·열용량 정의 결정**이 남는다. 결합부 수정이 정당화될 때 그 부분만 수정하고 필요한 회귀로 연결한다.
- 양의 cloud의 Gamma8 반경을 최종 실제 host가 소비하는 범위, 과학적 PSD/발생영역 수용성과 독립 reference는 미승인이다.
- 기존 일곱 종료 조건을 byte 그대로 보존했다. RFMIP/LBLRTM FAIL, 전체 에너지, 일반 입력·경계·혼합상·장시간·관측 평가는 이번 결과로 통과시키지 않는다.
- 이 사례의 새 추적은 여기서 종료한다. 같은 내부 시간 ledger나 같은 YSU 행렬 재생을 새 개발 성과로 반복하지 않는다.

실행:

```sh
python -I -S validation/rrtmgp37/applied-radiation-energy/verify_saved.py
python -I -S validation/rrtmgp37/applied-radiation-energy/test_saved.py
```

이 두 명령과 CI는 보존 자료의 재생이다. 새로운 WRF·RTE 과학 실행으로 세지 않는다. 원본 source snapshot·read-only 변환·실제 command receipt·full history packet·부호 있는 결과와 분석 코드를 함께 보존한다.
