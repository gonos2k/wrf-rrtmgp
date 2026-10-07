# 현재 UDM 부분 활성화·두 밀도 관측

PR152 최종 head `59697ca409279cc0f837c4182fb5045cdc675e46`의 11개 CI는 모두 terminal SUCCESS이다. 병합 main `d87cd50d33d3ccebb4fdaec9c69d3ae800ae9479`와 시험된 소스의 전체 tree는 `7491ad2dcfdbf4db750b7a990e16d7abae4fdabd`로 같다. 이전 head eaae의 PASS를 전용하지 않았다. 새 Nc 시험 PR의 CI 결과와도 구분한다.

이번 시험은 **현재 전체 module_mp_udm을 직접 컴파일·호출한 제조 셀 fixture**이다. 원본 모듈과 관측 call만 넣은 private 사본을 각각 컴파일하고, 원본/OFF/ON의 입력·반환값·CF epoch/top을 비교한다. 관측 블록 12개를 제거하면 원본 source bytes가 정확히 복구된다. 생산 UDM, Registry, 수농도 변환식과 복사계수는 변경하지 않았다.

최종 시도 v6는 GNU Fortran 13.3, 기본 REAL32, O0/O2, bounds 및 signaling-NaN/FPE 검사에서 성공했다. 컴파일·링크 자식16개, fixture 실행6개, compiler version 조회1개가 모두 RC0였다. 각 실행의 실제 outer UDM 호출4개로 총24호출이다. ON에서 최적화별4입력×3활성층을 관측했으므로 **최종 활성 셀 관측24개**이다. 4번째 층은 udm2d의 `ktopini=kte-1` 위에 있으며 반경 helper는 네 층 모두 호출된다. 그 층의 초기 CF=1을 진단된 구름으로 해석하지 않는다.

| 제조 입력 | 실제 CF(선행 closure) | 실제 activation fraction |
|---|---:|---:|
| rho_d≈0.7, 목표 alpha=0.35 | 0.5800508261 | 0.3499958515 |
| rho_d≈0.7, 목표 alpha=0.65 | 0.5800508261 | 0.6499993205 |
| rho_d≈1.1, 목표 alpha=0.35 | 0.5800508261 | 0.3499958515 |
| rho_d≈1.1, 목표 alpha=0.65 | 0.5800508261 | 0.6499993205 |

각 셀의 초기 T=285 K와 목표 RH를 맞추고, 실제 UDM saturation table로 QV를 구한 뒤 `p=rho_d*T*(Rd+Rv*qv)`를 구성·검사한다. 같은 원시 NN=2e8, NC=5e7을 사용하며 그 단위를 승인하지 않는다. **EOS 일관 셀이지 정역학적으로 균형 잡힌 WRF 기둥이나 실제 예보가 아니다.** 두 밀도에서 p와 qv까지 같은 상태라고 주장하지 않는다.

관측은 number adjustment 전/후, CF divide 전/후, CF restore 전/후, activation 입구/rate/출구, 반경 helper 전/후를 구분한다. 원문 순서는 다음과 같다.

```text
CF 진단 → 수상체 질량을 CF로 나눔 → 녹음/동결 과정
        → 질량을 격자평균으로 복원 → 후속 과정 → CCN activation
        → 후속 과정·반환 → native radius helper
```

따라서 activation에서 저장한 CF는 **앞선 closure 단계의 값**이다. 활성화 시점의 QC가 여전히 in-cloud라고 설명하거나 CF를 새로 진단한 것처럼 해석하지 않는다. NN/NC/NR의 immediate CF transform 불변은 코드 관측이며 number population 정의의 승인과 다르다.

선택 활성화 단계에서 엄밀히 0<alpha<1 및 양의 NC_ACT, NN-rate cap·수증기 cap·CCN floor·NC floor/max의 비활성을 확인했다. actual default-REAL 연산 순서로 NN/NC·QV/QC·잠열 T 갱신을 확인한다. NC_ACT의 질량 전환은 native처럼 **분자에서 NC_ACT를 곱한 후 3*rho로 나누며**, exp/log는 선언한 REAL32 오차범위로 비교한다. isolated activation NN+NC 잔차는 REAL32 반올림 범위이다. 전체 UDM 호출에는 다른 과정이 있으므로 raw NN+NC 불변을 요구하지 않는다. 실제 activation 직전 NC가 초기값에서 조금 변한 사실도 보존한다.

원본/OFF/ON의 전체 fixture 반환73개 REAL32 word와 epoch/top은 각 최적화에서 정확히 같다. helper 입력 불변 및 helper→outer return 조인을 검사한다. floor 강제·alpha=1·stage 누락·잠열 T 변조를 넣은 **저장 상태 대조**는 각각 거부된다. 이 부정대조를 추가 WRF 실행으로 집계하지 않는다.

`attempt-summary.json`은 준비 UTF-8 오류, 시험 모듈 중복 링크, 활성층 개수 기대값 오류 및 첫 v4 PASS 뒤 팀이 지적한 오라클 보강, v5 후 명시 CF 시점 join 보강을 보존한다. 전체 개발 시도는 compiler/link62자식, fixture21실행(outer UDM84호출), compiler version2조회이다. 최종 v6의24호출과 합산해 중복 집계하지 않는다. 이전 실패는 생산 코드 결함으로 해석하지 않는다.

`receipt.json`은 실제 working-source·compiler·executable 전후 hash, flags, 자식 PID·실제 RC를 연결한다. 미래 PR commit/tree에서 과거 fixture를 실행했다고 하지 않는다. 작은 stdout에 모든 binary32 관측을 보존하고 native/observer source는 lossless gzip으로 저장한다. executable/object/.mod는 보관 패키지에 포함하지 않는다. 로컬 전체 WRF build·WRF host·transport·MPI·RTE·LBLRTM 실행은 모두0이다. CI에서는 현재 working source를 별도로 새로 컴파일한다.

현재 소스 fresh 시험:

```bash
python3 WRF/test/rrtmgp/test_udm_partial_activation.py WRF --workdir /new/empty/udm-observation
```

과거 저장 상태만 검증:

```bash
python3 -I -S validation/rrtmgp37/partial-activation-observation/verify_saved.py
```

**PHY-NC는 계속 OPEN**이다. host producer/storage/scalar transport의 단위·질량 분모·population authority, PSD/LUT 유효크기, RFMIP strict21 FAIL, LBLRTM negative-OD FAIL, occurrence·최종 identity·예보 검증도 그대로 남는다. 이번 관측으로 밀도/CF 배율이나 Registry 단위를 선택하지 않으며 `production_accepted=false`, 완료15/잔여7 및 원래19/current12를 유지한다.
