# 일관된 warm SCM 입력과 두 NIR 밴드의 조건별 광학 대조

기준은 PR175 main `7fa7e594c34514fe995ba0321a3f84efa55f2aab`, tree
`4a1885e17ea746caca3325e94052e60feb4898c8`이다. **생산 WRF/UDM/RTE 코드,
정책 기본값, 반경, 광학계수는 변경하지 않았다.** 정책3나 밀도 보정배율도 없다.
PR174의 원래 CF0 전환 입력과 PR175의 실패 수지는 그대로 보존한다.

## 결과에 따른 결정

- **새 warm 연구 입력을 채택한다.** 원 WRF ideal의 sounding 초기화에서 시작해
  응결물 하중·EOS·압력·지오포텐셜과 moist 온위 완화 기준을 일관되게 구성했다.
  동일 호출의 native/host 물수지가 일치하므로, 이 사례에서 host 밀도를
  `md/dz`로 덮어쓰거나 미세물리 반환 혼합비를 보정할 근거는 없다.
- **전체 host 수지 승인은 보류한다.** 남은 약 2.5e-5 kg/m²를 반올림으로
  단정하지 않으며, 전체 에너지 폐합도 OPEN이다. 초기 입력 정합성의 개선과
  모든 기상 상태에서의 결합부 보존성은 다른 주장이다.
- **Gamma k8/veff0.1은 조건부 진단으로 유지한다.** SW8/SW6에서 시험한
  PSD shape 변경보다 굴절률 자료·보간 규약의 영향이 컸다. Segelstein 25°C는
  두 밴드의 흡수 차이를 크게 줄였지만, 이것으로 원 LUT의 생성 자료·온도·
  PSD·가중 규약을 인증하지 않는다. 생산 반경·표를 바꾸지 않는다.
- 기존 일곱 조건과 `production_accepted=false`를 유지한다.

## 1. 입력 생산: 개별 필드의 보정 대신 같은 상태를 구성

`module_initialize_scm_xy.F`의 원 ideal executable을 그대로 사용했다.
수평 2×2, 59층, ztop=12 km, periodic 연구 구성에서 약 293 K의 등온 sounding과
qv=0.009 kg/kg를 제공했다. 이 sounding은 제조 입력이며 실제 관측 기주가 아니다.
원 ideal이 P/PB, MU/MUB, AL/ALB, PH/PHB와 dry/moist 온위를 함께 생성한다.
원 seed의 모든 응결물은 0이다.

`make_input.py`는 그 clear seed만 받아 다음을 명시적으로 구성한다.

- 원 seed의 1500 m 이하에 qc=1e-5, qr=2e-4 kg/kg를 넣는다. 혼합상은 0 유지.
- 원 initializer의 이산 하향 압력식을 재사용하되, 하중에는 qv+qc+qr를 쓴다.
- 건조 온위와 수증기로 EOS의 alpha를 구하고, `md*alpha*g`를 적분해 Phi를
  구성한다. rho를 수지에 맞춰 덮어쓰는 처리가 아니다.
- 새로 정의한 체적 CCN/NC/NR=1e8/5e7/2e4 m⁻³에서 eta=n/rho_d를 만든다.
  기존 raw number나 checkpoint의 단위를 인증·재해석하지 않는다.
- `T_BASE=initial THM`, `Z_BASE=initial mass height`로 둔다. Policy metadata는
  number1/population2다. 일반 real/ideal/boundary producer 지원을 추가하지 않는다.

최종 input의 `rho*dz/md`는 1±6.2e-9, dry EOS 상대 잔차는 8.2e-10 이내,
응결물 하중을 포함한 이산 압력식 잔차는 6.7e-6 Pa 이내다. 이는 저장 필드의
대수 점검이며, 실제 REAL32 실행에서는 질량비가 약 1±4e-6 범위다.
과정 전·후의 25개 MB 값 및 실제 MUT/C1H/C2H/DNW/g를 같은 호출로 연결했다.

실행 예:

```sh
python validation/rrtmgp37/consistent-warm-input/make_input.py \
  --canonical-ideal-seed SEED.nc --output NEW.nc --receipt receipt.json
```

일반 파일 변환기가 아니다. 제한한 dimensions, all-warm, clear seed, theta_m,
terrain-following, 초기 질량·기하 정합성을 검사한다. 출력은 새 파일만 허용한다.
보존한 실제 input과 재생성한 모든 변수 bytes가 같음을 NetCDF 시험으로 확인했다.

## 2. 기준상태 대조와 실제 60초 수지

세 입력 variant를 순서대로 분리했다.

1. **canonical:** warm ideal의 기하/EOS + 명시적 liquid perturbation.
2. **theta_reference:** 1번에서 T_BASE만 initial THM으로 변경.
3. **final:** 2번에서 응결물 하중 압력/EOS/Phi를 재구성하고 Z_BASE·eta를 연결.

원 SCM initializer는 dry T_BASE를 저장한 뒤 THM을 만든다. Rayleigh damper는
실제 t(theta_m)에 대해 기준값을 뺀다. 이 사례의 초기 차이는 최대 6.235 K다.
정책2나 UDM 수식의 새 결함으로 일반화하지 않고, **연구 입력의 기준 변수 표현**을
실제 소비 변수와 일치시켰다. `theta_reference`와 `canonical`의 다른 변수 bytes가
모두 같음을 검사한다. 최종 단계도 허용한 P/AL/PH/Z_BASE/eta만 달라진다.

| 0–60초, 단위 | final dt10 | final dt5 |
|---|---:|---:|
| 지면 강수, kg/m² | 0.01703851 | 0.01777645 |
| Host W60−W0−E+P, kg/m² | -2.61014e-5 | -2.53897e-5 |
| 실제 UDM 호출의 host md 잔차 합, kg/m² | -8.49087e-8 | +1.87961e-7 |
| 같은 호출의 rho*dz 잔차 합, kg/m² | -8.94787e-8 | +1.83497e-7 |
| 추가 RK forcing의 온도 등가량, J/m² | -412.74 | -585.61 |

T_BASE만 바꾸기 전 warm canonical의 추가 forcing은 -623316/-620537 J/m²였다.
따라서 이 감소를 새 복사 정책의 정확도 개선이라고 부르지 않는다. 원 PR174의
약 -15 MJ/m²와도 입력이 다르므로 같은 상태의 개선량으로 해석하지 않는다.

물수지는 실제 건조 압력층질량과 AREA2D를 사용한다. 지표 증발은 ACLHF/2501000,
강수는 RAINC+RAINNC이며 종별 보조 누적을 중복 합산하지 않는다. Periodic 측면과
소스가 부과하는 상대 eta 상·하단 ww=0을 경계 조건으로 사용한다. 물리 W=0을
가정하지 않는다. E/P/질량의 시점과 경계 정의는 PR175와 같다.

남은 host 잔차는 약 2.5e-5 kg/m²로 대부분 미세물리 바깥의 잔차다. 이를 아직
특정 clipping/수송 source로 배정하지 않았다. 두 timestep은 radt=0이라 물리·복사
호출 간격도 달라지며, 공식 수렴 차수를 주장하지 않는다. native 잠열 진단,
표면·복사 적분, 동결 EOS의 RK forcing도 저장했으나 압력 일·침강 강수 에너지까지
포함하는 **전체 이산 에너지 법칙의 승인**은 수행하지 않았다.

## 3. SW8/SW6: 한 요소씩 바꾼 독립 계산

동일한 298.15 K, reff=12 μm, 구형 입자 Mie, Gamma k8을 기준으로 고정했다.
굴절률은 고정 commit의 Hale–Querry 또는 Segelstein 전사 자료를 사용한다.
Segelstein은 같은 연구 그룹의 자료 개선·범위 확장이며 독립 관측 두 세트로
집계하지 않는다. 데이터 둘 다 25°C다. **온도 의존 실험은 수행하지 않았다.**

miepython 3.2.0은 PR175에 검증된 같은 설치를 재사용했다. 실제 계산은 반경/
분광 구적 1024/96→2048/192, 두 밴드×네 조건이다. 마지막 변화는 모든 선택
모멘트에서 0.29% 미만이다. 각 계산에서 균일 파수/Planck5780 가중을 분리했다.

| 같은 Planck 가중의 Mie/LUT 흡수비 | SW8 | SW6 |
|---|---:|---:|
| Hale, log(k) 보간, Gamma k8 | 2.17551 | 0.54172 |
| Hale, k만 선형 보간 | 4.59249 | 0.73320 |
| Segelstein, log(k) 보간, Gamma k8 | 0.98882 | 0.96473 |
| Hale, shape만 k16, 같은 reff | 2.17789 | 0.54321 |

굴절률 및 그 보간의 영향이 시험한 shape 변화보다 컸다. 원 LUT와 같은 자료라고
확인된 것은 아니므로, 차이를 Gamma 오류나 LUT 오류로 단정하지 않는다. k16도
새 최종 PSD로 채택하지 않는다. 보간을 값을 맞추는 손잡이로 사용하지 않는다.
소광·산란·흡수·sca*g를 별도로 저장하고, raw/delta absorption 불변식도 검사했다.

## 4. 출력이 차이를 구분하는 얇은 광학 진단

원 50초 opaque capture는 유지했다. 별도 진단에서는 한 native layer30에만
liquid를 두고 reff12, CF1, 원 LUT의 band6 raw tau=1이 되도록 경로를 정했다.
다른 수상체·uniform path는 0이다. 기체·source·태양·지표·seed는 같은 값을 쓴다.
이는 새로운 실제 대기 상태나 WRF 예보가 아니다.

원 LUT / Hale Mie / Segelstein Mie로 public-column을 각각 실행했다. band6/8의
reff12 질의에 필요한 인접 두 노드만 같은 독립 Mie12 값으로 바꾸고 나머지는
그대로 뒀다. 진단 표를 일반 반경 LUT로 배포·승인하지 않는다. 생산 어댑터의
원 delta scaling 경로를 한 번 사용하며 같은 상태·mask·clear flux를 확인한다.

| LUT 대비 최대 절대차 | Hale | Segelstein |
|---|---:|---:|
| UP, W/m² | 0.0169373 | 0.0369568 |
| DN, W/m² | 0.0789795 | 0.0554504 |
| HR, K/day | 0.0545697 | 0.0065861 |

이번에는 차이가 REAL32 출력에 해상된다. Segelstein의 흡수비가 더 가깝다고
모든 플럭스 차이도 단조 감소하지는 않는다. 소광·산란·비대칭도 함께 바뀐다.
이 수치는 진단 민감도이며 관측 오차나 최종 예보 우수성의 판정이 아니다.

## 실제 실행, 제외 시도, 재생

- 적격: canonical ideal 1회, WRF 8회(세 input variant의 dt10/dt5와 두 OFF 대조),
  독립 Mie 한 캠페인, thin RTE 3회. 한 제조 기주의 variants이며 독립 사례 수가 아니다.
- theta_reference/final의 dt10 OFF/ON은 모든 7개 history 시각의 211개 배열 bytes 동일.
- 제외: 초기 writer의 잘못된 변수명(ideal 후 중단), ztop2 km/zdamp5 km의 host abort,
  실행하지 않은 EOS 지수 초안 오류. 원 receipt·오류 로그를 별도로 보존했다.
  abort 원인 수식까지 확정하지 않으며 정상 물리 실행으로 합산하지 않는다.
- PR175의 읽기 전용 observer/executable·archive 연결을 재사용했다. 새 과학 소스
  컴파일이나 원 build 변경은 없다. 실행 코드·실제 input과 history packet·raw
  과정 기록·광학 원자료·계수·결과·child RC/PID receipt를 보존했다. Mie 프로세스
  PID는 별도 보존하지 않아 최종 identity capsule로 승격하지 않는다.

저장 자료 재생은 stdlib만으로 실행하며 새 모델을 돌리지 않는다.

```sh
python -I -S validation/rrtmgp37/consistent-warm-input/verify_saved.py
python -I -S validation/rrtmgp37/consistent-warm-input/test_saved.py
# 실제 NetCDF producer 재생은 NumPy/netCDF4 필요:
python validation/rrtmgp37/consistent-warm-input/test_make_input.py
```

다음 작업은 밀도 보정배율·새 occurrence 옵션이 아니라, **남은 비미세물리 host
잔차와 전체 에너지의 source/work 정의**, **온도·RI·가중이 명시된 광학 후보의
지원 범위 판단**이다. 기존 RFMIP/LBLRTM FAIL과 최종 예보 미승인을 보존한다.

광학 자료 출처:
[Hale–Querry](https://doi.org/10.1364/AO.12.000555),
[Segelstein thesis](http://hdl.handle.net/10355/11599),
[고정 RI 데이터 commit](https://github.com/polyanskiy/refractiveindex.info-database/tree/c5c2f188e848453def5970e347399d653df2ffc2/database/data/main/H2O/nk),
[miepython](https://miepython.readthedocs.io/en/stable/).
