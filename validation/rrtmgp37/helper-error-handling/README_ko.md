# NetCDF helper·SCM namelist 오류 처리

기준 main은 `9d7e79182395cd81bc7ed3805126575f64005bc3`이다. 상속된 오류 경로를 수정하며 복사 계수·UDM 수농도·입자 크기·발생분율 정책은 변경하지 않는다.

## 변경

- GetDim은 실패 시에도 NDim=0을 반환한다. ZeroLengthHorzDim·ExtOrder·ExtOrderStr는 배열 접근 전에 Status를 검사한다. 오류 logical은 true, 정수 인자는 유지, 문자열 출력은 빈 값으로 정의한다.
- 추가 unchecked caller FieldIO도 잘못된 order를 scalar field I/O로 진행하지 않고 반환한다.
- SCM set_assignment는 요청한 group 안의 0/1/중복 개수를 검사한다. 다른 group·주석·따옴표 값은 보존한다. 지원 범위는 scalar RHS, 별도 행의 group 경계와 comma-segment assignments이며 지원하지 않는 whitespace-separated layout은 명시적으로 거부한다.

## 실행 근거

`netcdf-backend-result.json`은 축약 함수 재구현이 아니라 실제 wrf_io.F90과 field_routines.F90를 NetCDF 라이브러리에 연결한 시험이다. GNU O0/O2, fcheck=all, finit-integer=99에서 정상 helper 순서 20개·오류 short token 5개, 오류 후 정상 순서 복구, FieldIO의 잘못된 read 거부·버퍼 보존을 검사했다. 기존 3×5 ordered ZZ의 2개 Time 기록·이름·타입 변환·읽기·쓰기 모두 통과했다. generic rank helper는 module_io에서 원문을 추출한 것이며 전체 module_io 실행은 아니다. 오류 token은 API의 3자 표현 범위이며 임의 길이 문자열 지원을 주장하지 않는다. 기존 cc의 GetDim/helper 수용 범위 차이는 이번 수정 범위가 아니다.

`parent-negative-classified.json`은 기준 main의 실제 backend O0 빌드에서 ExtOrderStr('qq')가 NDim=99로 배열 경계 오류(RC2)를 낸 기록이다. 최초 실행기의 예상 진단 substring 판독은 실패했다(`above upper bound`를 기대했으나 GNU는 `outside of expected range`를 출력). 원래 harness 실패·stderr·RC를 보존하고 새 메타데이터 판독만 추가했다. 컴파일·probe 재실행은 없다. negative_backend_once.py는 당시 실행한 단발 기록이며 현재 HEAD를 대상으로 다시 쓰는 일반 재현 실행기가 아니다.

`namelist-final-result.json`은 최종 15개 unittest 방법을 확인한다. 초기 Python packet은 수정 중간의 12개 namelist와 기존 4개 dummy-process 정리 시험 및 original acceptance 무결성 검사를 보존한다. 최종 namelist 결과가 현재 source pin에 결속된다. process cleanup 코드는 변경하지 않았다.

실행 수는 NetCDF final 2compile/2fixture, 중간 수정본 2compile/2fixture, parent negative 1compile/1probe다. 전처리·nf-config 호출은 별도 journal에 있다. 전체 WRF 빌드·예보·MPI·RTE·LBLRTM 실행은 0이다. 새 임계값·허용오차 완화·음수 clipping이나 physical acceptance 승인은 없다.

## 재검증

```bash
python3 WRF/test/rrtmgp/test_netcdf_zz.py WRF --workdir build/new-netcdf-helper-check --output build/new-netcdf-helper-check/receipt.json
python3 WRF/test/rrtmgp/test_udm_startup_snow_scm_namelist.py
```

NetCDF runner는 기존 validate-port standalone-columns CI에 포함된다. 새 namelist 시험은 standalone CTest에 등록했다. 이 자료는 원격 full WRF CI가 완료됐다는 증거가 아니다. 원래 acceptance19/current12, historical source pins와 물리 OPEN/FAIL을 유지한다.
