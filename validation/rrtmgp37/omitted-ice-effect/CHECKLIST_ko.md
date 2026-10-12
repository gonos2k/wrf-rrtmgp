# 완료 가속 체크리스트 — #168 이후

고정 종료 조건은 `closure-conditions.json` 원문 그대로입니다. 기존 15개 제한적 완료와 #168 실제 호출 연결을 유지합니다.

- [x] Number의 다음 구현 목표를 dry-number-grid-v1으로 명시: host ηdry ↔ native nvolume, 단위·집단·cold/boundary/return/checkpoint와 density 변환 경계 정의.
- [x] 현재 raw 직접 전달을 새 계약 구현으로 승인하는 해석, native size/LUT 모멘트 자동 동등성, 경험적 density/CF/radius 배율을 기각.
- [x] #168 실제 네 기주의 A baseline을 공통 모든 기록에서 비트 재현.
- [x] 추가 경로 0인 Z control이 A를 비트 보존함을 확인.
- [x] 누락 빙정만 occurrence-one 광학 성분으로 추가한 B를 실제 공개 column/RTE로 계산.
- [x] 공통 CF·기존 mask/광학 성분/반경·기체·경계 고정과 extra-only SW single delta scaling 검증.
- [x] 새 ice raw extinction을 SW unscaled direct 진단에도 포함하고 solver flux와 WRF-convention SWDOWN 구분.
- [x] 모든 층/경계/band의 Δoptics·Δflux·Δheating 저장; WP64/REAL32 출력과 에너지 산술 폐합 구분.
- [x] LW 3쌍, SW 35쌍/기주의 paired-seed 영향·spread 평가와 불확실성 범위 명시.
- [x] 실제 process/RC·준비 오류·재사용·최종 적격 자료를 구분해 봉인하고 기존 CI에 재생 연결.

이번에 해소한 하위 작업은 고정 상태의 누락 ice 단독 영향과 정책 판단 근거입니다. 같은 상태의 경로·해시 관측을 다시 최상위 gate로 올리지 않습니다.

| Gate | 현재 | 다음 완료 산출물 |
|---|---|---|
| PHY-NC | OPEN | 선택한 dry-number-grid-v1의 전 경계 구현과 기존 partial-CF/partial-activation/two-density 종료 실험. 정책 정의를 production 구현으로 재명명하지 않음. |
| PHY-SIZE | OPEN | 정확한 pinned LUT의 primary PSD/population/모멘트와 native 최종 크기 연결. 자동 동등성 가정은 기각했으며 근거 없는 배율은 넣지 않음. |
| PHY-OCCURRENCE | OPEN | 이번 단독 영향·seed spread를 재사용해 CF0 및 종별 발생분율 가설의 독립 광학/관측 수용성을 판단. occurrence-one을 정답이나 일반 상한으로 승인하지 않음. |
| REF-RFMIP | FAIL | 기존 strict 21 실패와 publisher 생성·저장 정밀도 계보 해결. 이번 민감도 PASS로 대체하지 않음. |
| REF-LBL | FAIL | 기존 음의 OD 실패를 보존하고 승인 가능한 독립 분광·복사 기준 확보. 완료한 내부 trace를 반복하지 않음. |
| FINAL-IDENTITY | OPEN | 선택한 최종 production 정책의 source/binary/runtime/input/coefficient/result 연결. 진단 빌드의 identity를 최종 승인으로 retag하지 않음. |
| FINAL-FORECAST | NOT_RUN | 정책 고정 뒤 사전 기준에 대한 장시간 4/37·관측 평가. 이번 고정 상태 ΔF를 coupled forecast 오차로 부르지 않음. |

`production_accepted=false`. 작은 경로 비율에 근거한 무영향 판정은 기각하지만, 균일 빙정을 생산 정책으로 채택하는 판단은 독립 근거 뒤에 합니다.
