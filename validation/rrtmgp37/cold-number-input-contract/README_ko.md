# Cold-start 세 수농도 입력 계약 보강

기준 main은 PR156의 `23c118bd04729a73a3e7bb873e14b2c37b262f31`, tree는
`3c5ce46d5a89264c0cbffb4352a5d09152c3327f`이다. PR156의 원본 package는 변경하지 않는다.

새 checker는 파일의 QNCCN/QNCLOUD/QNRAIN 59층 REAL32 비트를 START_PRE와 대조한다.
START_PRE→START_POST 및 RESET_PRE→RESET_POST에서는 QNC/QNR 비트를 검사한다.
START_POST→RESET_PRE 사이에는 실제 수송이 있으므로 두 지점의 불변성을 요구하지 않는다.
Restart도 같은 파일 대조 함수를 사용하며 기존 reset 부재 검사를 유지한다.

제조 QNR은 양수·비균일 raw sentinel이다. 초기화 블록에서 잘못 0으로 바뀌는 경우를
구분하기 위한 입력이며 실제 rain PSD/수농도 단위의 승인 근거가 아니다.
생산 Fortran·Registry·초기화 정책·밀도/CF 변환·UDM27 전용 조건은 변경하지 않았다.

루트가 검증된 GNU13 REAL32 serial allocatable PR156 관측 실행파일을 재사용해
ideal 1회, cold forecast 5회, 실제 checkpoint restart 1회(총 모델 자식 7회)를 실행했다.
이번 로컬 fresh compile/full WRF build는 0회이다. 원래 5917개 tracked WRF 파일과
현재 파일의 차이는 시험 Python 하나이며, 다섯 관측 대상 생산 source hash도 일치한다.
실행파일 digest와 재사용 근거는 binary-reuse.json에 있다. 첫 metadata 명령의 잘못된
상대 작업경로는 정정 기록으로 남겼으며, 모델 실패로 집계하지 않는다.

각 ON 실행 RK 2124쌍, 총8496쌍의 source-order 상대잔차는 0이다.
파일만 한 ULP 바꾼 QNN/QNC/QNR 세 반례는 원래 downstream join이 PASS인 채 거부된다.
START_POST와 RESET_POST의 QNC/QNR 변경 네 반례도 거부된다. 추가 모델 실행은 없다.
청천/구름 OFF·ON 각211개 history 배열과 전체 파일 bytes는 동일하다.

`verify_saved.py`는 정확한 package roster/hash와 실행 영수증의 범위를 검증하는
stdlib integrity 검사이다. NetCDF 내용을 독립적으로 해석하는 검사가 아니다.
`replay.py`는 저장한 실행 checker와 NetCDF 원본을 재생하는 검사이며 독립 산술 reference가 아니다.
Fresh remote connected-host workflow는 현재 checker로 전체 WRF를 다시 빌드·실행한다.
그 결과는 이 로컬 sealed package의 실행 결과와 별도로 기록한다.

현재 cold start의 QNN 상수 reset은 기존 정책을 확인한 것이다. 외부 입력 보존 정책의
승인은 OPEN이다. QNN/QNC 단위·population·PSD/LUT·RFMIP strict·LBLRTM·최종 예보는
이 시험으로 닫지 않는다. original19/current12, 완료15/잔여7, production_accepted=false 유지.
