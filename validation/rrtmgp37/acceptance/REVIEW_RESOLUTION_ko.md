# 이전 검토 지적 해소 체크리스트

기준 main: `a91d0d855da3e24094c2e6c7ba1088b56bc8c461`, tree `887d3fd1cf8c097219b201b1bdb9cdd428d593a9`. UDM27–RRTMGP37 전용.

구현, 분기 검증, main 반영, 통합 검증을 구분한다. [PR146](https://github.com/gonos2k/wrf-rrtmgp/pull/146)은 startup·Registry·ZZ runtime/I/O, 별도의 [PR147](https://github.com/gonos2k/wrf-rrtmgp/pull/147)은 보존 RFMIP/Nc 증거를 main 기반으로 통합한다. 두 PR 모두 병합 전이므로 기준 main에 반영됐다고 표시하지 않는다. 원래 19개 gate와 current 12개 항목은 [기존 index](checklist.json)에 그대로 보존한다. `production_accepted=false`.

| ID | 우선 | 항목 | 구현 | 기준 main | 후보 통합 검증 |
|---|---|---|---|---|---|
| INT-135 | P2 | Startup 실행기·전 밴드·capture OFF/ON | 완료 | 미반영 | PASS_SCOPED |
| INT-136 | P1 | Registry subgrid_x/y 기본값 | 완료 | 미반영 | PASS_SCOPED |
| INT-137 | P1 | Ordered ZZ NetCDF 저장·읽기 | 완료 | 미반영 | PASS_SCOPED |
| INT-BUILD | P1 | 통합 소스 Make/CMake 및 remote CI | 완료 | 미반영 | PASS_SCOPED |
| INT-RESTART | P1 | 통합 실행파일 MPI checkpoint/restart | 완료 | 미반영 | PASS_SCOPED |
| EVD-RFMIP | P2 | Historical/current RTE×optics 증거 연결 | 완료 | 미반영 | PASS_SCOPED_SAVED_EVIDENCE |
| EVD-NC | P2 | Nc 양성·activation·부분구름 단계 증거 연결 | 완료 | 미반영 | PASS_SCOPED_SAVED_EVIDENCE |
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

각 항목의 종료조건·범위·증거는 [기계 판독 체크리스트](review-resolution-checklist.json)에 있다. `PASS_SCOPED`는 명시된 범위의 성공이다. `OPEN`, `FAIL`, `NOT_RUN`을 CI PASS나 PR 수로 닫지 않는다.

새 [terminal 증거](../main-runtime-io-integration-terminal/README_ko.md)는 실행한 PR146 head `dd7eb1d`와 merge-test의 동일 tree에 결속한다. 원격 11개 check가 모두 성공했고, 로컬 fresh MPI4×OpenMP2 빌드·설치와 13h control/12→13h restart가 두 구성에서 성공했다. 660개 ordered ZZ sentinel 값과 같은 arm의 history 4번 228개·37번 231개 배열/변수 속성이 정확히 유지됐다. 전역 `START_DATE` 차이는 별도 기록했다. `multi_perturb=0` I/O 시험이므로 활성 확률물리·McICA 난수열 승인은 아니다.

PR147의 6개 saved verifier와 12개 manufactured controls는 통과했다. 과거 RTE/모델 호출 수는 새 실행 수가 아니다. 원래 package/hash를 유지하고, historical verifier의 분석 파일 재작성을 임시 복사본 안으로 격리했다. PR147 자료는 PR146 tree에 들어 있다고 주장하지 않는다.

Nc 조사에서는 `ccn_conc`의 체적 단위와 QNN/QNC의 Registry 질량 단위 표기, 단위 변환 없이 직접 전달하는 경로가 확인됐다. 어느 표기/producer가 의도된 계약인지 확정할 authority가 없으므로 Nc·population과 PSD/LUT 유효크기 항목은 OPEN으로 유지한다. RFMIP strict 21개 실패와 LBLRTM negative OD FAIL도 유지한다. 다음 종료조건은 물리 입력 계약·승인 가능한 reference 및 최종 병합 정책의 장시간/관측 검증이다.

[최초 focused 증거](../main-runtime-io-integration/README_ko.md)는 당시 상태를 보존하며 terminal 기록으로 덮어쓰지 않는다.
