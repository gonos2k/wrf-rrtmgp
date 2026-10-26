# Cloud-off 입력 수정과 자동 검증

`icloud=0`은 LW/SW 복사에 전달하는 모든 수상체를 제외한다. QC/QR/QI/QS에 더해 QG를 기둥마다 0으로 초기화하고, hail도 0을 전달한다. 실험 frozen1의 uniform G/H와 diagnosed CU population 역시 제외한다. 기체 입력과 원래 미세물리·대류 상태 배열은 유지한다. 선택한 정책의 초기 설정·입력 계약 검사는 계속 적용한다.

`icloud/=0`의 기존 수상체 포장과 frozen1 정의는 유지한다. frozen0에서 양의 hail 입력을 거부하는 기존 규칙도 유지한다. 이 수정은 기본 정책·계수·관측 점수를 조정하는 변경이 아니다.

## 확인 방법

`WRF/test/rrtmgp/test_cloud_off_inputs.py`는 실제 LW/SW 소스의 초기화·수상체 포장·hail 선택 블록을 추출해, 실제 `module_ra_rrtmgp_input.F`와 함께 컴파일한다. QG를 NaN으로 오염시킨 첫 사용과 cloudy→clear 기둥 재사용, frozen0/1, CU 선택을 O0/O2에서 확인한다. 초기화 누락·무조건 hail 읽기·무조건 CU 사용의 반례는 거부한다. CTest의 `cloud_off_wrapper_inputs`에 연결한다. 전체 WRF 예보나 RTE 적분을 대신하는 시험은 아니다.

Acceptance workflow는 PR과 main push 모두에서 루트 README, `docs/porting/**`, `sterling-transport-state/**` 변경을 감지한다. 기존 acceptance suite가 수송 재생과 회귀시험을 실행하고, 별도 step은 `review_math.py`의 결과를 저장 JSON과 바이트 단위로 비교한다.

## 과거 실행 근거의 범위

PR #209까지의 cloudy 실자료 실행·수송 결과는 그대로 보존한다. `historical-source/snapshot-789188e2.json`은 수정 전 두 wrapper와 registration의 원 바이트를 압축·원문 해시 및 크기로 고정한다. 영향받는 저장 검증기는 이 세 파일만 명시적인 과거 소스로 읽고, 분석 코드·검증 코드·나머지 의존성은 현재 파일로 검사한다. 수정된 검증 코드와 의존성의 식별값만 갱신하며, 기존 수치 결과·CSV·원 실험 archive는 바꾸지 않는다.

저장 결과 안의 당시 `current_runtime_source_matches=true`는 당시 snapshot에서의 판정이다. 현재 재생의 출력은 `source_scope=historical_PR209_snapshot`, `current_runtime_source_matches=false`로 표시한다. 과거 실행을 수정 후 코드의 새 실행으로 집계하지 않는다. 이번 수정 경로의 근거는 위의 컴파일·실행 회귀와 현재 소스의 빌드 검사다.

고정 직렬 연구 구성의 공학적 완료와, Sterling 오후 구름·일사의 정량적 적용성 미승인이라는 기존 판정은 유지한다. 새로운 24시간·WPS·REAL·Mie 캠페인은 필요하지 않다.
