# 실제 UDM–Thompson 액체 반경 커널 대조

기준 main은 `42641d19d5cd5cf4b3b124270d365aa973be7727`, 전체 tree는
`4ccaf55b452f329780465b27b742956a07c01f26`이다. PR153 제출 head와 병합 main의
전체 tree가 같으며 [PR153](https://github.com/gonos2k/wrf-rrtmgp/pull/153)의
11개 check가 terminal SUCCESS인 상태를 `pr153-terminal.json`에 보존한다.
일반 WRF run `37591785004`, CMake run `37591785031`은 과거 원격 실행이다.
이번 로컬 비교의 WRF 실행 횟수에 합산하지 않는다.

전체 `module_mp_thompson.F`와 `module_mp_udm.F`를 GNU 13.3 REAL32로 컴파일해
실제 `calc_effectRad` 및 `udm_mp_effective_radius`의 액체 경로를 호출했다.
UDM은 실제 `udminit`을 사용한다. Thompson의 별도 시험 사본은 private flag
`is_aerosol_aware`와 실제 초기화 식 `obmr=1./bm_r`만 설정한다.
**`thompson_init`, CCN/충돌 테이블, WRF 8/28 routing을 실행한 시험이 아니다.**
실제 helper 본문은 바꾸지 않았고, 시험 bridge와 관측 호출을 제거하면 원본 source
bytes가 복원된다. 초기화·timing/host 모듈의 shim과 미사용 procedure section 제거는
액체 커널을 링크하기 위한 시험 장치다. 생산 Fortran·Registry·UDM27-only gate는 그대로다.

## 입력과 결과

`T=285 K`, `qv=0.008`, `qc=10^-4`이고 `qi=qs=0`이다. Thompson 자체의 밀도식을
역으로 이용해 압력을 구성한다. UDM에도 실제로 계산된 같은 건조밀도를 전달한다.
이는 helper 입력을 일관되게 제조한 것으로, 정역학 기둥이나 실제 WRF 예보가 아니다.
입력 배열의 비트가 호출 전후 유지되는지도 검사한다.

| 비교군 | 입력 수농도의 해석 | ρ≈0.7 반경 μm | ρ≈1.1 반경 μm |
|---|---|---:|---:|
| Thompson fixed-volume kernel | 내부 고정 `Nt_c=10^8`, μ=12 | 5.911622 | 6.872872 |
| Thompson aerosol-aware kernel | host mass-number `5×10^7`; 내부 ρN, μ=15 | 8.285250 | 8.285250 |
| Thompson aerosol-aware high-number | host `3×10^8`; 내부 ρN, μ=7/5 | 4.799018 | 4.949638 |
| UDM fixed-raw kernel | raw `5×10^7` 그대로 | 6.939790 | 8.068223 |
| UDM conditional volume-number arm | **가정**: raw=ρ×`5×10^7` | 7.815924 | 7.815924 |

값은 O0의 실제 반환이며 O2도 허용범위에서 같은 관계를 만족한다. Thompson에서
질량과 수농도의 밀도 변환이 상쇄되는 것은 **같은 PSD shape인 선택 군**의 결과다.
높은 number 군은 shape가 달라져 반경이 달라짐을 따로 확인한다. UDM의 고정 raw
군과 Thompson 고정 체적 군은 약 `(1.1/0.7)^(1/3)`의 밀도 반응을 보인다.

Thompson은 lookup 대신 독립 gamma moment 비율 `(μ+1)(μ+2)(μ+3)`로 계산한
`re=(μ+3)/(2λ)`와 대조한다. UDM은 실제 `pidnc`, raw number와 밀도 기반 질량의
대수 관계를 검사한다. **UDM의 해당 식이 승인된 광학 PSD 모멘트라는 증명은 아니다.**
REAL32 피연산자의 곱·나눗셈 순서를 반영하되 Python power/최종 나눗셈은 binary64다.
따라서 상대 허용범위 `2×10^-6`/`3×10^-6` 내 일치이며 native-kind 비트/ULP 재생이 아니다.
이 범위는 published RFMIP strict 기준을 바꾸지 않는다.

## 검증 범위와 실행 기록

O0/O2마다 bridge-only, observer OFF, observer ON을 실행했다. 반환 비트는 세 군에서
동일하고, kernel flag를 8→28→8→28로 전환한 재호출도 비트가 같다. Number cap과
반경 제한은 선택 군에서 비활성이다. 잘못된 number 변환·관측 누락·shape·반경 clamp·
조건부 입력군 변조는 checker가 거부한다.

최종 v3은 compile/link 22회, fixture process 6회, compiler version query 1회다.
**72는 12 helper 호출×6 process**이며, **24는 ON 관측 12개×O0/O2**다.
12개 중 2개는 state 전환 뒤 동일 입력 재호출이므로 서로 다른 설정은 10개다.
독립 기상 사례 72개·24개라는 의미가 아니다. 전체 WRF build/host·Thompson init·
MPI·RTE·광학/플럭스·예보 실행은 0회다.

`attempt-summary.json`은 v1 anchor 검사 실패(compiler child 없음), v2 통과 후 checker
입력군 검증 보강, 최종 v3 통과를 구분한다. 과거 receipt/hash는 고치지 않았다.
v1/v2는 개발 receipt 기록이고, 완전한 source/stdout 대조는 최종 v3을 기준으로 한다.

현재 소스로 새 실행:

```sh
python3 WRF/test/rrtmgp/test_udm_thompson_radius.py WRF --workdir /fresh/radius-kernel-run
```

보존 byte와 결과의 재검산(compiler/model 실행 없음):

```sh
python3 -I -S validation/rrtmgp37/udm-thompson-cloud-radius/verify_saved.py
```

팀은 source·작은 receipt metadata만 독립 검토했다. compiler/helper 실행과 원시 상태
판독은 root가 담당했다. `reviews/`에 원본 source, checker, scope 검토를 보존한다.

## 남은 판정

Thompson28의 명시적인 number→density→PSD 경계가 대조군으로 동작함을 확인했다.
이 사실로 UDM host의 QNN/QNC 단위·population을 확정하거나 밀도/CF 배율을 채택하지
않는다. QNN의 맑은 부분 CCN, scalar transport, UDM PSD/LUT, ice/snow와 발생분율은
별도 계약이다. Thompson37 gate 해제·복사/예보 우열도 주장하지 않는다.
후속 checklist **15 PASS_SCOPED / 7 OPEN·FAIL·NOT_RUN**, 원래 acceptance
**original19/current12**, `production_accepted=false`를 유지한다.
