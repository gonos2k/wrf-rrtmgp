# UDM27 싸락눈·우박 광학의 독립 수치 기준

현재 남은 `qg/qh` 복사 연결을 검토하기 위한 **실험적 동질 얼음 구형입자
기준 계산**입니다. WRF 실행 경로의 싸락눈·우박 지원 완료나 관측 정확도를
의미하지 않습니다. 현재 양의 우박 거부 정책은 유지됩니다.

부모는 PR #17의 `62ca59d8b0c4b8f5027b3406898798814059cc8b`이며,
[해당 CI 7개 작업](https://github.com/gonos2k/wrf-rrtmgp/actions/runs/37048069079)은
전체 WRF GNU 직렬 SCM까지 모두 PASS했습니다. 이번 자료의 핵심은 새 광학
계산의 재현성과 수치 검증입니다.

## 실제로 확인한 것

| 검사 | 결과 |
|---|---|
| 공개 MIEV0 수치 3사례 | 반올림된 논문값 허용범위 내 일치 |
| 별도 miepython 3.0.2 구현 20사례 | PASS, Qext/Qsca 최대 절대 차이 5.17e-11, g 1.99e-11 |
| 큰 입자 recurrence workspace | 고정 400000 제한의 거부를 재현하고 동적 workspace로 계산 |
| 기본 COMPLEX 정밀도 결함 | 실제 약한 흡수 입력에서 수정 전 Qsca>Qext, 수정 후 정상·독립값 일치 |
| 해석적 PSD 및 SW/LW source 변환 | PASS |
| 분광 chunk와 전체 적분의 관계 | 일정/변화 효율·주야 source의 해석적 시험 PASS |
| 안정적 Gauss–Laguerre 규칙 | 4–1024차 다항식 모멘트, 256차까지 별도 규칙과 일치 |
| 잘못된 수치 제어값 | 14종 조기 거부 |
| 잘못된 표·task·source·binary identity | 21종 거부 |
| 최종 완결된 band task | 6개 자료 집합, 총 420개 |

SOCRATES 원본은 지정 commit과 byte-identical로 보존합니다. 실행 시 생성한
복사본의 `CMPLX` 네 곳에만 `KIND=RealK`를 넣고 diff와 source hash를
기록합니다. 계수를 물리 범위로 강제 투영하여 문제를 숨긴 수정이 아닙니다.

초기 SciPy special-function 512차 실행은 비유한 가중치를 반환했고, 이전
generator는 이 경우 0인 계수를 만들었습니다. 해당 출력은 invalid로 보존한
뒤 이번 유효 자료에서 제외했습니다. 최종 generator는 고유값으로 규칙을
구성하고 유한성·면적·질량 모멘트를 검사한 뒤에만 분광 작업을 시작합니다.

## 수렴 측정은 완료 판정과 다릅니다

세 PSD slope `300/2000/20000 m-1`, 네 Planck 온도 `180/233/250/300 K`를
시험했습니다. 256/512차는 차이가 가장 큰 `lambda=20000`에 한정했습니다.
아래 값은 각 계수 차이를 같은 위치의 reference extinction 계수로 나눈
최댓값입니다. `W/m2` 플럭스 오차나 실제 예보 오차율로 해석하지 않습니다.

| 비교 | 범위 | 최대 extinction-normalized 차이 |
|---|---|---:|
| 32 → 64차 | 3 slopes, 50 cm-1 | 0.5548% |
| 64 → 128차 | 3 slopes, 50 cm-1 | 0.4819% |
| 128 → 256차 | 20000 m-1, 50 cm-1 | 0.4383% |
| 256 → 512차 | 20000 m-1, 50 cm-1 | 0.2203% |
| 50 → 25 cm-1 | 64차, 3 slopes | 0.3860% |

이 행렬은 **전체 수렴을 입증하지 않습니다.** 적분 차수, 분광 간격 및 실제
보간 격자·온도축을 추가 검증해야 합니다. 비교기는 명시적인 수치 허용값을
주지 않으면 PASS를 만들지 않고 차이만 보고합니다.

## 표의 물리량과 적용 한계

`N(D)=N0 exp(-lambda D)`와 구형 `m=rho_bulk*pi*D^3/6`에서 질량 정규화한
`kappa*rho_bulk [m-1]`를 저장합니다. UDM graupel 500, hail 912 kg/m3로
나누면 `kappa [m2/kg]`이고 실제 path `[kg/m2]`와 곱하면 optical depth입니다.
`lambda`는 유효반경이 아닙니다. UDM의 고정 N0/cutoff/cap과 반환된 상태에서
재구성한 slope가 정확한 침강 전 process slope를 뜻하지도 않습니다.

얼음 자료는 정적 Warren–Brandt ice-Ih이고, SW 가중은 NOAA NNLSSI1
BaselineModel입니다. RRTMGP gas의 NRLSSI2를 재현한 것이 아닙니다.
LW 온도축은 Planck 가중에만 적용됩니다. 장파의 흡수와 산란을 별도 저장하므로
흡수 전용 해법에서 extinction을 absorption으로 사용할 수 없습니다.

입자 밀도를 질량 정규화에 쓴 것만으로 다공성·wet coating·비구형 광학이
결정되지는 않습니다. 이것은 공개 소스에 근거한 명시적 실험 모델이며 NOAA
내부 UDM의 실제 광학 구성이나 관측 정확도를 입증하는 자료가 아닙니다.

## 재현과 파일 계보

[도구·수식·실행 명령](../../../tools/udm_frozen_optics/README.md)의 경로는 저장소
루트 기준 `tools/udm_frozen_optics/README.md`입니다. 생성된 각 `gw-*` 폴더에는
표, 완결 task receipt, 원본/수정 source identity와 diff가 있습니다. 원시 solar/
ice-index 자료는 pin을 확인해 별도로 가져오며 이 폴더에 재배포하지 않습니다.

`checks/`는 커널·독립 구현·규칙·제어값·artifact 거부 시험의 원문 receipt입니다.
`final-*.json`은 원래 실행 디렉터리에서 source 및 local library를 검사한 비교
결과입니다. 이 저장소의 portable 자료에는 binary 자체가 없으므로 local
library 확인은 원래 실행 결과의 hash 근거이며 binary 재배포가 아닙니다.
현재 comparator로 portable 표/task와 해당 checkout의 source identity를
검사할 수 있습니다. `provenance.json`, `manifest.json`이 파일 계보를 묶습니다.

다음 단계는 실제 UDM 상태 범위의 보간 검증, occurrence/path 정책, 선택
가능한 실험적 WRF 연결, same-state replay 및 우박이 생기는 장시간 사례입니다.
이 자료만으로 그 단계가 완료되었다고 표시하지 않습니다.
