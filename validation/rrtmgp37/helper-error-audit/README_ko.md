# PR149 이후 누락·실수 감사

기준 main은 `439bf0d626a89ab105093945e946e47d7cf80f94`이다. PR149의 실제 시험 head `1b879fc…`와 전체 tree `229f937…`가 같다. 원격 check 11개 모두 terminal SUCCESS를 직접 확인했다. [조회 원본](pr149-terminal.json)은 이 연결을 보존한다. 이 결과는 이번 Python 후보의 CI 결과가 아니다.

이번에 놓친 실제 편집 경계는 두 종류다. 인덱스 LHS `ra_lw_physics(1)=4`는 기존값을 둔 채 bare 키를 삽입했고, 여러 값 또는 다음 줄로 계속되는 RHS는 첫 값만 바꿨다. 해당 형식은 현재 SCM fixture에 없으므로 기존 SCM 수치가 잘못됐다는 증거는 없다. [원래 감사](audit.json)와 [기존 시험 설명 정정](test-coverage-erratum.json)을 함께 보존한다. 원래 15개 unit도 production 함수를 직접 호출했고, 이 사례의 coverage가 없었던 것이다.

후속 수정은 scalar 편집 계약 밖의 인덱스·반복값·여러 값·null slot·연속값을 명시적으로 거부한다. 일반 scalar, 같은 줄의 다른 assignment, 문자열·주석·CRLF는 유지한다. [현재 직접 unit 결과](current-test-receipt.json)는 22개 method이다. [전체 fixture 비교](fixture-compatibility.json)는 실제 `make_namelist`의 4/4 및 37/37 전체 출력 바이트가 부모와 같은지 확인한다. 두 입력 파일도 저장했다. 이것은 모델 실행 결과가 아니다.

독립 팀 감사에서 추가로 발견한 상속 NetCDF 항목은 다음과 같다.

- `module_io.F`의 NetCDF 변수정보 wrapper는 backend의 9개 dummy에 8개 actual을 전달한다. 내부 호출자는 찾지 못했으며 latent API 문제로 한정한다.
- `LowerCase/UpperCase`는 짧은 출력에 입력 길이만큼 substring을 쓴다. 긴 padded 문자열과 공개 API의 3자 truncation 정책은 기존 short-token 시험 밖이다.
- `FieldIO`는 invalid write의 order 검사보다 먼저 `GetTimeIndex`를 호출한다. 기존 fixture가 확인한 것은 invalid read의 버퍼 보존이다.

[NetCDF 감사](netcdf-inherited-review.json)는 세 항목 모두 소스 확인만으로 OPEN 처리한다. 새로운 실행·컴파일은 없고 PR149 신규 회귀로 분류하지 않는다. 이번 후보는 이 Fortran/API 문제를 수정하지 않는다. 기존 backend proof 20개 payload 및 historical source pin은 그대로 보존했다.

[후속 체크리스트](../acceptance/review-resolution-checklist.json)는 기존 19항목에 새 상속 P2 3개를 추가해 22항목으로 관리한다. 기존 12개의 제한된 완료 근거를 유지하며 미완료는 기존 물리·최종 7개와 새 P2 3개다. 기본 namelist 수정은 main에 있고 이번 추가 scalar 수정은 후보에 있다. 원래 acceptance의 original19/current12 내용과 `production_accepted=false`는 변경하지 않았다.

이번 검사는 Python·소스·메타데이터 및 PR149 terminal CI 조회다. 새 WRF build/forecast, MPI, RTE, LBLRTM 실행은 0이다. Nc·population·PSD/LUT, published RFMIP strict 21개 실패 및 LBLRTM negative OD, 최종 정책의 장시간 관측 승인을 닫지 않는다.
