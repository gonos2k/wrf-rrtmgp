# LBLRTM 한 파수의 R3 최초 음수 전환

PR159의 최소 대상 계획을 실제 실행으로 진행했다. 생산 WRF/UDM/RTE 코드·계수·초기화 정책은 변경하지 않았다. 대상은 기존 held-state의 layer21, 약 `618.6144711111115 cm⁻¹`이다. R3의 정의된 누적값에서 최초 음수로 바뀌는 국소 경로를 관측했으며, **LBLRTM 물리 reference 승인은 여전히 FAIL**이다.

## 실제로 확인한 경로

| 경계 | 관측 결과 |
|---|---|
| Panel 이동 후 tail clear | 실제 `MAX3=283`; 새로운 R3(170)이 0으로 정의됨 |
| 최초 음수 전환 | CNVFNV coupling phase2, line centre 약 618.0235026348411 cm⁻¹ |
| 전환 전·후 | `2.6505117157309957e-4 → -2.945352328401023e-5` |
| 같은 파수의 다음 panel | R3(170)의 값이 R3(20)으로 정확히 carry됨 |
| 다음 continuum 기여 | `-2.5643980319365688e-5 + 8.775708875840199e-6` |
| PANEL 직전 최종값 | `-1.686827144352549e-5`, 과거 선택 상태와 정확히 일치 |

실제 좌표 `VFT + (index-1)*DVR3`로 대상을 연결했다. Runtime panel 번호가 우연히 과거 `owner_header=14`와 같다는 사실을 식별 근거로 쓰지 않는다. 초기화부터 최초 음수까지 713개 mutation 기록이 연결되고, 전체 선택 CNVFNV mutation 1,976개를 기록된 binary64 연산 순서로 비트 재생했다. 이 수치는 독립 기상 사례 수가 아니다.

첫 음수까지 선택 accumulator에 미확정 XINT source-write는 없었다. Layer21 시작에서 `ILBLF4=0`이고, 해당 HIRAC1 소스 경로에서 이 값이 바뀌지 않는다. 모든 관측 RSYM gate는 비활성이며 VFT도 양수다. R3 목적지의 세 XINT 호출 경로에는 공개 XINT와 같은 산술을 가진 별도 관측 사본을 연결했다. 다른 호출자와 공개 XINT ABI는 그대로다.

**닫힌 것은 선택 accumulator의 clear→mutation→최초 음수 경로다.** Line의 절대 파일 record ID·분자/동위원소 식별·coupling 계수 생성의 물리적 수용성까지 인증하지 않았다. Continuum의 전체 입력 stencil 생성 계보·R4가 활성인 다른 구성·모든 layer 및 파수의 ancestry도 완료하지 않았다. `all_operand_generation_ancestry_complete=false`, `full_LBLRTM_reference_accepted=false`를 유지한다.

## 실행과 불변성

기존 GNU13.3 double stock stage를 분리 복사했다. 새 module과 marker 관측 블록을 제거하고 관측 XINT 이름을 되돌리면 원래 OPROP bytes와 추가 separator newline 하나가 복원된다. 기존 산술을 바꾸지 않았다. 성공 빌드 뒤 다른 object 20개는 stock 및 이전 v10의 bytes와 동일하고 `oprop.o`만 다르다.

관측 실행파일의 OFF와 ON으로 같은 38개 입력의 전체 45-layer held-state를 각각 실행했다. 두 모델 자식 모두 RC0이었다. 원시 Fortran record marker를 확인해 45개 OD 파일의 **FILHDR 이후 panel 좌표·OD 기록 53,279개**를 판독했다. 모두 OFF/ON 및 이전 v10과 비트 단위로 같다. 새 source/candidate capture는 독립 spectroscopic truth가 아니다.

**전체 파일 bitwise 비교는 FAIL로 보존한다.** 첫 FILHDR의 source-mapped `YID(1)=HDATE`, `YID(2)=HTIME` 16바이트에서 실행 날짜·시각이 다르다. 그 외 FILHDR bytes도 모두 동일했다. [과학 기록 판독 결과](scientific-record-comparison.json)는 이 범위를 명시한다. Timestamp 제외 판독을 전체 파일 동일성으로 재명명하지 않는다.

[시도 기록](attempts.json)은 최초 관측 선언 위치 오류의 build FAIL, nested input directory 준비 실패, whole-file 비교 FAIL 및 reader의 잘못된 CN_PRE 기대를 보존한다. 최종 reader는 양의 continuum 이후 PANEL_PRE가 과거 상태의 비교 경계임을 확인했다. Reader 수정으로 모델을 재실행하지 않았다. 총 make 자식 2회(1회 실패), solver 자식 2회다. 기존 source와 큰 출력은 원래 위치에 보존했다.

## 보존 자료 검사

```bash
python3 -I -S validation/rrtmgp37/lbl-minimal-r3-transition/verify_saved.py
python3 -I -S validation/rrtmgp37/lbl-minimal-r3-transition/test_saved.py
```

CI는 포함된 source snapshot·trace·JSON bytes와 선택 mutation 연산을 검사한다. 원시 45개 OD·실행파일·TAPE3·coefficient를 다시 열거나 모델을 빌드하지 않는다. Manifest는 내부 정합성 기록이며 외부 서명이나 publisher 진위 보증이 아니다. Runtime scripts는 당시 root 실행 기록이고 one-use external build/data 경로를 전제로 하므로 CI 실행 명령이 아니다.

[PR159 terminal 연결](pr159-terminal-main.json)은 병합 main `d2226c6…`와 실제 정밀도 CI checkout `62dc33d…`의 tree `c86d36c…` 동일성을 기록한다. 3개 검사는 terminal SUCCESS다. 해당 정밀도 CI를 이번 LBLRTM 실행이나 새 전체 WRF 검증으로 합산하지 않는다.

소스·작은 JSON에 한정한 [별도 검토](source-review-v1.json)는 native 산술 보존을 확인했다. 원시 trace·OD·로그 판독이나 모델 실행은 수행하지 않았다. 지적한 두 저장 메타데이터 검사 공백은 패키지 봉인 전에 보완했으며 [처리 기록](source-review-disposition.json)에 분리했다. 선택 mutation 반례 네 개와 OD 판독 receipt의 모순 반례 두 개를 검사한다. 이 receipt 검사는 원시 OD 재판독을 대신하지 않는다.

## 다음 reference 경계

이 coupling 항은 signed intermediate contribution일 수 있다. 최초 음수 전환을 특정했다고 제거·clipping·선택 coupling OFF를 해법으로 채택하지 않는다. 다음은 해당 line의 강도·coupling 계수·선택/절단 범위와 필요한 양의 상쇄항을 원래 입력부터 연결하는 일이다. 저장된 전체 OD의 음수 문제 및 RFMIP strict FAIL21, 원래 acceptance19/current12, 완료15/물리·최종7과 `production_accepted=false`는 유지한다.
