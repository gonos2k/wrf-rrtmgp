# 정책2 수지·발생영역 판정과 독립 액체 광학

PR174 main `0da2ca008373eb9cbf149be6698968f08146535e`의 연구 정책을
**실제 수지와 독립 광학으로 평가**했다. 생산 WRF/UDM/RTE, number bridge,
발생분율, 최종 반경, 계수, namelist 기본값을 변경하지 않았다. 새 policy3도 없다.
기존 CF0 지속 계산·restart와 Gamma 모멘트 검증은 완료 상태로 보존한다.

## 판정

- **정책2는 연구용으로 유지한다.** 현재 제조 사례로 전체 host 물·에너지
  보존성을 승인하지 않는다. Native microphysics의 `rho*dz`와 host의
  건조 압력층 질량이 다르며, 물수지 잔차의 대부분이 이 경계에서 나타난다.
- **Gamma(k=8, 유효분산 0.1)는 조건부 구형 입자 광학 진단으로 유지한다.**
  독립 Mie 계산을 수행했지만 기존 LUT와의 동등성은 인증하지 않는다.
  일부 NIR 흡수량 차이, 광학 온도/원래 밴드 가중치의 미확정, 크기 범위
  밖 상태가 남는다. 경험적 반경 배율이나 새로운 생산 계수를 넣지 않는다.
- 기존 일곱 최상위 조건과 `production_accepted=false`는 그대로다.
  이 자료의 integrity PASS는 수지·광학 정확도의 PASS가 아니다.

## 1. 원래 60초 사례의 물수지

원 PR174 물리 입력을 유지한 채 dt=10초와 5초로 같은 0–60초 구간을 계산했다.
각 경우 `radt=0`이므로 radiation을 포함한 호출 빈도도 timestep에 따라 바뀐다.
따라서 차이는 **전체 시간 분할 민감도**이며, CF만의 효과나 공식 수렴 차수가 아니다.

dt10의 원래 실행, 진단용 executable의 OFF, ON 세 실행은 모든 7개 history
시각의 **211개 배열 bytes가 동일**하다. 날짜가 들어가는 NetCDF 파일 전체
bytes 동일성은 주장하지 않는다. dt5도 같은 초기 input 파일을 사용했다.

물량은 모든 59층·2×2 physical column에서

`W = sum(A * md * (qv+qc+qr))`,
`md = -(C1H*(MU+MUB)+C2H)*DNW/g`

로 구성했다. `g`는 모델 REAL32 값 9.810000419616699다. 출력의 AREA2D를
사용하고, 아래 표는 전체 면적으로 나눈 kg/m²다. P는 RAINC+RAINNC 누적량,
E는 같은 시간 구간의 ACLHF에서 환산한다. Noah의 LH/QFX=**2.501e6 J/kg**를
실제 호출 값과 대조했다. UDM의 Lv0=2.5e6과 혼용하지 않는다.
종별 강수 보조량을 총강수에 다시 더하지 않았다.

| 0–60초 진단, kg/m² | dt10 | dt5 |
|---|---:|---:|
| Host `W60-W0-E+P` | -0.03986877 | -0.02039136 |
| 실제 microphysics 호출의 `md` 잔차 합 | -0.04084396 | -0.02038967 |
| 같은 호출의 `rho*dz` 잔차 합 | -0.000002316 | -0.000000766 |
| Host 잔차에서 microphysics `md` 잔차를 뺀 나머지 | +0.00097518 | -0.00000169 |

진단 observer는 **같은 microphysics 호출 직전/직후**에 md의 실제 입력
MUT/C1H/C2H/DNW/g와 rho/dz를 모두 기록한다. History와 내부 RK stage를 같은
시점으로 가정해 맞추지 않는다. 각 호출에서

`R_micro_md = R_micro_rhoDz + sum((md-rho*dz) * delta_q_total)`

로 차이를 분해할 수 있다. 이 사례에서 rho*dz 기준은 거의 보존되지만 이를
host md 보존으로 이름만 바꾸면 안 된다. 원 제조 input도 rho*dz/md가 약
0.632–0.984다. 이것만으로 생산 계산식의 원인까지 확정하지는 않는다.
진단 가중치·초기 상태의 정합성을 먼저 연결해야 한다는 근거다.

나머지 항은 비미세물리 과정·시간 분할·시점별 질량 변화가 합쳐진 값이다.
이를 관측하지 않은 clipping source나 강수 source로 임의 재명명하지 않는다.
전체 host 보존에 대한 사후 물리 허용오차를 만들어 통과시키지 않았다.

경계 회계는 periodic 측면과 코드가 부과하는 **상대 eta 속도 ww=0** 상·하단을
사용한다. History의 물리 W(top)는 8 m/s 이상일 수 있다. 움직이는 좌표면에서
W 자체를 관통 유량으로 해석하거나 W=0을 요구하면 다른 문제를 계산하게 된다.
해당 경계 소스를 snapshot으로 보존했으며 ww 배열을 새로 관측한 것은 아니다.

PH와 ZETATOP만 바꾸어 초기 rho*dz를 맞춘 별도 geometry control은 첫 호출의
warm scope를 벗어나 거부됐다. 이는 적격 비교가 아니며, 초기장을 고친 성과로
집계하지 않는다. 한 필드 수정으로 실제 입력 생산을 대신하지 않는다.

## 2. 에너지: 관측한 항과 아직 닫히지 않은 항

실제 전체 UDM 호출에서 native가 사용하는

`cpm_pre * delta_T + Lv(T_pre) * delta_qv`

를 모든 active cell·step에 연결했다. 온도·잠열 법칙의 면적평균 잔차는
**dt10 +7.09 J/m², dt5 -24.22 J/m²**이고, 대응하는 잠열 처리량은
약 42.99/55.37 MJ/m²다. 이것은 native 열역학 갱신식의 진단이며,
전체 대기 에너지 보존법칙을 대신하지 않는다.

이 제조 사례의 `damp_opt=2`는 온위도 base state로 완화한다. 실제 첫 RK stage의
forcing 전후를 추가로 관측했다. Rayleigh와 explicit diffusion을 포함한 추가
온위 forcing의 **동결 EOS에서의 온도 등가량**은 약 **-14.95/-14.84 MJ/m²**다.
압력·수증기와 함께 기록해 계산했지만, 이를 정확한 전체 에너지원으로 선언하지
않는다. 이 항을 빼고 냉각을 CF 정책이나 복사 오차라고 부르면 잘못된 해석이다.

ACHFX, ACLHF, TOA/지표 누적 복사 플럭스도 같은 구간으로 연결했다. 다만 TOA는
WRF native top보다 위의 확장층을 포함한다. 전체 host의 내부·위치·운동 에너지,
압력 일, damping 소산과 강수의 에너지 경계항을 정한 동일한 이산 회계는 아직
완료되지 않았다. 따라서 **full_energy_closed=false**를 유지한다. 작은 local
잔차나 유한한 출력만으로 전체 에너지 승인으로 승격하지 않는다.

## 3. CF 경계의 실제 과정률

CF를 강제로 지정하지 않은 전체 UDM에서 QC=0.95e-6, 1.05e-6, 2e-6 kg/kg,
같은 QR=0.0097907372 kg/kg와 grid rain number를 비교했다. 두 밀도, dt=0.01/10초,
production/observer OFF/ON을 합쳐 실제 UDM **36회**다. 각 dt의 반환은 동일하다.

실제 CF는 0→0.5, 계산 footprint는 1→0.5로 바뀌었다. Rain slope는 같고
**grid rain self-collection은 2배**, grid rain evaporation rate는 동일했다.
따라서 모든 과정이 같은 비율로 바뀐다고 일반화할 수 없다. dt10 host에서는
초기화 이후 rain 셀의 CF0→양수 전환 4회, 반대 7회였고 dt5에서는 둘 다 없었다.
독립 기상 사례의 빈도나 수렴 완료를 의미하지 않는다.

물질 수지와 입자 집단의 해석은 별개다. 현재 비선형 전환을 기록한 뒤 정책2를
연구용으로 유지하며, rain occurrence의 물리적 근거 없이 매끈한 CF나 policy3를
추가하지 않는다.

## 4. Gamma 후보의 독립 Mie 계산

고정 LUT를 Mie 입력으로 사용하지 않았다. 물의 n,k는 **Hale–Querry(1973),
298.15 K** 자료의 CC0 전사본을 commit/hash로 고정했다. miepython **3.2.0**의
구형 입자 해를 사용하며, 복소 굴절률은 n-ik, n은 파장에 선형, log(k)는 파장에
선형 보간한다. 물 밀도는 기존 후보와 같은 1000 kg/m³다.

Number-Gamma k=8의 면적 가중 분포를 x=lambda*r로 적분한다.
`x^9 exp(-x)/Gamma(10)`의 0–60 구간을 사용하고, 소광·산란·흡수·산란 비대칭
모멘트를 독립 적분한다. x=0의 면적 기여는 해석적으로 0으로 두었다.
반경/파수 구적을 512/24→1024/48→2048/96으로 함께 세분했다.

평가점은 유효반경 **8,12,20 μm**, SW band **8(7700–8050), 6(5150–6150),
4(4000–4650)**, LW band **6(820–980 cm⁻¹)**다. 균일 파수 가중과
SW 5780 K/LW 298.15 K Planck 가중을 나눠 저장했다. 12개 평가점의 마지막
두 구적 사이 최대 상대 변화는 1% 이내였다. 이는 선택점의 수치 진단이며
전체 스펙트럼 오차 상계나 물리 승인 기준은 아니다.

소광은 LUT와 약 0.1–1.9% 차이인 반면, 12 μm에서 Planck 가중 흡수량의
Mie/LUT 비는 SW8 약 **2.17**, SW6 약 **0.542**, SW4 약 **0.979**, LW6 약
**0.996**이었다. 소광 일치가 흡수 일치를 보장하지 않는다. 사전에 둔 5% 계수
동등성 screen은 일부 흡수량에서 충족되지 않는다. 원 LUT의 굴절률·온도·PSD·
밴드 가중 규약이 인증되지 않아 이를 Gamma 자체 또는 LUT의 결함으로 특정할
수 없다. **조건부 광학 비교이고 실제 기주의 정확도 판정은 아니다.**

Mie engine은 보존한 upstream MIEV0/Bohren 계열 양의 구형 입자 시험 9개를
통과했다. 최신 개발 API 전체 시험을 3.2에 적용한 별도 시도는 16개가 실패했고
57개가 통과했다. 새 multipole/zero-size API 등은 이번 계산에 사용하지 않으며,
전체 라이브러리 인증으로 집계하지 않는다. 원 시험과 로그를 보존했다.

## 5. 독립 계수에서 실제 플럭스까지

두 phase의 band6만 독립 Mie 계수로 만든 진단 LUT를 사용했다. 원래 다른
밴드·기체·상태·mask·seed는 유지했다. 독립 계수의 노드 9.5–20.5 μm에 해당하는
active Gamma layer만 대조하고, 다른 층은 native 반경을 유지했다. 비갱신
최상층과 LUT-clipped 크기의 영향을 후보 효과로 포함하지 않았다.

50초 같은 capture의 Gamma 상한 초과는 native 14·26층이며 그 액체 grid path는
전체의 **3.519%**다. 이것은 물질 삭제율이 아니다. LUT는 그 크기를 clipping한다.

적격 public-column RTE는 4회다. LW 최대 플럭스 차이는 약 6.10e-5 W/m²,
가열률 차이는 4.83e-5 K/day였다. SW에서는 cloud optical depth가 변했지만
UP/DN/HR 차이는 이 REAL32 상태에서 해상되지 않았다. 이 불투명 제조 상태의
차폐·반올림 때문에 차이가 작을 수 있으므로, 이를 계수 또는 PSD 정확도 PASS로
바꾸지 않는다. 전체 table을 바꿔 제외한 최상층까지 영향을 준 초기 대조 8회는
따로 두었으며 최종 범위의 성과에 합산하지 않는다.

## 실행·재생 범위

- 최종 적격 WRF 3회: dt10 observer OFF/ON, dt5 ON. Source/array 비간섭 확인.
- 실제 UDM 36회: 동일 rain의 CF 임계값 양쪽과 두 시간간격.
- 독립 Mie 계산과 원 시험 9개, 제한 범위 계수의 실제 RTE 4회.
- 초기 진단 스키마 3개 host 실행, 준비/zero-endpoint 오류, geometry 거부,
  API 버전 불일치, 범위가 다른 RTE prototype은 구분해 기록했다.

진단용 solve_em은 marker를 제거하면 원 source가 bytes로 복원된다. 원 archive를
수정하지 않고 copy의 solve_em object만 교체했으며, 다른 object payload가
동일함을 확인했다. 모든 명령·source·reference data·history packet·원시 관측과
제외 시도를 보존한다. 새 Mie 계산의 PID는 따로 저장하지 않았으므로 최종 실행
identity capsule로 승격하지 않는다. 연구 결과 재생과 최종 identity는 별개다.

재생: `python -I -S validation/rrtmgp37/policy2-budget-optics/verify_saved.py`.
필요 라이브러리 없는 CI는 저장된 raw 기록을 재계산한다. fresh 과학 실행은
`saved/executed/*.py.gz`의 실제 코드와 receipts의 compile/link/input을 사용한다.
관측 빌드는 보존된 PR174 base build를 재사용했으며 모든 base/object digest를
기록한다. 실행 시 library 설치는 별도 scratch의 miepython 3.2.0만 사용했다.

다음 집중 작업은 같은 CF0/restart 시험이나 Gamma 모멘트의 반복이 아니라,
**host/native 질량 carrier·초기 geometry/base-state forcing을 일관되게 연결하는
입력/결합 경계**, **원 LUT와 독립 광학의 온도·분광 가중 계약**, 그리고 정의된
전체 에너지 회계다. 그 전에는 최종 장시간·관측 승인으로 넘어가지 않는다.

출처: [miepython](https://miepython.readthedocs.io/en/stable/),
[Hale–Querry 논문](https://doi.org/10.1364/AO.12.000555),
[굴절률 전사 데이터](https://github.com/polyanskiy/refractiveindex.info-database),
[upstream Mie tests](https://github.com/scottprahl/miepython).
