# WRF RRTMGP 37 실행 검증

2026년 10월 1일, 이 저장소의 실제 연결 코드로 GNU Fortran 13.3.0, NetCDF C 4.9.2와 Fortran 4.5.4에서 검증했다. 결과는 CPU 계산과 WRF 출력 계약을 확인한다. 예보 정확도, 다른 컴파일러, MPI/OpenMP 및 GPU는 검증하지 않았다.

## 이 저장소에서 완료한 확인

| 확인 | 결과 |
| --- | --- |
| 등록 receipt와 이식 파일·계수 해시 | 통과 |
| 공식 Registry 생성 및 상류 원본과 경고 비교 | 통과, 기존 경고 56개 동일 |
| 기존 독립 pinned-core 맑은 하늘 시험 | 통과, assertion 17개, 에너지 잔차 0 |
| 연결된 WRF 어댑터 CMake 컬럼 시험 | CTest 1/1 통과 |
| WRF em_scm_xy GNU serial 전체 빌드 | wrf.exe와 ideal.exe 생성 |
| LW/SW 37번, 시간 간격 10초, 5분 적분 | SUCCESS COMPLETE WRF |
| 같은 사례의 기존 LW/SW 4번 | SUCCESS COMPLETE WRF |
| 37번 동일 조건 재실행 | 아래 복사·온도·바람 필드가 비트 단위로 일치 |
| 장파 37 / 단파 4 혼합 선택 | PAIR_REQUIRED로 거부 |
| aer_opt=1 및 cldovrlp=4 설정 | RRTMGP 설정 검사에서 거부 |

컬럼 시험은 맑은 하늘, 액체 전운량, 부분 구름과 액체·빙정·눈, 중첩 0~3 및 야간을 다룬다. 에너지 일관성, clear sky 보존, 직달·산란 및 가시광·근적외 합계, 표본 시드 재현성을 검사한다. 기존 `port/` core 시험과 실제 연결된 WRF 컬럼 시험은 별도 경로다.

SCM은 1999년 10월 22일 19:00부터 19:05 UTC까지 실행했다. 출력 6개 시각에서 복사 플럭스·누적 에너지·경향이 유한하고 출력되었음을 확인했다. `SWDOWN=SWDDIR+SWDDIF`, `RTHRATEN=RTHRATLW+RTHRATSW`가 성립했다. 이 검사는 경향 산출을 확인하며 실제 온위 업데이트의 정확성을 입증하지 않는다. 누적량의 양수 검사도 시간적분 규약을 입증하지 않는다. 검증 스크립트의 `--expected-options`로 출력 파일의 장파·단파 선택이 각각 37/37과 4/4임을 검사했다. 반복 비교는 SWDOWN, GLW, SWDDIR, SWDDIF, 세 복사 경향, ACSWDNB, ACLWDNB, T 및 W를 대상으로 했다.

37번 최대 SWDOWN은 284.65 W/m², 최대 GLW는 281.03 W/m²였다. 4번은 각각 230.89 및 282.61 W/m²였다. 계수·구름 광학·표본화가 다르므로 이 차이를 정확도 개선으로 해석하지 않는다. 4번 실행 성공은 기존 경로가 작동함을 확인하며, 수정 전 WRF와의 비트 단위 회귀 비교는 수행하지 않았다.

## 시험 조건과 한계

이전 개발 검증에서 원본 SCM의 60초 시간 간격은 작은 3×3 주기 격자에서 CFL 초과 후 온도 범위를 벗어나 종료됐다. 10초 설정은 정상 완료했고 반복 결과가 일치했다. 컬럼별 McICA 시드의 수평 차이가 SCM 균일성 가정과 관계가 있을 수 있으나 이 원인 해석은 추가 검증이 필요하다. 재현용 namelist는 10초를 명시한다.

WRF 설정 오류는 STOP 메시지와 종료 코드 0을 반환할 수 있다. 미지원 설정은 로그의 거부 메시지로 검사했고 정상 실행은 `SUCCESS COMPLETE WRF`를 확인했다. NetCDF를 비표준 위치에 설치한 환경에서는 `LD_LIBRARY_PATH`를 설정해야 한다.

전체 WRF CMake 빌드는 수행하지 않았다. CMake 검증 범위는 라이브러리와 독립 어댑터 시험이다. 실제 예보 도메인, 지형, 중첩, SSiB, 화학 결합, 계수 범위 밖 대기 상태 및 병렬 성능은 미검증이다. 장파 산란과 에어로졸을 포함한 HAFS 전체 suite 이식은 후속 작업이다.

## 재현과 근거

저장소 루트에서 실행한다. WRF 실행 파일 빌드 방법은 [이식 안내](README.md)에 있다. Python NumPy와 netCDF4가 필요하다.

```bash
WRF/test/rrtmgp/run_scm.sh build/new-scm37 37
WRF/test/rrtmgp/run_scm.sh build/new-scm4 4
python3 WRF/test/rrtmgp/validate_scm.py \
  build/new-scm37 build/new-scm4 --expected-options 37 4
```

측정 결과와 실행 파일 SHA256은 저장소의 [`validation/rrtmgp37/results.json`](../../../validation/rrtmgp37/results.json)에 기록했다. 로컬 전체 빌드 로그는 `build/wrf-compile-scm.log`, SCM 로그·출력은 `build/scm-37`, `build/scm-4`, `build/scm-37-repeat`에 있다. 대용량 실행 파일·출력·빌드 로그는 커밋하지 않는다. PR CI는 Registry/core, 컬럼 시험과 GNU serial SCM을 실행하고 빌드·실행 로그 및 결과를 artifact로 보관한다. CI 상태는 로컬 측정 기록과 별도로 보고한다.

## SWDOWN 역산 수정 후 검증

검토 기준 main `7061603` 이후 37번 `SWDOWN=SWDNB` 직접 반환을 적용했다. 수정한 driver와 설정 검사 모듈을 GNU serial 빌드의 동일 플래그로 재컴파일하고 WRF/ideal을 재링크했다. 다음을 실제 실행으로 확인했다.

- 회색 알베도 0·0.2·0.99·1과 분광 네 알베도 입력의 독립 컬럼 주야간 시험: 통과. 실제 solver 상향 플럭스와 알베도로 가중한 가시광·근적외 직달/산란 플럭스도 비교했다.
- 37/37과 4/4의 기본 5분 SCM: 통과.
- LSM=0, usemonalb=true 및 prescribed ALBBCK를 사용해 실제 출력 ALBEDO를 일정하게 유지한 네 회색 SCM: 통과. 모든 시각에서 `SWDOWN=SWDNB=SWDDIR+SWDDIF`, `GSW=SWDNB-SWUPB` 및 유한성을 검사했다. 알베도 1에서도 하향 플럭스가 계산됐다.
- `swint_opt=1,2`: 명시적인 미지원 메시지로 거부됐다.
- 수정 전 포팅본 4/4와 수정 후 4/4: 공통 출력 변수 203개가 비트 단위로 일치했다. 이 비교는 공식 upstream 원본과의 회귀 시험을 대신하지 않는다.

분광 시험은 어댑터 컬럼 시험이며 SSiB 전체 결합 또는 지형·경사면의 운용 시험은 아니다. 결과는 [`swdown-fix.json`](../../../validation/rrtmgp37/swdown-fix.json)에 기록한다. 추가 WRF 시험은 다음 명령으로 재현한다.

```bash
python3 WRF/test/rrtmgp/test_surface_scm.py build/new-surface-scm
```

## RRTMGP 전용 구름 입력 수정 검증

기준 main은 `6e7353a096267007892d7960458a86f310c4b38d`이다. GNU serial `em_scm_xy` 전체 빌드에 성공했고, 청천 처리 정책을 반영한 입력 함수·어댑터·LW/SW 래퍼를 같은 빌드 플래그로 재컴파일해 실행 파일을 재링크했다. 최종 실행 파일로 다음을 확인했다.

- CTest 28/28 통과: 수상별 질량 계약, 작은 양의 구름분율, 큰 눈 반경, 입력 오류 거부, 64컬럼 개별·일괄·역순 비교 및 야간 영값. 이번 실행에서 일괄/개별/역순의 최대 절대차는 0이었다. 시험 허용치는 `1e-3 + 1e-5 × max(1,maxabs(a),maxabs(b))`이며 모든 플랫폼의 비트 일치를 보장하지 않는다.
- 37/37 및 4/4의 5분 SCM과 6개 출력 시각의 유한성·플럭스/경향 합계: 통과. 회색 알베도 0·0.2·0.99·1 SCM 및 `swint_opt=1,2` 거부도 통과했다.
- 기존 SWDOWN 수정본의 4/4 출력과 새 4/4 출력: 공통 변수 204개가 비트 단위로 일치했다. 공식 원본 WRF와의 회귀 비교는 아니다.
- `debug_level=100`으로 실행한 원래 LSM2 SCM: LW/SW 각각 793개의 `RRTMGP_CLEAR_CONDENSATE_EXCLUDED` 층별 진단이 있었고 모두 reason=6, 유한한 양의 제외 경로였다. 최대값은 층·복사 호출당 0.1037024 g/m²였다. 이를 전체 기둥 질량이나 시간 누적으로 해석하지 않는다.

양의 분율에서는 정확한 분율을 사용하여 각 수상 질량을 보존한다. WRF는 미량 응축수를 남기고도 구름분율을 0으로 진단하므로, 연결부는 해당 층을 명시적으로 청천 처리한다. 이 층의 응축수는 복사 광학 입력에서 제외되고 제외 질량을 진단하며, 모든 층에서 무조건 질량이 보존되는 구현으로 해석하지 않는다. 직접 입력 함수·어댑터의 기본 계약은 `cf=0`과 양의 경로를 거부한다.

측정 기록은 [`cloud-input.json`](../../../validation/rrtmgp37/cloud-input.json)에 있다. 실제 WRF는 여전히 `ncol=1`이며, 성능 측정·tile packing·MPI/OpenMP·restart·실제 예보와 독립 광학 기준 비교는 후속 검증 대상이다. 실제 WRF의 청천 처리 진단 시험은 다음 명령으로 재현한다.

```bash
python3 WRF/test/rrtmgp/test_cloud_scm.py build/new-cloud-contract-scm
```

## c705c44 이후 표본·분류·독립 재생 검증

표준 GNU serial `compile -j 12 em_scm_xy` 빌드가 성공했다. CTest 29/29, 2,048개 시드의 10개 cf sweep, 기존 알베도·보간 거부·청천 제외 시험이 통과했다. 평균·분산은 배정도이며 희박한 분율의 0회 표본을 정확도 증거로 해석하지 않는다.

MP2/4/5의 기본 5분 SCM, MP4/5의 약 248.865 K 수상체 제어 사례(5분), 실제 LW/SW 기둥의 독립 광학·RTE·WRF 변환 비교가 통과했다. 광학 배열·mask는 이 실행에서 정확히 일치했고 반환값은 단정도 허용오차 안에 있었다. 직전 4/4와 새 실행의 공통 변수 204개도 비트 단위로 일치했다.

MP95 제어 사례는 초기 과냉각 QC/QS의 양의 질량·구름 τ·cloudy mask와 독립 재생을 통과했으나 최종 후속 적분은 `RRTMGP_INPUT_PATH_OVERFLOW layer=1`로 종료됐다. 별도 반복에서는 압력 범위와 압력두께 오류도 관측했다. `--capture-only` 결과의 `PASS_COLUMN_REPLAY`는 예보 성공을 의미하지 않으며 `wrf.forecast.status=FAILED_AFTER_CAPTURE`를 함께 저장한다. 같은 SCM 설정의 baseline 4/4 탐색 실행도 segfault로 종료됐다. 이 오류들의 원인을 확정하거나 입력을 clip하지 않았다. Thompson/P3 runtime 시험은 완료된 범위에 포함하지 않는다.

[재생 방법](COLUMN_REPLAY.md), [현재 후속 항목](REVIEW_FOLLOWUP.md), [측정 JSON](../../../validation/rrtmgp37/sampling-replay.json), [표본 CSV](../../../validation/rrtmgp37/small-cf-sampling.csv), [표본 그림](../../../validation/rrtmgp37/small-cf-sampling.svg)에 코드·결과·한계를 구분했다. 로컬 표준 빌드는 기존 checkout에서 의존성을 따라 재빌드했으며 fresh checkout 전체 빌드는 PR CI에서 별도로 확인한다.

## UDM 동일 상태 물리 감사 (2026-10-02)

새 감사는 현재 타일의 UDM 내부 CF와 source step을 보존하고, live WRF 입력을 실제 4/37 wrapper에 다시 넣는다. 1,024개 결정론적 시드 집합, 모든 LW/SW 호출의 독립 재생, audit ON/OFF history 비트 비교 및 기존 4/37 저장본과의 공통 배열 회귀를 실행했다. 현재 standalone CTest는 48개이며 모두 통과했다. 반경 입력 경로·CF·graupel·delta 정책별 숫자와 해석은 [UDM 물리 감사 보고서](../../../validation/rrtmgp37/udm-physics-audit/REPORT_ko.md)를 참조한다. 저장본 4/4 회귀는 이전 포팅 실행파일과의 비교이며 pristine 공식 WRF와의 직접 실행 비교가 아니다.

## 독립 upstream RFMIP 기준 비교 (2026-10-03 공개 기록)

공식 RFMIP 1,800 profiles의 네 플럭스 배열에서 pinned upstream과 vendored CPU library가 bitwise 일치했다. 공개 reference에 대한 LW는 PASS지만 SW는 양쪽 모두 동일하게 원래 `1e-5 W/m²` 허용오차를 초과한다. 공개 SW residual을 성공으로 처리하지 않았다. 공개 reference는 g256/g224 청천이며 별도 production gas g128/g112에서도 같은 upstream/vendor 일치를 확인했다. 실제 UDM cloud/precipitation 또는 g128/g112의 독립적인 물리 정확도 시험은 아니다. [독립 검증 범위와 미지원 광학](INDEPENDENT_REFERENCE.md)에 판단과 재현 경로를 구분한다.
