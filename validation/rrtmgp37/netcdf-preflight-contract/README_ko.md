# NetCDF 입력 사전 검사 및 wrapper 계약

기준 main은 `457cde630bbeb41a24c09baa1f536c73622b615f` (PR150)이다. 이전 감사의 P2 세 항목을 수정한 후보다. 복사식·UDM 정책·계수는 변경하지 않는다.

`FieldIO`는 MemoryOrder, 지원 FieldType, 활성 차원의 양의 Length를 먼저 검사한다. 그 뒤에만 `GetTimeIndex`를 호출한다. 이는 이 세 입력 오류의 시간 기록 부작용을 막으며, 디스크 실패나 잘못된 handle/variable 등 모든 실패의 rollback을 보장하지 않는다. Scalar order 0의 빈 활성차원 검사는 그대로 허용한다.

MemoryOrder는 3자 표현을 유지한다. Direct helper는 trailing blank padding을 허용하고 leading blank는 기존처럼 거부한다. Public read/write는 기존 `TRIM(ADJUSTL(...))` 규약을 유지하지만 유효 토큰이 3자를 넘으면 prefix truncation 전에 거부한다. Case conversion과 reorder도 길이·토큰이 유효하지 않으면 짧은 출력에 쓰지 않는다. 변수정보 getter는 1–3바이트의 serialized attribute를 local 3자 버퍼로 읽고, caller 출력이 짧으면 명시적 길이 오류를 반환한다.

`wrf_get_var_info`의 공개 8인자 API는 유지한다. NetCDF 분기에 backend-only FieldType의 local sink를 추가해 실제 9인자 backend에 Status를 정확히 전달한다. 다른 backend의 대응 규약은 이번 NetCDF 전용 수정의 범위 밖이다.

## 실제 실행

[최종 실행](attempt-v3/result.json)은 원본 `wrf_io.F90` 전체와 `field_routines.F90`를 NetCDF-Fortran에 연결한 GNU 13.3 REAL32 serial 시험이다. `-O0/-O2`, bounds 검사 및 미초기화 정수 진단에서 모두 성공했다.

- 기존 20개 정상/5개 short-invalid helper, ordered ZZ 3×5·2 Time·타입 변환을 유지한다.
- Padded order, long suffix, direct/public 공백 규약, 짧은 출력 및 malformed attribute를 검사한다.
- 각 최적화에서 독립 파일 12개로 잘못된 order·type·0/음수 Length를 거부한 뒤 같은 시각/다음 시각에 정상 write한다. 메모리 TimeIndex·Times와 파일 Time 길이·기존/새 field 값이 기대대로 보존된다.
- 선택한 실제 `wrf_get_var_info` 본문을 그대로 연결해 정상·missing-variable·short-output Status를 검사한다. State constants, serial handle/monitor/routing과 호출되면 실패하는 quilt trap만 fixture shim이다. 전체 module_io 또는 MPI runtime 시험은 아니다.

[별도 SciPy reader](independent-reader-result.json)가 최종 출력 32개를 대조했다. 24개 write-recovery 파일에는 두 정상 레코드만 있고, rejected 시각의 빈 중간 레코드가 없다. Normal ZZ 두 파일의 네 변수·차원·시각·값과 malformed attribute 여섯 파일도 확인했다. 원시 NetCDF/실행파일은 receipt에 명시된 로컬 build 경로에 보존하며 이 작은 proof package에는 포함하지 않는다.

## 실패 기록과 범위

첫 시도는 wrapper가 참조하는 unused quilt symbol의 fixture stub 누락으로 link RC1이었다. 두 번째는 fixture가 backend 초기화 전에 파일을 열어 RC71이었다. 각 plan·실제 RC·로그를 원래 상태로 보존한다. 최신 시도는 수정된 fixture의 별도 실행이며 과거 FAIL을 PASS로 덮지 않는다.

별도 reader의 첫 비교는 기존 writer가 저장하는 `ZZ+blank` 3바이트를 2바이트 ZZ로 잘못 기대해 실패했다. 최초 스크립트와 사유를 보존하고 정확한 3바이트 조건으로 다시 확인했다. Production source나 허용오차를 바꾼 것이 아니다.

전체 compile/link 시도 4회, fixture 실행 3회이며 마지막 O0/O2 두 실행이 성공했다. WRF 전체 build/forecast, MPI, RTE, LBLRTM 새 실행은 0이다. NetCDF4 병렬, 다른 compiler/REAL64, 모든 메모리 순서 API 및 inherited cc helper mismatch까지 승인하지 않는다.

[체크리스트](../acceptance/review-resolution-checklist.json)는 후보 기준 22항목 중 15개 제한적 완료, 7개 물리·최종 OPEN/FAIL을 유지한다. 현재 main의 완료 근거는 12개이며 새 I/O 3개는 병합 전이다. Original acceptance19/current12와 historical 두 package의 55개 payload를 보존한다. Nc·PSD/LUT, RFMIP strict 21개 FAIL, LBLRTM negative OD 및 최종 예보 승인은 닫지 않는다.
