# main 기반 runtime/I/O 통합 검증

PR #135–#137의 선택된 소스·시험·CI 변경을 main `a91d0d8` 위에 통합했다.
22개 대형 historical evidence 파일을 새 통합 계산으로 복사하지 않았다.
기존 source pin 및 acceptance 19/12 gate는 보존된다.

새 working-source byte hashes에 결속한 root 실행은 한 번 수행됐으며 8개
상위 검사 모두 RC0이다. 실행기 dummy lifecycle 4개, startup 광학/관측기
manufactured controls 19개, acceptance controls 8개가 통과했다. 실제 Registry
생성물의 6개 field 및 원본 Registry 입력의 warning 비교도 통과했다.
누락 sentinel의 RC1은 명시된 음성시험의 기대값이다.

실제 NetCDF backend의 O0/O2 시험은 ordered 3×5 필드, 두 개의 서로 다른
시각과 unlimited Time, INTEGER/REAL4/DOUBLE→REAL4 write, REAL4→DOUBLE read,
ZZ/zz 및 오류 후 정상 읽기를 확인했다. module_io의 rank/case helper는
원문 선택 후 실행했다. 이것은 전체 module_io/MPI restart 실행이 아니다.

검사별 실제 PID/RC와 종료 기록, 실행 source 및 직접 NetCDF 의존성의 hash는
JSON receipt에 있다. 로컬 경로의 원본 로그와 NetCDF 파일은 저장소에 복사하지
않았다. 이 묶음은 작은 receipt와 source review의 보존이며 원본 출력 전체의
독립 복제를 주장하지 않는다.

이 tree의 전체 Make/CMake build/SCM 및 MPI checkpoint/restart는 별도 종료조건이다.
과거 분기에서의 48h·restart 결과를 이 tree의 새 실행으로 재표기하지 않는다.
Nc/PSD/LUT·RFMIP strict·LBLRTM OD·관측 정확도·production approval은 열려 있다.
