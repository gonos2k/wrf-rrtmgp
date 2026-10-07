# 이전 검토 지적 해소 체크리스트

기준 main: `a91d0d855da3e24094c2e6c7ba1088b56bc8c461`, tree `887d3fd1cf8c097219b201b1bdb9cdd428d593a9`. UDM27–RRTMGP37 전용.

구현, 분기 검증, main 반영, 통합 검증을 각각 기록한다. 아래 candidate는 main 기반 통합 PR의 변경이며 병합 전에는 main 반영으로 표시하지 않는다. 원래 19개 gate와 current 12개 항목, 독립 reference FAIL, `production_accepted=false`는 [기존 index](checklist.json)에 보존한다.

| ID | 우선 | 항목 | 구현 | 기준 main | 통합 검증 |
|---|---|---|---|---|---|
| INT-135 | P2 | Startup 실행기·전 밴드·capture OFF/ON | 완료 | 미반영 | PASS_FOCUSED_RUNTIME_PENDING |
| INT-136 | P1 | Registry subgrid_x/y 기본값 | 완료 | 미반영 | PASS_FOCUSED_RUNTIME_PENDING |
| INT-137 | P1 | Ordered ZZ NetCDF 저장·읽기 | 완료 | 미반영 | PASS_FOCUSED_RUNTIME_PENDING |
| INT-BUILD | P1 | 통합 소스 Make/CMake 및 remote CI | 완료 | 미반영 | NOT_RUN |
| INT-RESTART | P1 | 통합 실행파일 MPI checkpoint/restart | 완료 | 미반영 | NOT_RUN |
| EVD-RFMIP | P2 | Historical/current RTE×optics 증거 연결 | 완료 | 미반영 | NOT_RUN |
| EVD-NC | P2 | Nc 양성·activation·부분구름 단계 증거 연결 | 완료 | 미반영 | NOT_RUN |
| PHY-NC | P1 | Nc 단위·population·부분 activation | 미완료 | 미반영 | OPEN |
| PHY-SIZE | P1 | UDM PSD 모멘트와 pinned LUT 유효크기 | 미완료 | 미반영 | OPEN |
| REF-RFMIP | P1 | Published RFMIP strict | 미완료 | 미반영 | FAIL |
| REF-LBL | P1 | LBLRTM negative OD와 앞단 누적 | 미완료 | 미반영 | FAIL |
| PHY-OCCURRENCE | P1 | CF0 강수·qg/qh 발생/재료 정책 | 완료 | 반영 | OPEN |
| FINAL-IDENTITY | P2 | 최종 tree·실행·입력·정책 identity | 완료 | 반영 | OPEN |
| FINAL-FORECAST | P1 | 최신 정책 장시간 예보·관측 | 완료 | 미반영 | NOT_RUN |
| DONE-STARTUP | P1 | 초기 BG snow native diagnosis | 완료 | 반영 | PASS_SCOPED |
| DONE-STORAGE | P1 | Registry 실제 POINTER/ALLOCATABLE 저장형식 | 완료 | 반영 | PASS_SCOPED |
| DONE-EVD-PIN | P1 | Historical/current-source 검증 분리 | 완료 | 반영 | PASS_SCOPED |

각 항목의 종료조건·범위·evidence는 [기계 판독 체크리스트](review-resolution-checklist.json)에 있다. `PASS_SCOPED`는 명시된 시험 범위만 뜻한다. `OPEN`, `FAIL`, `NOT_RUN`을 CI PASS나 PR 병합 개수로 닫지 않는다.

먼저 INT-135→INT-136→INT-137의 검증된 변경을 통합한다. 다음은 새 통합 tree의 build/restart 검증과 evidence dependency 연결, 그 뒤는 Nc/입자 크기·독립 reference 및 최종 forecast 판정이다.

첫 묶음의 [새 focused 실행](../main-runtime-io-integration/README_ko.md)은 8개 상위 검사 RC0이다. 실제 모델 OFF/ON과 전체 build/restart 종료조건은 아직 별도이며, 자동으로 main 반영이나 과학적 승인으로 닫지 않는다.
