# 실제 WRF의 QNN/QNC 초기화·수송·UDM·반경 연결

생산 기준 main `32c13f2fd39d6846e35212f4f7bb53079fd6bd68`, tree
`487d10b2ed8bf6e9defa12341a410833186d1d82`. PR155의 11개 check는 모두
terminal SUCCESS다. 이전 pending 기록과 원래 archive는 변경하지 않는다.

이 시험은 함수 추출 fixture가 아니다. 현재 전체 WRF를 GNU13.3, REAL32,
serial, allocatable, CMake EM_SCM_XY로 새로 빌드하고 실행했다. 다섯 소스에
시험용 관측 블록을 넣은 snapshot이며, 블록 제거 시 원본 bytes가 복원된다.
5910개 tracked WRF 파일도 관측 블록 제거 후 작업 소스와 동일함을 확인했다.
생산 Fortran, Registry, UDM27 전용 gate와 물리 정책은 수정하지 않았다.

## 한 실행에서 연결한 경계

선택 위치는 domain1, i=j=1, 실제 mass layer1–59다. 실제 Registry slot은
QNN=2, QNC=3이며 snapshot 실행에서 기록한다. 10초 timestep의 여섯 step에서
RK1–3의 current/old/tendency/old-new mass/map/dt를 기록한다. 정확한
stage/step/slot/layer 집합, RK 갱신식, inter-RK current/old buffer, 초기/반환값과
다음 수송, 마지막 RK와 driver/UDM 소비를 검사한다. 실제 advection tendency가
0이 아닌 기록을 요구한다. 이 조건은 전체영역 입자수 보존 승인이 아니다.

| 실제 arm | 검사 |
|---|---|
| 비균일 QNCCN/QNCLOUD cold start, OFF/ON | 입력→start_em→RK→첫 상수 reset→UDM |
| QNCCN=0 cold start, ON | start_em 기본값 초기화; 변수 누락 시험은 아님 |
| 제조 warm-cloud cold start, OFF/ON | 양의 QC/QNC가 실제 native helper에 도달 |
| 실제 warm-cloud 60초 checkpoint, 60→120초 restart | QNN/QNC 모두 비균일; start_em 보존과 첫 reset 비실행 |

각 ON arm은 실제 RK update 2124쌍을 포함한다. 최종 네 ON arm의 총 8496쌍에서
declared REAL32 연산 순서의 상대잔차 최대값은 0이었다. 순서/계약 검사이며
별도 모델의 예보 정확도 검증이 아니다. Warm-cloud에서 양의 QC/QNC helper
입력 186개를 관측했다. helper 입력→출력→driver 반환의 number/mass/density/
temperature/radius는 같은 call·셀에서 비트로 연결된다. 모멘트·단위 승인은 아니다.

청천/구름 두 OFF/ON 쌍 모두 history 211개 배열과 전체 NetCDF 파일 bytes가
동일했다. 같은 관측 실행파일의 OFF/ON이며, 관측기 없는 별도 생산 실행파일이나
pristine WRF와의 비교는 아니다. 전체 파일 bytes 일치를 요구하므로 dtype,
shape, attributes까지 다른 파일이 이 gate를 통과할 수 없다.

## 실제 초기화 정책 확인

비균일 입력의 선택 layer10 QNN은 `109000000`으로 start_em에 들어가 그대로
유지된다. 첫 실제 RK3 후 `109071704`이며 driver reset 직전 값과 일치한다.
driver는 이를 `100000000`으로 바꾸고 UDM 입구도 같은 값이다. 이것은 기존
option37의 정책 관측이다. 외부 입력 보존 요구사항의 승인이나 새 정책 수정이 아니다.
비균일 checkpoint restart에서는 이 첫-step reset이 관측되지 않는다.

실제 specified lateral boundary는 실행하지 않았다. X/Y periodic SCM이므로
0속도 경계 reset의 실제 실행 수지까지 닫았다고 주장하지 않는다. PR155의
선택 boundary 절차 근거는 기존 범위로 유지한다. 실제 수송 옵션은
scalar_adv_opt=0, RK3, 수평5차/수직3차이고 다른 옵션/PD limiter는 미검증이다.

## 실행·과거 시도·원본

최종 fresh producer build의 configure/build RC와 실행파일 hash를 보존했다.
새 orchestration의 첫 runtime 이후 checker에 nonzero tendency와 whole-history
bytes 필수 gate를 보강하여 **같은 fresh binary로 한 번 더 실행**했다. 최종
runtime은 ideal1 + forecast5 + restart1의 일곱 child가 모두 RC0이다.
최종 build-receipt의 일곱 초기 모델 child와 후속 최종 일곱 child는 별도 기록이다.
이를 기상 사례 수로 합산하지 않는다. RTE는 WRF 안에서 사용되며 별도 RTE/
LBLRTM reference solver는 실행하지 않았다.

첫 observer는 RK1에서 아직 사용되지 않은 old buffer를 읽었다. Root의 원시
기록 점검과 팀 소스 검토에서 확인해 explicit IF로 현재값을 기록하도록 수정했다.
이전 관측 소스·preparer·RC·receipt는 superseded로 보존한다. 초기 runtime-v1/v2
Python checker snapshot은 따로 보존되지 않았으므로 최종 재현 근거로 쓰지 않는다.
새 빌드 실행기의 첫 configure는 install prefix 누락으로 권한 오류 RC1이었다.
작업 디렉터리 안의 prefix로 수정했고 실패는 별도 보존했다. 현재 fresh build는 성공했다.

작은 원본 NetCDF 입력/history/checkpoint, 실제 stdout/stderr를 gzip으로 보존했다.
압축 전후 hash와 receipt 연결을 검사한다. 실행파일과 라이브러리 자체는 포함하지
않는다. source tree와 source hash는 실행 snapshot의 관측 변경과 구분한다.
외부 trusted manifest hash가 없으면 내부 무결성 검증이다. 제공한 table hash는
OS의 실제 file-open 추적이 아니다. 팀은 소스와 작은 JSON만 검토했으며 원시
과학 자료 판독·컴파일·모델 실행은 root가 수행했다.

```sh
python3 -I -S validation/rrtmgp37/connected-host-number/verify_saved.py
python3 WRF/test/rrtmgp/test_udm_connected_host_build.py WRF \
  --workdir /fresh/connected-host --parallel 2
```

첫 명령은 stdlib로 정확한 roster, 실제 기록의 단계 연결과 RK 식, 다섯 변조 거부를
재검사한다. NetCDF 파일은 bytes/hash로 연결하며 새 NetCDF reader를 실행하지 않는다.
두 번째는 현재 working source의 새로운 full build/runtime이다. 새 workflow는
과거 저장 검증과 별도로 current-source를 빌드하며 원본 output을 artifact로 보존한다.
Fresh workflow artifact는 저장 verifier 전체를 포함한 self-contained package가
아니므로 실행 checkout과 함께 검토해야 한다. 원격 신규 CI의 terminal 상태는
PR에서 별도로 확인한다; 로컬 PASS를 원격 PASS로 대신 쓰지 않는다.

real.exe/외부 분석장 ingestion, 모든 영역/수송 옵션, 물리적 단위·population,
PSD/LUT 호환성, 연속/restart 예보 endpoint 동등성, 장시간 관측 정확도는 미승인이다.
완료15/잔여7, RFMIP strict21 FAIL, LBLRTM negativeOD 및
`production_accepted=false`를 유지한다.
