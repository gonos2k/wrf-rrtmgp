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

SCM은 1999년 10월 22일 19:00부터 19:05 UTC까지 실행했다. 출력 6개 시각에서 복사 플럭스·누적 에너지·경향이 유한하고 계산·적용되었음을 확인했다. `SWDOWN=SWDDIR+SWDDIF`, `RTHRATEN=RTHRATLW+RTHRATSW`가 성립했다. 검증 스크립트의 `--expected-options`로 출력 파일의 장파·단파 선택이 각각 37/37과 4/4임을 검사했다. 반복 비교는 SWDOWN, GLW, SWDDIR, SWDDIF, 세 복사 경향, ACSWDNB, ACLWDNB, T 및 W를 대상으로 했다.

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
