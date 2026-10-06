# 실제 양성 활성화의 저장 증거

이 패키지는 같은 private 진단 소스·실행 파일·파생 입력을 사용한 2분 WRF OFF/ON 실험을 보존합니다. MPI 4개, OpenMP 스레드 2개, 시간 간격 60초이며 두 실제 모델 호출은 모두 RC0으로 종료되어 회수됐습니다. 큰 history/restart NetCDF, 실행 파일, 라이브러리와 실행 권한 파일은 포함하지 않습니다. 새 컴파일이나 모델 실행은 이 패키지 작성·검증에 필요하지 않습니다.

입력에서는 QVAPOR 한 원소만 바꿨습니다: Python 인덱스 `(0,6,1,22)`, Fortran 위치 `(i,j,k)=(23,2,7)`. 전체 197개 변수의 원본/파생 비교와 메타데이터 일치 기록을 보존했습니다. 입력 offset은 이전 호출 상태에서 목표 RH 1.003을 가정해 정했습니다. 실제 첫 step의 RH는 **1.0134907960891724**였으므로 목표값을 관측값으로 해석하면 안 됩니다. 이전 PR141 입력의 0-rate 결과는 별개의 음성 대조 증거입니다.

새 실행의 NUMBER packet 20개/880개 행과 QNN 경계 packet 24개/1,056개 행을 보존합니다. NUMBER 대상은 `(23,2)`, 44개 층, 두 step의 10개 stage입니다. QNN 경계 목적지 `(23,1)`과 인접 outflow 원본 `(23,2)`는 서로 다른 위치입니다. 두 packet 집합은 모두 이번 파생 입력 실행에서 나온 것이며 이전 zero-Nc 경계 packet과 섞지 않았습니다. NUMBER에는 step·clock이 있지만 RK identity는 없으므로 QNN과 임의의 RK 동일성을 주장하지 않습니다.

첫 step의 대상 k7은 원문 `min(1,...)` 활성화 분율 **1** 분기에 들어갔습니다. 실제 `NC_ACT=1666666.625`, `PC_ACT=2.2078543437942244e-8`이고 두 번째 step은 RH<1로 두 rate 모두 0입니다. 첫 step의 두 번째 NN-rate cap과 QV mass cap은 비활성입니다. stage21 초기 상태로 캐시된 CPM/XLV, stage30 입력과 stage31 출력의 source-ordered REAL32 연산을 독립 저장자료 검토에서 확인했습니다. host 상수는 CP=1004.5, CPV=4×RV, XLV=2.5e6, SVPT0=273.15이며 포화 표의 triple-point 273.16과 구별합니다.

**기존 CCN 하한의 효과를 숨기지 않습니다.** 첫 step에서 REAL32 `NC_ACT×dt`는 1e8로 반올림됩니다. NN의 하한 적용 전 값 0에 기존 `ccnmin=5e7`이 적용되어 NN=5e7이 됩니다. 저장 NC 증가량은 99999992이고 저장 NN+NC 합은 49999992 증가합니다. 합의 변화는 저장된 REAL32 값을 binary64로 승격해 뺀 수치입니다. 이것은 원문 하한·반올림 연산의 관측이며 수농도 보존이나 물리적 타당성의 승인이 아닙니다. 기록의 `m3` 등 단위 접미사도 process 문맥을 표시할 뿐, producer 단위 권위를 증명하지 않습니다.

원문 후속 과정 때문에 stage31의 모든 상태가 radius helper까지 그대로 남지는 않습니다. 첫 step k7 NC는 helper50까지 198858336으로 남지만 QC는 0.0004965627449564636에서 0.0005615028203465044로 변합니다. helper51 cloud radius는 8.9602444859338e-6 m입니다. stage40 반환 복사→helper50 입력→helper51 입력의 9개 공통 필드는 두 step 모두 44층에서 정확히 이어집니다. 별도 독립 검토는 QC/QNC/NN/NR/QV/QR profile을 source-step에 맞춘 history와 연결했습니다. packet clock 0/1분의 microphysics 출력은 완료된 history 1/2분과 연결하므로 단순 clock 동일성으로 조인하지 않습니다.

OFF/ON history(231개 변수)와 restart(668개 변수)는 각각 전체 파일 바이트와 SHA가 같습니다. 원래 실행 후 비교는 모든 변수 배열·dtype·차원·shape·속성 및 전역 속성을 확인했고 독립 검토도 전체 파일을 다시 비교했습니다. root는 기록된 두 process group에 남은 member가 없음을 별도 확인했습니다. 이 패키지의 CI는 외부 대형 NetCDF를 다시 열지 않고 보존된 비교 기록·해시·count를 인증합니다.

원래 실행 소스 head는 `8017ff7caf8f979dc16e1d9119c9a88eaa362a2b`, tree는 `eef44b724e452bd412431928bad1d26f15c6dab4`입니다. 부모 `positive-nc-stage` 패키지의 고정 manifest와 소스/빌드 자산을 재사용합니다. 새 `module_physics_init.F.gz`는 추가 host 초기화 call을 보여 주기 위한 원문 무손실 gzip이며 stored hash와 inflated hash를 모두 검사합니다. 원문 소스·입력·모델 정책을 이 PR에서 변경하지 않습니다.

v1의 열역학 oracle 준비 오류, v2의 arm 경로 오류, v3의 validator 경로 핀 오류는 `preparation-failures/`에 별도로 남깁니다. 이것들은 모델 subprocess 실패가 아니라 실행 전 준비 차단입니다. 최종 v4만 실제 두 모델 호출에 사용됐습니다. 원본 `prepared.json`의 `UNRUN` 계열 표현은 작성 당시 기록이며 실제 종료는 `runtime/execution.json`으로 판정합니다. 원본 runner·input preparer·독립 checker는 실제 실행된 과거 소스입니다. private 절대 경로와 외부 파일에 의존하므로 packaged 위치에서 바로 재실행하는 도구로 제공하지 않습니다.

`verify_saved.py`는 표준 라이브러리만 사용합니다. 닫힌 파일 목록·해시·원문 copy/gzip·부모 자산·실제 RC/reap·packet 구조와 source-state 기본 REAL32 연산을 검사합니다. 포화 lookup/native transcendental 함수와 전체 rate 식을 CI에서 독립 native 계산한 것으로 주장하지 않습니다. 해당 수치 증명은 보존된 원래 독립 검토에 연결합니다. 이전 PR141의 zero-rate 증거를 양성 결과로 재해석하지 않습니다.

Nc 단위, CCN/구름입자 population/PSD/LUT 계약, restart 단위, 물리적 정확도 및 forecast relevance는 모두 열려 있습니다. 이 증거는 선택된 manufactured 상태의 실제 활성화 응답과 observer passivity에 한정되며 scientific acceptance는 false입니다.

임의의 working directory에서 다음 saved-only 명령으로 검증할 수 있습니다.

```sh
python3 -I -S /path/to/repository/validation/rrtmgp37/positive-nc-activation/verify_saved.py
```
