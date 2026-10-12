# 기존 PHY-NC 후보 구현 점검

| 경계 | 결과 | 제한 |
|---|---|---|
| Host η → UDM n → host η | PASS_SCOPED | 한 호출의 동일한 dry density; 다음 호출에서 새 밀도 |
| 체적 CCN cold background | PASS_SCOPED | 상수 초기화; 외부 QNN 보존 아님 |
| 입구 제한과 최종 과정 반환 | PASS_SCOPED | 기존 체적 제한 그대로; 새 최종 clipping 없음 |
| Partial CF/activation, 두 밀도, 비활성 cap/floor | PASS_SCOPED | 실제 전체 UDM의 제조 조건 |
| 최종 반경/반사도 소비 | PASS_SCOPED | 체적 number 사용; LUT 모멘트 물리 승인 아님 |
| 저장/수송 표현 | PASS_SCOPED | 실제 periodic SCM와 기존 scalar_adv_opt=0; 다른 수송/경계 캠페인 미승인 |
| Metadata/restart | PASS_SCOPED | tagged eta; raw 재해석 거부, 120s control와 재개 일치 |
| Real/ideal/경계 producer | UNSUPPORTED_EXPLICIT | 새 표현을 생산하지 않는 경로의 잘못된 표기 거부 |
| Legacy 기본값 | PASS_SCOPED | 이전 실행파일과 211 변수×13시각 일치 |
| 과거 source 재생과 현재 후보 분리 | PASS_SCOPED | 원 hash/snapshot 보존; 현재 소스 별도 검증 |
| PHY-NC 최상위 물리 승인 | OPEN | 자체 정책 후보와 원 의도/물리적 적용성은 구분 |

새로운 최상위 gate를 만들지 않습니다. PSD/LUT는 종별 모멘트·생성 정의의 지원/미지원 판정으로, 발생분율은 #169와 다른 가설의 독립 근거로, reference는 기존 FAIL을 보존한 승인 경로로 이어집니다. 기존 occurrence-one 실험이나 number 선택표를 반복하지 않습니다.
