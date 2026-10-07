# 이전 검토 지적 해소 체크리스트

현재 기준 main: `457cde630bbeb41a24c09baa1f536c73622b615f`. UDM27–RRTMGP37 전용.

PR #146–#150은 main에 병합됐다. 기존 실행의 source pin·범위는 그대로 보존하며, 현재 전체 tree에서 모든 과거 모델을 새로 실행했다고 주장하지 않는다. PR #149의 NetCDF guard와 기본 namelist 검사는 main에 반영됐고 정확히 같은 tree에서 11개 CI가 성공했다. PR150의 추가 scalar 경계 수정도 main에 반영됐다. 새 I/O 세 항목은 후보 분기에서 실제 backend 시험을 통과했으며 아직 main에 들어가지 않았다.

후속 해소 목록은 **후보 기준 22개 중 15개 PASS_SCOPED, 7개 OPEN/FAIL/NOT_RUN**. 현재 main은 12개 제한적 완료이고 새 I/O 3개는 통합 전이다이다. 이것은 원래 acceptance의 **19개 gate + current 12개 항목**과 다른 작업 목록이다. [원래 index](checklist.json)는 변경하지 않았고 `production_accepted=false`를 유지한다.

| ID | 항목 | 현재 main 반영 | 검증 상태 |
|---|---|---|---|
| INT-135 | Startup 실행기·전 밴드·capture OFF/ON | 반영 | PASS_SCOPED |
| INT-136 | Registry subgrid_x/y 기본값 | 반영 | PASS_SCOPED |
| INT-137 | Ordered ZZ NetCDF 저장·읽기 | 반영 | PASS_SCOPED |
| INT-BUILD | 통합 Make/CMake·CI | 반영 | PASS_SCOPED |
| INT-RESTART | MPI checkpoint/restart | 반영 | PASS_SCOPED |
| EVD-RFMIP | 보존 RTE×optics 증거 | 반영 | PASS_SCOPED_SAVED_EVIDENCE |
| EVD-NC | 보존 Nc 단계 증거 | 반영 | PASS_SCOPED_SAVED_EVIDENCE |
| PHY-NC | Nc 단위·population | 내부 근거만 반영 | OPEN |
| PHY-SIZE | PSD/LUT 유효크기 | 미확정 | OPEN |
| REF-RFMIP | Published strict reference | 실패 보존 | FAIL |
| REF-LBL | LBLRTM negative OD | 실패 보존 | FAIL |
| PHY-OCCURRENCE | CF0 강수·qg/qh 물리 정책 | 실험 경로 반영 | OPEN |
| FINAL-IDENTITY | 최종 승인 실행 identity | 기반 반영 | OPEN |
| FINAL-FORECAST | 최종 정책 장시간·관측 | 과거 범위 근거 유지 | NOT_RUN |
| DONE-STARTUP | 초기 BG snow native 진단 | 반영 | PASS_SCOPED |
| DONE-STORAGE | Registry 저장형식 계약 | 반영 | PASS_SCOPED |
| DONE-EVD-PIN | Historical/current-source 분리 | 반영 | PASS_SCOPED |
| P2-IO-HELPER | NetCDF short-token 오류 경로 | 반영 | PASS_SCOPED |
| P2-NML | Namelist group·중복 key 및 scalar 경계 | 반영 | PASS_SCOPED |
| P2-IO-VARINFO | 변수정보 wrapper 인자 수 | 후보 수정 | PASS_SCOPED_CANDIDATE |
| P2-IO-LENGTH | Memory-order 길이·padding | 후보 수정 | PASS_SCOPED_CANDIDATE |
| P2-IO-WRITE-SIDE-EFFECT | Invalid write의 시간 기록 | 후보 수정 | PASS_SCOPED_CANDIDATE |

[기계 판독 목록](review-resolution-checklist.json)은 항목별 종료조건·실행 범위·근거를 제공한다. [새 P2 검증](../helper-error-handling/README_ko.md)은 실제 NetCDF backend O0/O2, 수정 전 경계 오류, Python 15개 namelist 및 기존 4개 프로세스 정리 시험을 연결한다.

기존 [runtime terminal](../main-runtime-io-integration-terminal/README_ko.md)은 실행 head `dd7eb1d`의 build/install·13h control·12→13h restart와 660개 ZZ 값·228/231 history 배열 일치를 보존한다. `START_DATE` 차이와 `multi_perturb=0` 범위도 유지한다. 새 P2 시험은 전체 WRF/MPI/restart 재실행이 아니다.

[NOAA 원자료](../nc-noaa-primary-contract/README_ko.md)는 내부 체적 단위 근거와 미확정 host 저장·population 규약을 분리한다. 권위 규약 없이 밀도·CF 배율을 추가하거나 Registry 단위를 바꾸지 않는다. RFMIP strict 21개 실패와 LBLRTM 음의 OD를 CI PASS로 닫지 않는다.

[추가 누락 감사](../helper-error-audit/README_ko.md)는 인덱스 LHS·여러 값/연속 RHS의 조용한 편집을 거부한다. 직접 unit 22개와 실제 4/4·37/37 namelist 전체 바이트의 부모 대비 동일성을 확인했다. 원래 15개 시험도 production 함수를 직접 호출했고 이번 누락 사례가 없었던 것이다.

NetCDF 세 항목은 상속 문제이며 PR149 회귀나 실제 예보 실패로 분류하지 않는다. [후속 actual-backend 시험](../netcdf-preflight-contract/README_ko.md)은 긴 문자열·getter·invalid write와 복구를 O0/O2에서 검사했다. 선택한 wrapper 본문은 실행했지만 전체 module_io/MPI runtime은 실행하지 않았다. 기존 proof package와 물리 승인 FAIL/OPEN은 보존한다.
