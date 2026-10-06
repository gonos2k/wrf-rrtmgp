# UDM27–RRTMGP37 해소 체크리스트

`checklist.json`은 현재 작업 12개와 기존 검토의 원래 19개 항목을
함께 보존한다. 항목별 상태·담당·종료 조건·판정 범위를 기록한다.
원래 항목의 PR 번호와 상태는 과거 기록이며, 현재 원격 상태가 아니다.
스냅샷 기준은 main `a29be085b34975c52bc97f6567b328a9a790d900`이다.

| 순서 | 작업 | 현재 판정 |
|---|---|---|
| 1 | 첫 호출의 native snow 반경과 양의 눈 광학 | PR #127 반영, 로컬 제한 범위 통과; 전체 CI 진행 중 |
| 2 | Nc·ice-fit·activation evidence 소스 핀 분리 | PR #128 반영, 해당 CI 5개 통과 |
| 3 | Nc 생성·수송 단위와 PSD/LUT 크기 정의 | 진행 중, 임의 밀도·반경 배율 적용 금지 |
| 4 | RFMIP strict 및 LBLRTM reference 수용성 | FAIL 유지, 허용오차 완화·음의 OD clipping 금지 |
| 5 | 최신 main의 CMake build/install/export/consumer | 통합 공백 검토 중 |
| 6 | 최신 정책의 장시간 예보·관측 검증 | 과거 48시간 근거 보존, 최신 정책 재검증 필요 |
| 7 | 실행·계수·입력·정책을 묶는 최종 identity | 이 목록은 자료 연결 단계, 전체 실행 manifest는 미완료 |

`PASS_SCOPED`는 명시된 구현·자료·실행 범위의 통과다.
기록의 hash가 맞거나 일반 CI가 성공했다는 이유로 물리 정확도 또는
운영 승인으로 승격하지 않는다. UDM의 기본 mode 0과 실험 mode 1도
구분한다. 첫-call 수정의 208개 배열 비교는 보존된 프로젝트 RRTMG4
기준이며, 모든 입력에 대한 pristine WRF 보존 주장이 아니다.

Nc에서는 generic `make_DropletNumber/rho` 초기화가 UDM에 적용되지
않는다. 기존 entry-density의 708개 동일 호출 표본도 이미 존재한다.
추가로 확인할 것은 실제 Nc producer/population의 단위 계보다.
RRTMGP는 Nc 자체가 아니라 UDM이 진단한 반경을 소비한다.

다음 명령은 다른 작업 디렉터리에서도 실행할 수 있다.

```sh
python3 /path/to/repo/validation/rrtmgp37/acceptance/verify.py --output /tmp/acceptance-index.json
python3 /path/to/repo/validation/rrtmgp37/acceptance/test_verify.py
```

검사기는 7개 연결 자료의 바이트·원래 gate 목록·상태 형식·종료 조건을
검사하고, startup에서 실제 시험한 5개 runtime source의 hash를 현재
파일과 비교한다. 원본 evidence의 내부 payload 전체나 과학 계산을
새로 검증하지 않는다. Runtime source가 바뀌면 기존 증거를 새 소스에
재표기하지 않고 `startup_source_subset_matches=false`로
기록한다. 다른 소스까지 모두 검증됐다는 뜻도 아니다.

`--require-production-acceptance`는 현재 반드시 RC=2와
`NOT_ACCEPTED`를 반환한다. RC=0의 일반 index 검증과 구분한다.
V1의 승인 boolean을 바꾸어 PASS를 만드는 방식은 검사기가 거부한다.
새로운 물리 승인에는 별도의 검토된 decision/schema와 완전한 실행
identity가 필요하다. 기존 FAIL 기록과 historical producer pin은 유지한다.
