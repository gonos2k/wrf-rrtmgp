# 이전 검토 지적 해소 체크리스트

현재 기준 main: `32c13f2fd39d6846e35212f4f7bb53079fd6bd68`. UDM27–RRTMGP37 전용.

PR #146–#151은 main에 병합됐다. 기존 실행의 source pin·범위는 그대로 보존하며, 현재 전체 tree에서 모든 과거 모델을 새로 실행했다고 주장하지 않는다. PR #149의 NetCDF guard와 기본 namelist 검사는 main에 반영됐고 정확히 같은 tree에서 11개 CI가 성공했다. PR150의 추가 scalar 경계 수정도 main에 반영됐다. PR151의 I/O 세 항목도 main에 반영됐고 정확히 같은 전체 tree에서 11개 CI가 성공했다.

후속 해소 목록은 **main 기준 22개 중 15개 PASS_SCOPED, 7개 OPEN/FAIL/NOT_RUN**. 항목의 중요도·범위가 다르므로 완료율 백분율로 사용하지 않는다. 이것은 원래 acceptance의 **19개 gate + current 12개 항목**과 다른 작업 목록이다. [원래 index](checklist.json)는 변경하지 않았고 `production_accepted=false`를 유지한다.

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
| P2-IO-VARINFO | 변수정보 wrapper 인자 수 | 반영 | PASS_SCOPED |
| P2-IO-LENGTH | Memory-order 길이·padding | 반영 | PASS_SCOPED |
| P2-IO-WRITE-SIDE-EFFECT | Invalid write의 시간 기록 | 반영 | PASS_SCOPED |

[기계 판독 목록](review-resolution-checklist.json)은 항목별 종료조건·실행 범위·근거를 제공한다. [새 P2 검증](../helper-error-handling/README_ko.md)은 실제 NetCDF backend O0/O2, 수정 전 경계 오류, Python 15개 namelist 및 기존 4개 프로세스 정리 시험을 연결한다.

기존 [runtime terminal](../main-runtime-io-integration-terminal/README_ko.md)은 실행 head `dd7eb1d`의 build/install·13h control·12→13h restart와 660개 ZZ 값·228/231 history 배열 일치를 보존한다. `START_DATE` 차이와 `multi_perturb=0` 범위도 유지한다. 새 P2 시험은 전체 WRF/MPI/restart 재실행이 아니다.

[NOAA 원자료](../nc-noaa-primary-contract/README_ko.md)는 내부 체적 단위 근거와 미확정 host 저장·population 규약을 분리한다. 권위 규약 없이 밀도·CF 배율을 추가하거나 Registry 단위를 바꾸지 않는다. RFMIP strict 21개 실패와 LBLRTM 음의 OD를 CI PASS로 닫지 않는다.

[추가 누락 감사](../helper-error-audit/README_ko.md)는 인덱스 LHS·여러 값/연속 RHS의 조용한 편집을 거부한다. 직접 unit 22개와 실제 4/4·37/37 namelist 전체 바이트의 부모 대비 동일성을 확인했다. 원래 15개 시험도 production 함수를 직접 호출했고 이번 누락 사례가 없었던 것이다.

NetCDF 세 항목은 상속 문제이며 PR149 회귀나 실제 예보 실패로 분류하지 않는다. [후속 actual-backend 시험](../netcdf-preflight-contract/README_ko.md)은 긴 문자열·getter·invalid write와 복구를 O0/O2에서 검사했다. 선택한 wrapper 본문은 실행했지만 전체 module_io/MPI runtime은 실행하지 않았다. 기존 proof package와 물리 승인 FAIL/OPEN은 보존한다.

[PR151 병합·terminal 상태](../netcdf-scalar-terminal/README_ko.md)는 head/main 전체 tree 동일성과 원격 Make/CMake 11개 성공을 연결한다. 이전 실행 기록·source pin은 수정하지 않는다. 같은 backend의 스칼라 order `0` 두 시각 회귀는 별도 로컬 실행으로 관리하며 생산 물리 변경이나 최종 물리 승인에 합산하지 않는다.

[PR152 자체 감사·정정](../netcdf-scalar-audit/README_ko.md)은 최종 검토 영수증의 잘못 연결된 체크리스트 hash를 새 정정 영수증으로 분리한다. 원래 sealed 기록은 변경하지 않았으며 완료15/미완료7의 내용은 동일하다. 독립 reader의 총수만 검사하던 약점은 실제 replacement 반례로 확인했고, 정확한 파일 roster 검사와 CI 독립 판독을 추가했다.

[PR152 최종 CI 및 현재 UDM 부분 활성화 관측](../partial-activation-observation/README_ko.md)은 병합된 head의 11개 terminal SUCCESS와 같은 전체 tree를 연결한다. 새 직접 UDM fixture는 두 EOS 일관 밀도, 선행 부분 CF, 엄밀한 부분 activation 및 선택 과정 cap/floor 비활성을 관측한다. CF로 나눈 질량은 activation 전에 grid mean으로 복원됨을 구분한다. 생산 source·수농도 변환식은 바꾸지 않았으며 host input/storage/transport·단위·PSD/LUT 계약은 여전히 OPEN이다. 완료15/잔여7 및 원래19/current12는 그대로 유지한다.

[PR153 terminal 및 실제 Thompson–UDM 액체 반경 커널 대조](../udm-thompson-cloud-radius/README_ko.md)는
PR153의 main 통합과 11개 terminal SUCCESS를 별도로 연결한다. 새 O0/O2 시험은
Thompson의 private cloud 상태만 준비하며 `thompson_init`·WRF 8/28 routing은 실행하지 않는다.
질량당 입력→체적 수농도→gamma 모멘트 경계, 고정 체적 수농도와 UDM 원시 수농도의
조건부 반응을 구분한다. actual helper 72회는 기상 사례 수가 아니며 물리 gate를 닫지 않는다.
Thompson37 운영 지원·광학/예보 우열은 주장하지 않는다. 기존 sealed source pin은 유지한다.

[PR154 terminal 및 host scalar 수송 절차](../host-number-transport/README_ko.md)는
PR154 main 통합과 11개 terminal SUCCESS를 연결한다. 신규 O0/O2 fixture는
실제 네 절차를 원문 추출해 최소 adapter로 호출하며 셀별 flux·건조질량/면적
보존·QNN boundary 직접 주입을 검사한다. 전체 모듈/WRF host/UDM routing은 아니다.
초기화→수송→UDM 입구의 의도된 단위·population은 여전히 OPEN이며
15개 완료/7개 잔여와 원래19/current12, production_accepted=false를 유지한다.

[PR155 terminal 및 실제 연결된 host 실행](../connected-host-number/README_ko.md)은
PR155의 main 반영과 11개 terminal SUCCESS를 연결한다. 새 가역 관측 snapshot의
전체 WRF GNU13/REAL32/serial/allocatable SCM에서 비균일 입력, QNN=0 입력,
양의 구름 입력, 실제 비균일 checkpoint restart를 실행했다. 입력→start_em→실제
Registry QNN/QNC RK1–3→첫 driver 상수 reset→UDM entry→native helper→반환을
같은 셀·층·step에서 연결하고 청천/구름 OFF/ON history 전체 bytes를 검사했다.
첫 driver는 외부 QNN을 상수로 바꾸며 restart에는 해당 reset이 실행되지 않는다.
이것은 현 정책의 관측이지 외부 QNN 보존을 승인하거나 단위를 결정한 수정이 아니다.
real.exe, 실제 specified lateral boundary, 다른 수송 정책, 입자크기 물리 승인과
최종 예보 정확도는 포함하지 않는다. 완료15/잔여7과 production_accepted=false 유지.

[Cold-start 세 number 입력 보강](../cold-number-input-contract/README_ko.md)은 PR156의
기존 정책을 유지하면서 파일→START_PRE QNN/QNC/QNR 비트 대조와 START/reset
직전·직후 QNC/QNR 보존을 자동 강제한다. 양의 제조 QNR sentinel, 7개 오류 반례,
기존 실행파일을 재사용한 7개 모델 자식 및 OFF/ON 동일성을 보존한다.
초기화 정책 결정과 단위 계약은 여전히 OPEN이며 완료15/잔여7을 변경하지 않는다.
