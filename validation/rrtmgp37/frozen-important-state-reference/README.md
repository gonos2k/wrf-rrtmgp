# 실제 중요한 frozen1 상태: 조건부 수치 참조와 수송 전파

현재 frozen1 표를 고정한 직렬 연구 기준선에서, 실제로 소비한 warm-ambient hail 상태 하나의 **조건부 수치 검증은 완료**했다. 생산 WRF·UDM·RTE, 기본 정책, 계수표는 바꾸지 않았다. 실제 융해·젖은 우박의 물성, 입자모양, 액체 함량, 예보 정확도는 승인하지 않는다. 주변 공기온도를 액체 함량으로 해석하거나 새 온도 guard를 넣지 않는다.

기준 main은 PR197 병합 `ce3d1e46503c0bee1f71005e7024e83add7ed1ed`, 전체 tree `3cd893040359e7e015a2f61d56206cdf69a9c6f6`이다. PR197의 native SW 마감, 기존 음수 수정·cold 하루·동일 코드 재시작 성과를 다시 수행하지 않았다. 원래 forcing의 한 시간 cold 실행 두 개로 선택 관측과 public capture만 보완했다.

## 실제 상태의 선택과 재현

선택 기준은 독립 광학 계산 전에 고정했다. 기존 하루에서 hail 물경로가 중요했던 source 3000초의 실제 8,910개 기주 중 **따뜻한 주변층(T>273.15 K)의 hail 물경로가 가장 큰 기주**, 그 안의 가장 큰 양의 warm hail 층이다. 광학 오차를 최대화하는 선택이나 대기 대표성 표본은 아니다.

| 실제 소비량 | 값 |
|---|---:|
| WRF 위치 / native 층 | i=42, j=30 / 17 |
| LW source / radiation step | 3000 s / 51 |
| 층 온도 | 276.97808837890625 K |
| 층 hail 물경로 | 2425.99609375 g/m² |
| 실제 λ | 422.9497375488281 m⁻¹ |
| 기주의 warm hail 물경로 | 7061.392705440521 g/m² |
| native / 확장 포함 층수 | 44 / 57 |

실제 면적을 사용한 전체 warm hail 물경로 0.0030475750717284013 kg/m²는 기존 source reduction과 6.51×10⁻¹⁸ kg/m² 차이다. 선택 관측 실행과 별도 public capture 실행은 각각 기존 수정 cold 기준의 00·01시 **450/450 배열**과 같다. 서로 다른 두 기상 사례로 집계하지 않는다.

Capture의 전체 입력을 소비한 public column은 비-WRF wrapper 결과를 모두 정확히 재현한다. 실제 **UDM population0와 CU population1을 구분**하고 CU의 LWP/IWP/REL/REI, 16밴드 방사율, 기체·mask·seed·상단을 유지했다. Capacity0 호출은 optional native capacity를 공급하지 않은 실제 경로를 그대로 재현했다.

## A/B/C의 의미

| 경로 | 같은 실제 상태에서의 hail 흡수 |
|---|---|
| A | 실제 고정 표의 조회값 |
| B | 같은 원 생성기·SOCRATES binary·order128·50 cm⁻¹ 규약으로 직접 계산 |
| C | MiePython 3.0.2 커널과 별도 PSD·분광 적분으로 직접 계산 |

세 경로는 같은 정적 Warren–Brandt ice-Ih, 균질 구형 입자, 지수형 number-diameter PSD, 밀도 912 kg/m³, 주변 매질 1, 밴드 경계와 실제 온도의 Planck thin 평균을 사용한다. B−A는 같은 방법 안의 표 조회/직접 계산 차이이며, C−B는 커널과 적분 방법의 차이가 함께 들어 있다. 두 차이를 순수 물성 오차 또는 순수 분광 오차로 부르지 않는다.

독립 경로는 log(λD) Gauss–Legendre, λD∈[10⁻⁶,40], 무한 지수 PSD의 해석적 질량분모 πρ/λ⁴를 사용한다. 반경 격자로 잘린 질량으로 다시 정규화하지 않는다. 정적 굴절률 보간 절점으로 분광 구간을 나누고 각 구간에서 Gauss–Legendre 적분한다. Ext/sca/abs/sca·g 모멘트, 단색 값·노드·가중·Planck source를 저장했다. 음의 흡수는 잘라내지 않는다. 기록한 기하학적 tail은 인증된 광학 오차 상계가 아니다.

16개 LW 밴드 모두 fine(512 반경 노드/절점 구간당 분광 degree8), radius-half(256/8), spectral-half(512/4)에서 사전 수치 기준인 **각 축 흡수 변화 ≤1%**를 통과했다. 최대 상대 변화는 반경 1.286×10⁻⁶, 분광 8.430×10⁻⁷이다. 이 기준은 물리 허용오차 또는 현 표의 정확도 기준이 아니다. 마지막 두 수준 차이도 엄밀한 참오차 상계가 아니다.

기존 SOCRATES/MiePython 비JIT 20개 회귀를 재사용하고, 실제 상태의 9개 x·굴절률에서 JIT/비JIT를 추가 대조했다. 패키지 3.0.2와 소스 해시가 기존 근거와 같다. 원 생성기·binary·quadrature·물질 해시는 `identity.json`과 archive의 context에 연결한다. 정적 ice-Ih 자료를 온도 의존 또는 wet-hail 자료로 승격하지 않는다. [원 물질자료와 보간 안내](https://atmos.uw.edu/ice_optical_constants/), [고정 MiePython 3.0.2 소스](https://github.com/scottprahl/miepython/tree/v3.0.2).

## 실제 수송 전파

Public A, hook 비활성 A, B, C-fine, C-radius-half, C-spectral-half의 **실제 column 프로세스 6회**를 실행했다. 격리한 renamed adapter의 hail 조회 직후 한 지점에서 **선택한 한 층의 16밴드 흡수만** 대입했다. 물경로·PSD·온도·기체·구름·CU·rain·graupel·mask·경계·clear 결과와 비선택 hail 층은 유지된다. 원본 adapter는 수정하지 않는다.

| 같은 native 위치의 working-precision 최대 절대차 | UP/DN, W/m² | 층 가열률, K/day |
|---|---:|---:|
| B−A | 4.94204×10⁻⁵ | 9.97490×10⁻⁶ |
| C−B | 9.28397×10⁻⁵ | 1.88744×10⁻⁵ |
| C−A | 1.42260×10⁻⁴ | 2.88493×10⁻⁵ |

Signed 배열에서 같은 위치의 (B−A)+(C−B)=C−A를 검사한다. 각 최대값을 더하거나 빼지 않는다. 이 상태의 지표·native 상단·기주 순수렴량 차이는 working precision에서도 정확히 0이다. 내부 경계와 층의 차이는 위와 같이 비영값이다. 이를 다른 상태의 오차 상한이나 국소 영향 없음으로 해석하지 않는다.

축별 변화 절댓값 합의 경험적 규모는 native flux 2.888×10⁻¹¹ W/m², 가열률 5.865×10⁻¹² K/day다. 소비 REAL32에서는 두 변화가 0으로 반올림되므로 working precision을 함께 보존한다. 실제 소비 C−A 최대값은 1.52588×10⁻⁴ W/m²와 2.88486×10⁻⁵ K/day이다. 현 표와 C의 최대 상대 흡수 차이는 약 0.34149%이나, 이를 실제 입자의 광학 오차율로 쓰지 않는다.

## 적용 판정과 종료 범위

선택 상태의 **같은 구형 ice-Ih·지수 PSD 수학 문제**에 대한 독립 수치 참조와 실제 수송 전파는 완료다. 현 계수를 변경할 포팅 결함이나 물리적 교체 근거는 확인하지 않았다. 기존 frozen1은 **고정한 experimental 직렬 연구 구성에 한해 유지**하고, 일반 예보·실제 융해/젖은 hail 정확도는 범위 제한으로 남긴다.

물리 허용량과 실제 입자에 대한 참조/대표성 불확실도는 `null`이다. 실제 입자의 상·액체 함량·형상에 대한 근거 없이 온도만으로 입자를 삭제하거나 wet fraction을 만들지 않는다. 전체 물·에너지 보존, 기존 일곱 종료 조건, RFMIP/LBLRTM과 관측 정확도를 이번 성공으로 PASS 처리하지 않는다. 다음 과학적 판정에는 해당 입자 상태의 적격 물성 또는 관측 근거가 필요하며, 동일한 구형 Mie/column 계산의 반복을 필수 과제로 다시 올리지 않는다.

## 저장 검증과 실행 범위

```sh
python3 -I -S validation/rrtmgp37/frozen-important-state-reference/verify_saved.py
python3 -I -S validation/rrtmgp37/frozen-important-state-reference/test_saved.py
```

저장 재생은 표준 라이브러리만 사용하며 새 WRF·Mie·RTE를 실행하지 않는다. 실제 신규 계산은 원래 한 사례의 한 시간 WRF 2회, 독립 축별 밴드 적분 48회, 원 방법 직접 적분 16회, 실제 상태 JIT/비JIT 9쌍, column 6회다. Helper/caller의 증분 compile/link 명령은 총 10개이며, 전체 WRF clean build나 새 하루/재시작 캠페인이 아니다.

대형 NetCDF는 로컬에서 직접 배열 비교했고 archive에는 각 배열·파일 해시를 보존한다. Portable replay가 NetCDF를 새로 읽었다고 주장하지 않는다. 원 물질자료는 URL·해시만 보존하며 재배포하지 않는다. Standalone Python 적분의 PID는 기록하지 않았고 성공 로그·완료 결과·실행 소스를 보존한다. WRF/column은 command receipt의 PID·종료 상태에 연결된다. 계수 context-after는 완료 후 확인이며 pre-run snapshot으로 재명명하지 않는다.

초기 bootstrap의 Numba cache 디렉터리 충돌과 CU 입력을 빠뜨린 caller의 사전검사 실패는 development 자료로 보존한다. 후자는 RTE 프로세스 실행 전에 거부됐으며 적격 결과에 포함하지 않았다. 최종 caller는 실제 CU 입력을 전달하고 actual capture와 일치한다.

의미 반례 7개는 잘못된 선택 층·밀도 정규화, 축 혼합, 미수렴 승격, 비선택 clear flux 변경, 물리 승인 승격, 비교 변수 누락을 거부한다. `result.json`에는 16밴드 계수와 native signed profile 및 두 정밀도의 결과를 보존한다.
