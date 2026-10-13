# CF0 warm 상태 전환: 제한된 연구 정책 2

PR173의 40초 거부를 같은 초기 물리 배열로 재현하고, 별도 opt-in
`udm_population_policy=2` (`warm-CF0-grid-v1`)로 60초까지 진행했다.
30초 checkpoint에서 재개한 60초 terminal 배열 211개는 bytes가 같다.
기존 default 0과 strict fixed-footprint 1은 유지한다. 이 결과는 연구용
지속 계산과 단기 restart의 근거이며, 과학적 생산 승인은 아니다.

## 실제 첫 거부와 선택한 가정

40초, step/substep/i/call_lat/k = 5/1/1/1/13에서 CF=0,
QC=2.6695605e-7 kg/kg, QR=9.7907372e-3 kg/kg였다.
NC=161797.515625 m^-3, NR=815809 m^-3, T=284.058136 K,
QV=0.0104267122 kg/kg, dry density=1.07103682 kg/m^3였다.
작은 cloud remnant와 상당한 rain이 공존한 경우다. 제조 기주의 값이며
실제 대기에서의 발생 빈도나 관측 오차를 뜻하지 않는다.

정책 2는 diagnosed cloud CF를 변경하지 않고, CF0의 양의 warm liquid/rain을
grid-mean 균일 population(f=1)으로 계산한다. 각 substep에서 footprint를
선택해 같은 값으로 조건화·복원한다. 물/number/T/QV를 그 자리에서 바꾸지
않으며, 이후 기존 증발·응결·CCN 교환·donor/update가 변화량을 만든다.
작은 CF floor나 임의적인 물 삭제는 없다. Rain-only 층도 실제 CF 진단을
받도록 정책 2에서 active column 전체를 진단한다.

이것은 특정 rain occurrence 관측이 확인됐다는 주장이 아니다. CF>0이면
PR173의 공통 cloud/rain footprint를 유지하고, CF0에서만 균일 잔여 집단이라는
별도 연구 가정을 사용한다. 서로 다른 cloud/rain 영역의 일반적 모델,
entrainment, 혼합상, snow/graupel/hail은 구현하지 않았다. 기존 all-warm,
number policy 1, 단일 periodic 영역 등의 입력 보호를 유지한다.
정책 metadata 2가 있어야 입력/checkpoint를 소비하며 정책 1과 섞지 않는다.
일반 real/ideal/boundary eta 생산기는 계속 미지원이다.

## 복사 소비도 별도 성분으로 연결

정책 2에서 CF0의 liquid/rain grid path는 기존 구름내 경로·cloud CF·McICA
mask를 보존한 채 별도 균일 성분으로 LW/SW에 추가한다. 해당 path는 omission
회계에서 실제 소비량으로 이동한다. SW liquid는 새 성분만 한 번 delta
scaling하고, 이미 scaling한 rain 계수와 합친다. 비축소 직달광 진단에는
raw extinction도 더한다. 정책 2의 wrapper는 scalar column 경로를 사용한다.

첫 capture는 기본 선택에 따라 source time 0이었다. 이를 CF0 이후 증거로
사용하지 않았다. 동일 입력을 capture call 6으로 실행해 **source time 50초**를
확인했다. 해당 기주 CF0 rain path는 1191.9692383 g/m²이며, LW/SW에서 모두
비영 광학량으로 소비됐다. 두 phase의 path를 물질량으로 중복 합산하지 않는다.
동일 public-column native 재생의 UP/DN/HR은 실제 WRF capture와 비트 일치한다.

50초 상태에서 uniform 성분을 0으로 둔 대조와 비교한 최대 가열률 절대차는
LW 0.155084744 K/day, SW 5.29757e-5 K/day다. 최대 층 경계 플럭스 차이는
LW 0.118743896 W/m², SW 0.019121170 W/m²다. `result.json`에 위치·지표·TOA
차이도 보존했다. 고정 제조 상태의 직접 민감도이며 예보/관측 오차가 아니다.

## 최종 액체 PSD 진단 후보

`final-liquid-gamma-veff-0p1-v1`은 최종 q와 dry-mass number eta로
M0=rho_d*eta, M3=3*rho_d*q/(4*pi*rho_w)를 구성하고, 유효분산 0.1,
number-Gamma shape k=8을 **명시적인 연구 가정**으로 둔다.
lambda=[M0*k*(k+1)*(k+2)/M3]^(1/3), M2=M0*k*(k+1)/lambda²,
r_eff=M3/M2다. 최종 production helper의 반경은 바꾸지 않는다.
자동전환 시점의 shape 또는 1.17767을 최종 반경에 복사하지 않는다.

64-node Gauss-Laguerre 적분으로 M2/M3를 별도 대조했다. native 소비 반경,
같은 시점에서 재계산한 평균체적 반경, Gamma 유효반경 세 경우를 계산해
반경 시점/반올림과 PSD shape 효과를 분리했다. UDM이 갱신하지 않는 native
최상층은 기존 반경을 유지하며 최종 PSD 채택 범위에서 제외한다.

같은 50초 상태에서 PSD shape만 바꾼 최대 가열률 차이는 LW 0.007049248,
SW 0.004501082 K/day이며, 최대 층 경계 플럭스 차이는 LW 0.006378174,
SW 3.579376221 W/m²다. 큰 입자 구형 Qext=2의 가시광 소광 극한도 독립
근사 대조로 저장했으나, 이것은 Mie/흡수/플럭스 참값이 아니다. LUT 좌표
clipping을 명시하며, 고정 LUT 원 생성 PSD 인증과 독립 정확도 승인은 남긴다.

## 실행 범위와 재생

- GNU O0/O2 실제 전체 UDM 36회: rain-only, residual L/R, residual L,
  두 밀도, 실제 CF 진단, 10초 step. Observer OFF/ON과 production 반환 일치.
- Resolver는 물/number/온도 인공 source 0. 실제 local warm bulk water 잔차
  최대 2.07e-10 kg/kg, 잠열 온도식 반올림 잔차 9.23e-6 K.
  전체 host의 지면·수송·침강을 포함한 에너지 폐합 인증은 아니다.
- 적격 WRF 4회: strict 40초 거부, policy2 60초, 30초 restart→60초,
  동일 입력의 50초 radiation capture. Capture 선택 변경 전후 7개 primitive
  history 배열은 bytes가 같고, strict/control의 거부 전 공통 5시각도 같다.
- 실제 상태 public-column RTE 8회: LW/SW × native/synchronous-volume/Gamma/zero-uniform.
- 별도 CF0 액체 광학 제조 probe 2회: 10 μm, 추가 path 0.2 g/m²에서
  LW absorption과 SW 한 번 scaling한 소광을 고정 계수 식과 모든 gpoint에서 대조.
- 초기 Runner 오류, TOA path shape 거부, 준비 오류, time0 PSD prototype
  12개 RTE 호출, 별도 최초 forensic WRF 1회는 적격 결과와 분리했다.
  실행 시도는 삭제하지 않으며 `identity.json`과 원래 build scratch에 남긴다.

저장 재생: `python -I -S validation/rrtmgp37/cf0-warm-transition/verify_saved.py`.
실제 새 UDM 검사: `test_udm_cf0_transition.py WRF --workdir <새 scratch>`.
SCM 재현은 `test_udm_cf0_scm.py --help`, PSD 준비는 `prepare_psd.py --help` 참조.
저장 CI는 모델을 새로 실행하지 않는다. 기존 CTest에는 실제 UDM 검사를,
acceptance에는 원시 기록 재생을 연결했다. 과거 PR173 source/result는
historical snapshot으로 보존하고 새 정책의 실행으로 재명명하지 않는다.

기존 일곱 최상위 종료 조건과 `production_accepted=false`는 그대로다.
다음은 균일 잔여 집단/최종 PSD의 독립적인 물리 수용성 판정이며,
이번 민감도나 60초 실행으로 RFMIP/LBLRTM FAIL을 대체하지 않는다.
