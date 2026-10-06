# LBLRTM 초기·열 보정 line-strength ancestry 관측

이 패키지는 PR120의 candidate-v3 실행을 기준으로 관측 코드만 추가한 별도 실행의 작은 증거 모음입니다. 물리 정확성이나 production 변경을 승인하지 않습니다. 동일 입력 38개로 증분 빌드 1회와 계측 솔버 1회를 실행했고, 저장 자료 reader 2회의 종료코드는 순서대로 1, 0입니다. WRF·REAL·RRTMGP 실행은 없습니다.

원래 strict CAND 전체 바이트 비교는 **FAIL**이며 outer runner 종료코드 3을 보존합니다. 실제 solver child는 종료코드 0입니다. 첫 reader도 CNVFNV의 미정의 진단 필드를 만나 종료코드 1로 끝났습니다. 두 번째 reader의 범위 제한 비교는 이를 대체하지 않습니다.

| 관측 항목 | 저장 결과 |
|---|---|
| 새 prefilter ancestry 기록 | 72개: 좌측 검열 prefix 69개 + 큰 음의 R3 기여를 갖는 3개 |
| ancestry→선택된 CNVFNV 연결 | prefix 69개는 이전 VFT, 나머지 3개는 선택된 VFT |
| scalar operand 비교 | 303개, 차이 0: prefix 276개 + dominant 27개 |
| dominant 27개의 세부 구성 | phase3 연결 12개 + 같은 phase2 호출 15개 |
| 기존 CAND의 미정의 metadata 차이 | 14,379행의 25,070필드, 지정된 세 필드에만 한정 |
| 기존 R3/PANEL 진단 파일 | 전체 바이트 해시 동일 |
| OD 스펙트럼 | 45층 / 63,838,065개 표본 동일; 기존 HTIME 헤더 word168 예외만 적용 |
| 열 보정 식의 서술적 binary64 재평가 | 72개, SUI/SP/SPPSP 최대 잔차 0; compiler/libm 마지막 bit oracle는 아님 |

72개 기록의 loaded line strength, 열 보정 전후 SUI와 SP는 모두 유한·양수입니다. 세 CO2 기여 항은 SP가 양수여도 선택된 네 R3 grid에서 coupling 항이 음수입니다. 각 항의 8개 term 행은 **baseline 4개 + 음의 coupling 4개**이며, 8개 모두 음수라는 뜻이 아닙니다. 이 관측은 저장된 연산 경로를 연결할 뿐, 원래 계수 생성·물리 타당성이나 빠진 cancellation partner를 증명하지 않습니다. 음의 OD 물리 FAIL은 유지합니다.

두 번째 reader는 소스로 확인한 사용 불가 진단 필드만 별도로 취급합니다. LNCOR1 phase2에는 IPANEL/IDATA를 이름으로 공유하거나 할당하지 않고, CNVFNV phase3에는 KPANEL binding이 없습니다. 허용 예외는 phase2의 두 필드와 phase3의 한 필드뿐입니다. 그 밖의 CAND token과 예외 밖의 fixed-byte 영역은 같아야 합니다. prospective patch는 해당 진단 호출 12개의 인수를 `-1` sentinel로 바꾸는 제안이며 **컴파일·실행하지 않았습니다**. 이미 실행한 파일이 수정되었다고 주장하지 않습니다.

공개 요약은 이벤트 69+3개와 scalar-field 검사 303개를 구분합니다. 원문 private report의 `matched_event_count`와 `dominant_same_call_bit_checks`는 혼동을 주는 이름이므로, 원문을 고치지 않고 root/독립 label-correction을 같이 제공합니다. 전체 원문 보고서의 SHA와 크기는 요약·scope에 남깁니다. loaded 원래 strength 값, full ancestry operand 벡터, raw 이벤트·linebank·TAPE3·OD·실행파일은 포함하지 않습니다.

`primary-audit/`의 AER 원문 조사와 additive erratum은 함께 읽어야 합니다. SP/SPPI/SPPSP의 소스 위치는 **LNCOR1**이며, public release compatibility 표 자체가 실제 사용한 source/data/executable의 동일성을 증명하지 않습니다. 입력 strength는 이미 LNCOR에 들어온 상태이므로 원래 ASCII 계수의 독립 검증으로 해석하지 않습니다. 관측 patch의 AER 코드 문맥에 대한 기존 [AER notice](../stock-lblrtm-r3-terms/LICENSE_AER.md)도 그대로 적용합니다.

`python3 -I -S verify.py --output <패키지 밖 receipt.json>`은 stdlib만으로 닫힌 파일 목록, 저장·gzip 복원 해시, 원본 copy 핀, 부모 PR120 파일 참조와 공개 summary/실행 receipt 관계를 확인합니다. raw 출력이나 private source/library/input을 다시 열지 않으며 물리 연산·솔버·reader를 실행하지 않습니다. 따라서 외부 source/data/library 핀은 역사적 실행 attestation입니다.

동봉된 `runtime/run_once.py`와 `reader/executed-v5/`는 실제 실행된 **역사적 코드**입니다. 원래 private cwd·input·helper·authorization을 가리키므로 이 공개 위치에서 곧바로 재실행 가능한 runner라고 주장하지 않습니다. reader 파일명 v5는 출력 formatting의 additive successor이며 계획 schema V4와 기존 승인된 output 경로를 사용했다는 원문 기록을 보존합니다. 재배치 실행에는 별도의 경로·핀·실행 범위 검토가 필요합니다.
