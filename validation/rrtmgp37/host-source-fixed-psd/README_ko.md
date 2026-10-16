# Host source 최초 차이와 고정 질량·number PSD 진단

기준 main은 PR176 `819e48db62eeb4c1d07d576fe5676a9964ff63ed`, tree
`046b4a5a539eced30680c4edf867e2c70dd4b94a`다. **생산 WRF/UDM/RTE, 초기장,
정책 기본값, 반경, 계수를 변경하지 않았다.** 기존 warm 입력을 재구성하지 않고
그대로 사용했다. 새 policy3, 밀도/혼합비 배율도 없다.

## 판정과 중단 범위

- **잔차의 최초 경계 추적은 현재 사례에서 종료한다.** 실제 지표 QFX에 비해
  host 건조 층질량으로 적분한 PBL 반환 경향이 이미 다르다. 이를 실제 PD source
  적용과 RK 갱신, 미세물리까지 연결하면 기존 host 잔차의 설명되지 않은 부분은
  dt10/dt5에서 약 +1.4e-8/-2.8e-8 kg/m²다.
- 이것은 **실제 지표–대기 물 교환의 물리적 폐합 PASS가 아니다.** QFX를
  PBL의 작은 적용량으로 이름만 바꾸지 않는다. PBL 내부의 전체 수치 해법을
  전수 인증하지 않았으며 생산 버그를 자동 등록하지도 않는다. UDM number
  bridge나 반환 밀도를 보정할 근거는 없다.
- **광학 진단은 q/eta에서 M0/M3를 고정하고 Gamma8의 M2/reff를 계산하는
  정의를 유지한다.** Gamma16은 shape 불확실성 대조로 둔다. 같은 reff에서
  shape 영향이 작았다는 사실을 같은 질량·number에서 영향이 작다는 결론으로
  확대하는 것은 기각한다. 두 후보 중 실제 구름에 맞는 쪽을 관측으로 선택한
  결과는 아니며 생산 반경도 그대로다.
- 기존 일곱 조건, REF-RFMIP/REF-LBL FAIL, `production_accepted=false` 유지.

## 1. 실제 host 갱신 경계

PR176 final 입력의 같은 0–60초, dt10/dt5를 사용했다. `radt=0`의 전체 시간 분할
대조이고 공식 수렴 차수가 아니다. 진단용 solve_em object만 private archive의
복사본에 교체했다. Marker를 제거하면 원 source가 bytes로 복원되고, 원 archive와
그 외 object payload는 그대로다. 세 실제 WRF 실행(OFFdt10/ONdt10/ONdt5)의
OFF/ON 및 PR176 history 모든 7개 시각·211개 배열 bytes가 같다. dt5도 이전
PR176 결과와 같다. 원 build는 수정하지 않았다.

관측 위치는 다음 세 묶음이다.

1. 첫 RK physics driver의 **PBL 반환 직후**, source의 mass coupling 전.
   QFX, rqvblten/rqcblten, dry md와 실제 p8w 양면 압력을 같은 셀에서 기록.
2. **rk_update_scalar_pd 입·출구**와 RK scalar update 입·출구.
   실제 old/new md, old/current scalar, source·advection·dt_rk를 기록.
3. 기존 **미세물리 입·출구** 및 history inventory.

이 구성은 number의 `scalar_adv_opt=0`과 별개로 `moist_adv_opt=1`(PD)을 사용한다.
PD 경로는 마지막 RK stage에서 physics tendency를 moist_old에 먼저 적용한 뒤
source를 0으로 만들고, advective scalar update를 수행한다. RK predictor 세 개를
세 번의 물리 시간 적분처럼 더하지 않았다.

PD 적용은 같은 old mass를 사용하므로 m*delta_q로 측정하고, 마지막 advective
update는 **m_new*q_new - m_old*q_old**를 직접 계산했다. 따라서 질량이 바뀔 때
필요한 q*delta_m과 교차항을 누락하지 않는다.

| 60초 적분, kg/m² | dt10 | dt5 |
|---|---:|---:|
| surface QFX*dt | 0.00255810860 | 0.00296400873 |
| PBL 반환의 host dry-md source | 0.00253394809 | 0.00294263608 |
| **PBL source − surface flux** | **-2.41605e-5** | **-2.13726e-5** |
| PD 실제 적용량 − 전달 source | -1.86595e-6 | -4.17530e-6 |
| RK3 산술·기록 가중 잔차 | -4.15e-9 | -1.60e-9 |
| 미세물리 잔차 | -8.49e-8 | +1.88e-7 |
| 기존 전체 host 잔차 | -2.61014e-5 | -2.53897e-5 |
| 위 갱신들로 재구성한 뒤의 나머지 | **+1.40e-8** | **-2.82e-8** |

QFX 적분은 같은 구간 ACLHF/2501000과 일치한다. PBL→실제 PD 전달 source의
차이는 약 1.4e-10/1.7e-10 kg/m²다. 주된 차이는 미세물리나 scalar advection에서
갑자기 만들어진 것이 아니라, **첫 PBL source 반환에서 이미 관측된다.** 첫 호출의
차이는 dt10 -7.89e-8, dt5 +5.68e-7 kg/m²이며, 항상 같은 부호라는 뜻은 아니다.

## 2. PBL의 pressure 가중과 산술 잔차를 분리

YSU 내부는 실제 p2di 차이 `del=p2di(k)-p2di(k+1)`를 사용하며, 지표 수분항은
`qfx*g/del*dt2`다. WRF wrapper는 qv mixing ratio와 p8w를 이 경로에 전달한다.
반환 경향은 host dry mass와 결합되어 PD source가 된다. 이 소스와 wrapper를
snapshot으로 보존했다. 전체 pressure 기준 집계도 비교용으로 함께 계산했다.

`PBL_md - QFX = (PBL_md - PBL_dp/g) + (PBL_dp/g - QFX)`

| 분해, kg/m² | dt10 | dt5 |
|---|---:|---:|
| 서로 다른 pressure mass 가중의 기여 | -1.99381e-5 | -2.33675e-5 |
| PBL column solve/반환의 pressure 가중 잔차 | -4.22240e-6 | +1.99487e-6 |

따라서 다른 가중치를 골라 작은 잔차로 바꾼 뒤 PASS라고 하지 않는다. 두 번째
항의 내부 tridiagonal solve·반환 산술과 물리적 pressure-mass 규약까지 모두
인증한 것은 아니다. 지금 닫은 것은 **host 잔차가 처음 발생하는 경계와 이후
전달량**이다. 기존 공통 host physics의 source 계약은 UDM/RRTMGP만을 위한
경험적 배율로 수정하지 않는다.

PD/RK의 관측 산술·기록 가중 잔차는 유한 정상 REAL32 입력과 최근접 반올림을
가정한 gamma24 기반 보수적 연산 envelope 안에 있다. 이 envelope는 각각 약
0.00118/0.00236 kg/m²로 **느슨한 수치 회계 점검**이다. 전체 물수지의 물리
허용오차나 엄밀한 compiler interval proof가 아니다. PBL source 차이까지 이를
근거로 무시하거나 전체 보존성으로 승인하지 않는다.

## 3. 현재 warm 사례에는 최종 cloud PSD를 비교할 입자가 없다

이번 실제 source time50 capture의 QC=0이며, history60의 QC/NC도 모두 0이다.
그 상태에서 액체 PSD만 바꾸는 비영 효과를 보고할 수 없다. 이를 억지로 양의
구름으로 바꾸거나 과거 PR174의 불일치 초기장을 현재 상태로 재명명하지 않았다.

판별력 있는 비영 대조에는 **별도 실제 current UDM 종료 상태 한 개**를 사용했다.
기존 warm integration fixture를 한 밀도·한 초기상태로 제한하고 population2의
현재 production object에 실제 10초 호출 1회를 수행했다. CF를 코드에 강제로
삽입하지 않았다. 이 상태는 WRF 60초 예보 사례의 일부가 아니다.

- q_c=0.00647228444 kg/kg
- eta_c=588287424 kg_dry⁻¹
- rho_d=0.699999988 kg/m³
- M0=rho*eta 약 4.11801e8 m⁻³, M3 약 1.08160e-6

이 **같은** q/eta/rho/M0/M3에서 Gamma8/16의 M2를 계산한다. material RI는
Segelstein 298.15 K, log(k) 보간, SW Planck5780 가중으로 고정했다. 광학 material
온도와 실제 fixture 온도는 같지 않으며 온도 의존성 또는 관측 정확도 시험이 아니다.

| number-Gamma shape | M0/M3 | reff, μm |
|---|---|---:|
| 8 (veff0.1, 유지한 연구 진단) | 고정 | 15.3939111 |
| 16 (민감도 대조) | 고정 | 14.6257622 |

반경비는 약 0.95010047이다. 이 시험은 reff를 고정하려고 number를 바꾼 시험과
다르다. 현재 생산 helper의 평균체적 반경을 광학 유효반경과 자동 동등하다고
승인하지 않는다.

## 4. 실제 독립 광학 및 RTE 결과

두 NIR 밴드는 고정 M0/M3의 각 Gamma 분포를 독립 Mie 적분했다.
1024/96→2048/192 반경/분광 구적의 마지막 변화는 선택 모멘트에서 0.19% 미만이다.
고정 RI/온도/가중에서 Gamma16−Gamma8의 상대 변화는 다음과 같다.

| 독립 광학량 | SW8 | SW6 |
|---|---:|---:|
| 소광 | +5.293% | +5.300% |
| 산란 | +5.301% | +5.411% |
| 흡수 | +0.678% | +1.467% |
| sca*g | +5.278% | +5.361% |

따라서 고정 reff 대조의 작은 shape 차이로, 고정 mass/number의 광학 중요도를
낮출 수 없다. 이것은 Gamma16이 실제 구름에 더 적합하다는 판정도 아니다.

RTE는 정합적인 현재 host source50의 기체·경계조건을 재사용하는 **별도의
한 층 입자 광학 진단**이다. 원 host에 실제로 있던 구름이라고 주장하지 않는다.
UDM fixture의 rho*100m 층질량으로 정한 공통 물경로(약 453.06 g/m²), footprint1,
q/eta를 고정했다. 다른 수상체는 양쪽 모두 0이며 gas/source/seed/지표는 같다.

- LW: 유지한 고정 LUT에서 Gamma8/16의 reff만 변경, 2회.
- SW: 같은 LUT의 all-band 반경 민감도, 2회.
- SW: 위 두 상태의 band6/8만 각 PSD의 독립 Mie 계수로 교체한 hybrid, 2회.
  다른 밴드는 원 LUT의 해당 reff 값을 쓴다. 전체 스펙트럼 독립 Mie 검증이 아니다.

| Gamma16−Gamma8 최대 절대차 | LW LUT | SW LUT | SW + 독립 NIR |
|---|---:|---:|---:|
| UP, W/m² | 3.05e-5 | 5.30017 | 5.24591 |
| DN, W/m² | 3.05e-5 | 5.43854 | 5.42533 |
| HR, K/day | 9.54e-6 | 0.380859 | 0.349739 |

이 조건부 dense-cloud 진단의 플럭스·가열률 차이를 관측 오차, 실제 60초 host
효과나 장시간 예보 편향으로 바꾸지 않는다. 다른 종·혼합상·다른 occurrence로
확대하지 않는다. 생산 반경·광학계수는 변경하지 않았다.

## 실행과 재생 범위

적격 실제 실행은 **WRF 3회, 별도 양의 구름 UDM 1회, RTE 6회와 Mie 캠페인**이다.
단일 제조 warm 기주 및 하나의 별도 particle state이지 독립 예보 사례 수가 아니다.
초기 observer의 source-marker/preflight 실패 두 번은 모델 실행 전이었다.
PD 관측이 없던 초기 진단 빌드·host 3회는 별도 스키마로 보존하고 적격 수에
합산하지 않는다. 새 초기장 생산·기존 CF0/restart 비교 반복은 하지 않았다.

명령·source·read-only observer·archive member 대조·원시 값·actual child PID/RC와
제외 receipt를 보존한다. Mie parent PID는 별도 기록하지 않았으므로 최종 실행
identity capsule로 승격하지 않는다. 과거 source snapshot과 현재 승인도 구분한다.

```sh
python -I -S validation/rrtmgp37/host-source-fixed-psd/verify_saved.py
python -I -S validation/rrtmgp37/host-source-fixed-psd/test_saved.py
```

CI 재생은 저장 원시 자료를 다시 계산하며 새 WRF/UDM/Mie/RTE를 실행하지 않는다.
전체 물리 수용 기준을 사후에 만들어 통과시키지 않고 기존 일곱 조건을 보존한다.

다음은 PBL source의 dry/total pressure 및 column solve 계약에 대한 필요한 판정,
선택한 광학 정의의 적용 범위와 실제 복사 가열량/native 경계 플럭스 회계다.
이번에 끝낸 최초 경계 추적이나 같은 q/eta의 Gamma 모멘트를 다시 주력 과제로
반복하지 않는다. 전체 에너지·독립 정확도·일반 입력/경계·최종 예보는 미승인이다.
