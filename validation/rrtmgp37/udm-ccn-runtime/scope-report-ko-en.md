# 검증 범위 / Scope

이번 January2000 UDM27,MPI4,2타일,GNU13.3 사례에서 새3시간 RA37 OMP1/2 및 관찰기 사용/미사용 결과는225개 history 변수와664개 checkpoint 변수,metadata,전체 파일까지 같습니다. 네 MPI PID 각각에서 실제 두 radiation callback worker의 활동을 확인했습니다. 새24시간 OMP2 history는 이전1타일 결과와 전체 파일이 같고 모든 수치 history/checkpoint 검사는 유한값·마스크·기본 fill 검사를 통과했습니다. RA4 같은 스레드 수의 기존 결과와 기존 CCN 시작 결함은 보존됩니다.

Restart는 상태 범위로 승인되었습니다.15시 초기 history는222/225 동일하고 세 UDM history-only 진단값은 실제 초기화에 따라−1로 재설정됩니다.16시에는225/225 history 및664/664 최종 checkpoint raw 변수가 같습니다. 두 restart OMP 구성끼리는 전체 파일까지 같습니다. 연속/재시작 metadata의 차이는 START_DATE,history Time 길이,비활성 alarm55뿐입니다. 원본 엄격 comparison의 FAIL은 그대로 보존되며 전체 파일 재시작 동등성으로 표현하지 않습니다.

후보8개와 변경 전9개 모델 실행 모두 엄격한 수치 출력 검사를 통과했습니다. 기존4개 참조 실행까지 포함한 root의 범위 합계는21입니다. 과거 OMP raw 차이와 staging/self-test/build harness 실패는 보존했습니다. QNCCN의 `# kg(-1)`는 출력 라벨입니다. 두 변경의 효과를 각각 분리한 검증,일반 OMP/중첩/분할 불변성,물리적 예측 정확도를 주장하지 않습니다.

The combined startup/predicate repair passes scoped three-hour thread and observer noninterference comparisons,24h finite checks and historical history preservation. Own-restart state is accepted with initial diagnostic resets and a disabled timer attribution; the original strict FAIL remains unchanged. Final history225/225 and checkpoint664/664 raw fields match continuous integration. Restart OMP1/2 whole files match; continuous/restart whole-file parity is not claimed.

The package pins PR49 head199d0d9 (observation-only update) and runtime-tested head4673f9d. Latest CI37139840807 was pending at preparation; previous head passed all eight checks. The portable standard-library verifier checks retained text/hash-ledger relationships, not absent external arrays. No new model,build or reference calls were made by this curation.
