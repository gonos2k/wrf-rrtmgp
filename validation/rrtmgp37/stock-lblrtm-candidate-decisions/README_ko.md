# LBLRTM candidate 결정 경로 — 저장 증거

같은 held-state SAMPLE4 입력에서 관측용 candidate-decision hook을 추가한 private LBLRTM 진단을 한 번 incremental build하고 한 번 실행했다. 실제 build PID1750313과 solver PID1752919는 각각 RC0이었다. 변경된 object는 oprop 하나다. 실제 solver는 source-instrumented LBLRTM이며 unmodified stock 실행으로 세지 않는다. 이 패키지는 **진단 경로와 비간섭의 증거**이며 production source 수정이나 음수 광학두께의 물리적 수용 판정이 아니다.

## 실제 저장 결과와 제한

reader-v2는 PID1781213, 실제 RC0으로 종료했다. 기록된 candidate events는25,630개, target R3 term join은6,072개/837 full identity이다. 기존 R3/PANEL trace 해시는 같았으며45개 층의63,838,065개 spectrum sample과 panel payload를 exact 비교했다. OD 파일 header는 HTIME word168만 해당 run의 TAPE6 clock과 연결해 예외로 허용했다. 전체 OD 파일 byte identity를 주장하지 않는다.

Identity는 `(RDLIN pass,block,slot,LNCOR batch)`이다. Reason9는 corrected strength가 계산된 지점이며 이후 SPEAK/FREJ 필터를 모두 통과했다는 뜻이 아니다. Phase3는 실제 CNVFNV 진입을, reason11은 다음 panel로의 handoff를 기록한다. Reason11을 line drop으로 해석하지 않는다.

선택 VFT에 들어오기 전에 계산된 상태가 PANEL→label70 경로로 이어질 수 있다. Reader-v2는 같은 pass의 최초 관측 phase2 batch보다 **엄격히 이전인**69개 nonzero prefix entry를 left-censored로 분리했다. 이69개의 관측되지 않은 SP/SUI ancestry는 검증되지 않았다. 이후 누락은 실패 처리하며, prior reason9를 관측한4,155개 nonzero entry의 operand는 bitwise 검사했다. 이 routing 기록은 없어야 할/있어야 할 물리적 cancellation partner를 증명하지 않는다.

## 원문 보고서의 counter 정정

`reader/v2/report.json.gz`는 실행 원문을 lossless 압축한 것이다. 그 안의 `join.computed_reason9_invocations=7500`은 유효한 집계가 아니다. Missing-prefix lookup이 defaultdict에 빈 key69개를 추가한 결과다. `reporting-correction.json`은 원문을 바꾸지 않고 이 필드를 무효화한다. 직접 기록된 phase2 reason9 **event 행 수는7,431개**이며, 이를 unique invocation 수로 승격하지 않는다.

Prospective reader-v3는 lookup을 `computed.get`으로 바꾼 미실행 source-only 후속이다. 실행된 reader-v2 또는 원문 report를 v3로 바꾸어 표시하지 않는다.

## 실패와 준비 이력

Source-v1의 encoded MOL/isotope 진단 식 문제, v2의 identity 정정, v3의 reason9 해석 정정을 보존했다. V2/v3의 source/patch bytes는 같아 patch는 한 번 저장하고 두 origin을 기록했다. Full Fortran snapshot과 실행파일/object는 배포하지 않는다.

Runner-v3부터v6까지는 **실행 전** source/schema/pin 검토 결함이다. 이들을 실패한 solver invocation으로 세지 않는다. 실제 build/solver는 수정된 runner-v7을 사용했다. `runtime/reviews/preparation-v3.json`의 파일명은 준비 버전을 가리키지만 원문 schema/status는 실제 build/solver 종료 후 작성된 terminal metadata review다. 이를 실행 전 검토로 해석하지 않는다. Reader-v1은 PID1754901, RC1로 너무 강한 ancestry 조건에서 실패했다. 이 실패/claim/제한된 context를 보존했고 solver를 다시 실행하지 않았다. Reader-v2의 RC0와 별도 report-counter 결함도 그대로 구분한다.

## 파일과 검증 범위

Manifest는 이 패키지의 정확한 closed roster와 저장 해시를 기록한다. Gzip 파일은 원본과 inflated SHA/길이를 연결하고, 원문 patch/log의 공백을 자르거나 정규화하지 않았다. `origins.json`은 복사한 원문 pin과 authored 파일을 분리한다. 기존 PR117의 [R3 accounting report](../stock-lblrtm-r3-terms/r3-accounting-report-v2.json)와 [AER notice](../stock-lblrtm-r3-terms/LICENSE_AER.md)를 참조한다.

```sh
python3 -I -S validation/rrtmgp37/stock-lblrtm-candidate-decisions/verify.py --output build/candidate-archive-verification.json
```

이 verifier는 저장·inflated 해시와 **own-authored 메타데이터의 관계**만 확인한다. 원본 linebank, TAPE3,22MB events,15MB R3 trace, PANEL/OD binaries, 계수 벡터 또는 실행파일을 다시 열지 않는다. 패키지의 runner/reader는 당시 실행된 source archive이며 로컬 절대경로와 제외된 외부 자료를 필요로 한다. 공개 패키지에서 numerical reproduction을 직접 실행할 수 있다는 뜻이 아니다. Signed/root authorization 문서와 다운로드 URL은 배포하지 않는다.

기존 음수 OD의 physical FAIL, 원본 spectroscopy coefficient의 정확성 및 WRF4↔37 잔차는 계속 OPEN이다. 이 evidence 제출로 정상 판정이나 물리 목표 완료를 선언하지 않는다.
