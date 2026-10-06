# LBLRTM 음수 광학두께: 선택된 CO₂ 결합 기록의 변환 검사

기준일: 2026-10-06. UDM27–RRTMGP37의 독립 복사 기준 검증에 사용하려던 LBLRTM 출력에서 음수 광학두께가 발생했다. 이 묶음은 **그 원인을 WRF 포팅 오류로 잘못 돌리지 않도록**, 앞선 R3 항별 추적에서 큰 음수 항을 만든 CO₂ 선 3개의 데이터 전달 경로를 검사한다.

**결과: 한 번 실행한 저장자료 검사기가 실제 종료코드 0으로 끝났고, 선택된 3개 기록의 원본→TAPE3 전달 및 `YI/GI/SPPSP` 재구성이 정확히 일치했다. 그러나 독립 기준의 음수 광학두께 검증 실패는 해소되지 않았다.**

## 실행과 확인 범위

| 항목 | 이번 근거 |
|---|---|
| 실행 | 독립 소스 검토 후 stdlib Python 검사기를 정확히 한 번 실행. `executed-v2/execution.json`의 actual child RC=0, timeout=false |
| 대상 | 저장된 layer 21, CO₂ molecule 2 / isotope 1 / flag 1, trace I=32·60·99 |
| 입력 | 고정 AER v3.8.1 파일 908,403,720 bytes와 생성 완료된 TAPE3 122,157,832 bytes를 각각 한 번 읽어 해시 확인 |
| 원본 기록 | 각 대상의 유일한 main과 뒤따르는 한 foreign companion을 확인. 원본 전체를 다시 생성하지 않음 |
| TAPE3 | 3,129개 block framing 확인. 선택 기록은 모두 block 487의 slot 32·60·99; 각 인접 companion은 33·61·100 |
| 필드 | main의 9개 지정 필드와 companion의 8개 REAL4 표현이 정확히 일치 |
| 재구성 | 압력 이동 선 중심, YI, GI, SPPSP가 저장 실행 기록과 정확한 binary64 일치. 아래 세 대상에서 0 ULP |
| 새 모델·계수 생성 | WRF / RTE / LNFL / LBLRTM / compiler 실행 모두 0 |

| Trace I | 이동된 선 중심 cm⁻¹ | YI | GI | SPPSP |
|---:|---:|---:|---:|---:|
| 32 | 667.385965634841 | 3.034229991142273 | 0 | 1.0431859088670232 |
| 60 | 667.4004316856123 | 0.6961040106391907 | 0 | 0.23932460529508187 |
| 99 | 667.423203639405 | 0.2003582988820076 | 0 | 0.06888434783402594 |

실행 결과는 [record-audit.json](executed-v2/record-audit.json), 종료 근거는 [execution.json](executed-v2/execution.json), 입력·출력 해시는 [postflight.json](executed-v2/postflight.json)에 보존한다. 종료코드가 저장된 뒤 결과를 읽었다.

## 검사한 전달 계약

실제 LNFL 제어의 blank HOLIND는 F100 reader를 선택한다. 개별 기록은 CR/LF 종료문자를 제외한 본문을 해시하고, 첫 100문자만 source의 READ920/925 형식으로 파싱한다. 파일 전체 스트림 해시에는 종료문자도 포함한다. 과거 plan-v6의 모든 기록이 160문자라는 설명은 이 실행의 형식 근거로 사용하지 않았다.

companion은 다음과 같이 해석한다.

`A = (VNU, ALFA, MOL 워드의 REAL4 재해석, TMPALF)`

`B = (SP, EPP, HWHMS, PSHIFT)`

원본 Y/G 필드는 LNFL의 REAL4 대입과 승격을 재현해 비교한다. main의 SP는 원본 STRSV를 그대로 비교하지 않고 LNFL의 RADCN2/BETA0 기본 REAL 상수·연산 및 최종 REAL4 대입을 재현한다. 압력 이동 선 중심과 200–250 K 구간의 보간은 고정 source의 연산 순서를 따른다.

`SPPI/SPPSP` 재구성에는 **실제 trace의 SUI와 압력비**를 사용했다. 따라서 원본 SP의 전달은 검사했지만, SUI를 만드는 전체 분배함수·온도 보정 경로를 독립 재검증한 것은 아니다. 0 ULP는 지정된 양의 값과 저장된 0의 재현 계약이며 일반 IEEE 부호 영역 전체의 ULP 검증을 주장하지 않는다.

## 남은 원인과 기준자료 범위

앞선 PR117은 실제 기록된 R3 쓰기를 항별로 추적했다. 이번 결과는 **선택된 세 CO₂ 선의 잘못된 slot 대응·REAL4 변환·계수 전달**을 원인으로 지목할 근거를 줄인다. 전체 선 데이터, 원래 분광계수의 물리적 타당성, 모든 음수 OD, WRF의 4↔37 플럭스 차이는 이 검사로 판정하지 않는다.

[finite-support 검토 v2](source-followup/finite-support-review-v2.json)는 실제 항별 쓰기 추적이 이미 존재함을 반영한다. 기록되지 않은 LNCOR1 사전 탈락 후보나 상쇄할 선이 있었는지는 현재 trace만으로 확정할 수 없다. 다음 조사는 기존 TAPE3 후보 범위와 source의 탈락 조건을 연결하는 것이며, 이미 완료한 PANEL·항별 계측을 다시 하는 것이 아니다. v1의 오래된 제안은 변경하지 않고 함께 보존한다.

[공식 v12.17 예제 묶음 조사](official-examples/archive-review.json)는 실제 `_ex` 회귀 출력이 있음을 확인했다. 다만 검사한 묶음에서 **작은 OD-only 기준과 완전한 compiler·외부 line-data 신원**은 확정하지 못했다. 예제 출력이 없다는 뜻도, 현재 음수 OD를 허용한다는 뜻도 아니다. 이 조사에서는 archive 내용을 실행하거나 외부 symlink를 따라가지 않았다.

## 보존·재현·자료 취급

- `preparation-v2/`의 plan과 README는 실행 전 상태의 고정 원문이다. 현재 실행 사실은 `executed-v2/`와 본 보고서가 설명한다.
- `unexecuted-draft-v1/`는 잘못된 mapping으로 거부된 **미실행 초안**이다. 실행 지침이나 과학적 실패 결과로 사용하지 않는다. [거부 근거](reviews/blocked-draft-v1.json)를 보존한다.
- 실행 wrapper는 새 출력 디렉터리, 입력·reader·review 핀, 120초 process-group timeout, 종료코드 우선 저장으로 한 번의 실행을 제한했다.
- 실행 script와 plan은 보존된 private workspace의 절대 경로를 사용한다. 공개 묶음만으로 바로 재실행할 수 있는 portable dataset을 제공하지 않는다.
- 원본 AER 행, TAPE3 바이트, 전체 coefficient vector, archive, 실행파일, 임시 서명 다운로드 URL은 포함하지 않는다. 보고서는 기록 해시·위치·필드 일치 여부·유도 scalar만 포함한다.

상위 WRF 물리 코드와 CI workflow는 변경하지 않는다. `PASS_SCOPED_RECORD_AND_COEFFICIENT_PATH`는 전달·산술 범위의 통과이며, 독립 복사 기준의 물리적 승인이나 UDM 예보 정확성 완료가 아니다.
