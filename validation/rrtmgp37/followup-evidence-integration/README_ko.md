# 후속 검토 증거의 main 기반 통합

이 변경은 PR #138/#140과 #139/#141/#143/#144의 보존 증거를 `a91d0d855da3e24094c2e6c7ba1088b56bc8c461` main 기반 후보에 연결한다. Runtime/I/O 통합 [PR #146](https://github.com/gonos2k/wrf-rrtmgp/pull/146)과 독립된 main 기반 PR이다. 두 후보 모두 병합 전에는 main 반영으로 표시하지 않는다.

| 체크리스트 ID | 통합 내용 | 종료조건 |
|---|---|---|
| EVD-RFMIP | #138 fixed RTE → #140 historical/current runtime×optics | 두 원본 package와 외부 test harness 해시 보존, saved verifier와 선행 manifest 연결 |
| EVD-NC | #139 QNN → #141 양의 Nc → #143 activation → #144 부분구름 | 네 원본 package와 producer/helper 시점 join 보존, saved verifier와 부분구름 부정시험 |

생산 Fortran, CMake/Registry 설정, 기존 acceptance 19개 gate/12개 항목은 변경하지 않는다. `WRF/test/rrtmgp/rrtmgp_rfmip_sw_fixed_rte.F90`는 원본 fixed-RTE manifest가 요구하는 시험용 harness이다. 역사적 source, package manifest, 선택 packet/stream, 실행 receipt는 원래 바이트를 유지한다. 보존 source의 공백도 변경하지 않는다.

현재 통합 검사의 실행 정보와 파일 해시는 [manifest](manifest.json), 원래 package 의존성은 [dependency inventory](dependency-inventory.json), 항목별 상태는 [checklist addendum](checklist-addendum.json)에 기록한다. 새 통합 검사는 저장 자료 검증과 산술 재현이며, WRF/RTE/LBLRTM이나 compiler를 새로 실행한 것으로 집계하지 않는다. Historical RTE verifier가 analysis JSON을 재계산해 쓰는 동작은 원본과 동일하다. 새 workflow는 [격리 wrapper](verify_historical_isolated.py)를 통해 정확한 임시 복사본에서 이를 실행하고, 원본과 복사본 모두의 전후 바이트가 같은지 검사한다. 실패해도 원본 증거를 덮어쓰지 않는다.

물리 판정은 다음처럼 유지한다.

- Published RFMIP strict는 21개 실패(13 RSD + 8 RSU), `atol=1e-5`, `rtol=0`를 보존한다. 20-profile 2×2 분해의 작은 차이는 strict PASS가 아니다.
- Nc 양성 자료와 실제 activation/부분구름 자료는 소스 동작을 관측한다. Activation 자료의 cap=1과 CCN floor, 서로 다른 helper 시점을 분리한다. Nc 단위·기준질량·population·PSD 모멘트의 물리적 승인은 OPEN이다.
- 외부 전체 history/restart와 실행파일은 원래 비교 receipt의 해시·schema 기록으로 연결한다. 이 작은 package 검사가 해당 대형 파일을 다시 열어 검사한 것은 아니다.
- LBLRTM negative OD, pinned LUT 크기 정의, 최신 통합 tree 장시간 예보·관측 승인은 별도 항목으로 남는다. `production_accepted=false`를 유지한다.

Runtime/I/O 체크리스트는 PR #146의 `validation/rrtmgp37/acceptance/REVIEW_RESOLUTION_ko.md`에 있으며, 이 addendum은 EVD 두 항목만 갱신한다. 구현, 분기 검증, main 포함, 통합 검증을 하나의 PASS로 합치지 않는다.
