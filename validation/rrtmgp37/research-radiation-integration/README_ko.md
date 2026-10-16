# 선택형 복사 연구 기능의 일반 빌드 통합

기준 main은 PR179 `3485400c30b54c853787a4a4f9d54a3baea90424`입니다.
이전 private 후보의 성공을 보존하면서, 이번에는 **일반 WRF 소스**에 두
독립 옵션을 기본값 0으로 통합했습니다.

- `rrtmgp_capacity_policy=1`: native 층의
  `C=md*cpd*(1+(Rv/Rd)*qv)` 연구 source.
- `rrtmgp_liquid_size_policy=1`: 최종 Gamma8/veff=0.1의 광학 REL.

설정·범위·파일 계약은 [연구 옵션 문서](../../../WRF/doc/rrtmgp/RESEARCH_RADIATION_OPTIONS.md)에 있습니다.
환경변수나 전역 setter로 후보를 선택하지 않습니다. 열용량은 호출자 소유
배열로 전달하며 확장층은 기존 처리를 유지합니다. 미세물리 RE_CLOUD,
number/population 정책 기본값, 계수, cloud CF/mask와 held-theta 방식은 유지합니다.

## 실제 실행과 동일 입력 대조

GNU13.3 serial REAL32 O2의 **전체 일반 CMake 빌드**를 사용했습니다.
최종 빌드의 적격 WRF 프로세스는 14회입니다: 정상 9회와 의도한 거부 5회입니다.
독립 기상 사례 14개가 아니라 같은 작은 제조 기주의 실행 variants입니다.
Standalone UDM/RTE/Mie/LBLRTM/ideal을 새로 실행하지 않았습니다.
RTE는 실제 WRF 복사 호출 내부에서 실행됩니다.

양의 구름 입력의 모든 물리 변수 bytes를 유지하고 두 정책 표기만 바꾼
[0,0], [0,1], [1,0], [1,1]을 각각 60초 실행했습니다. 각 실행의 source10에서
양의 구름 22층의 q/eta/rho/footprint→Gamma8 M0/M2/M3→REL→고정 LUT를 연결합니다.
열용량을 켠 두 구성은 native 층의 `C*Tdot-Q` 최대 절대값이 LW/SW 모두
**4.44e-16 W/m²**였습니다. Clear/all-sky 분모도 동일하고,
exported REAL32 clear flux/HR의 차이는 해당 반올림 상계로 검사합니다.
같은 source10의 host 상태와 다음 history의 LW/SW 온위 경향도 연결합니다.

기존 양의 구름 [0,0]/[0,1], 기존 입력 capacity 단독, 옵션을 생략한 기본값은
각각 PR179의 **211개 history 배열×7시각**과 bytes가 같았습니다.
각 옵션의 비활성·단독 경로가 일반 빌드에서 기존 결과를 재현했습니다.

결합 효과는 같은 변수·시각·층의 signed
`X11-X10-X01+X00` 배열을 보존했습니다. 예를 들어 최대 절대 교차차이는
T 1.83105e-4 K, RTHRATEN 9.15461e-7 K/s, SWDOWN 5.45502e-4 W/m²입니다.
이는 결합 피드백과 유한정밀도의 진단이며, 0이어야 하는 조건이나 관측
정확도 판정이 아닙니다. 네 실행의 source10 상태는 이전 복사 피드백으로
달라지므로 순수한 동일 상태 반경 민감도라고 해석하지 않습니다.

## 호출 사이 checkpoint

결합 [1,1]은 복사 간격 30초에서 60초 연속 실행과 **20초 checkpoint 재개**를
비교했습니다. History의 20–60초 겹치는 **214개 배열이 비트 동일**합니다.
Checkpoint의 두 정책 표기, STEPRA=3, 유지된 LW/SW/total 및 clear 경향은
같은 시각의 연속 실행 상태와 같습니다. 재개 후 첫 실제 복사 source는
30초이고, 해당 raw/input/result 배열도 연속 실행의 source30과 같습니다.
Seed와 calendar 정책은 그 raw 입력과 결과 비교에 포함됩니다.

열용량만 바꾸거나 크기만 바꾼 restart, 선택 기능의 누락 표기·잘못된 형식,
미지원 theta_m 구성은 history 생산 전에 거부됐습니다. Serial fatal의 RC0을
성공으로 해석하지 않고 fatal/성공 문구와 산출물을 함께 검사했습니다.

진단용 37 scratch 호출에도 두 선택값과 같은 host QNC를 전달합니다.
진단 ON인 결합 실행은 진단 OFF의 211개 history 배열×7시각과 비트 동일했습니다.

## 실패·시험 코드 수정 기록

초기 두 compile 시도는 편집 중 남은 module interface 때문에 실패했고,
소스를 고정한 재빌드로 해소했습니다. 첫 WRF 시도는 새 빌드에 기존
big-endian 플래그가 없어 RRTMG_LW_DATA 초기화에서 RC2로 중단됐습니다.
후보 복사 계산에 진입하지 않았습니다. 이후 기존 Fortran/C/NetCDF 플래그로
전체 빌드한 실행만 적격 자료로 사용했습니다. 초기 로그와 실패 receipt는
`attempts/` 및 build 기록에 보존합니다.

앞선 빌드의 잘못된 문자열 metadata는 실제로 `Malformed ... metadata`로
거부됐으나, 시험 코드가 일반 `policy differs` 문구를 기대해 중단됐습니다.
그 거부의 원문·이전 receipt와 시험 소스 변경의 역산본을 보존하고 기대 문구를 수정했습니다.
초기 실행기는 원본 script 해시를 receipt에 고정하지 않았으므로 역산본을 원본 bytes 인증으로 취급하지 않습니다.
이미 수행한 정상/거부 실행은 재사용하고 마지막 미지원 구성 검사만 이어서
수행했습니다. 이어 수행한 recipe와 수정 내역도 저장했습니다.
이후 진단용 호출 전달을 보완한 최종 빌드에서는 수정된 전체 실행기를 그대로
수행해 14회를 모두 완료했습니다. 작업 전체의 WRF 프로세스는 초기 RC2 1회,
앞선 빌드 13회, 최종 빌드 14회의 총 28회이며 최종 통계에 중복 합산하지 않습니다.

## 재생과 해석 범위

`python -I -S verify_saved.py`와 `test_saved.py`는 저장 자료 재생이며 새 과학
실행이 아닙니다. 실제 실행기는 `WRF/test/rrtmgp/test_research_radiation_scm.py`입니다.
Identity는 소스 snapshot, Registry, 빌드 flags/cache/link, 실행파일·라이브러리,
실제 입력·계수, 실행 journal과 결과를 연결합니다. 과거 근거의 해시를 현재
후보 결과로 덮어쓰지 않습니다. 향후 소스가 바뀌면 과거 snapshot으로의
재생과 현재 소스 적용 여부를 구분합니다.

Capture `.input`은 광학·기체 입력입니다. 연구 capacity는 `.result`, 그 원천
md/qv·선택값은 `.raw`에 별도로 기록합니다. `.input`만 pressure-only standalone
도구로 재생한 것을 연구 capacity 재생으로 집계하지 않습니다.

**기존 일곱 종료 조건은 bytes 그대로 유지하며 `production_accepted=false`입니다.**
고정 조성 constant-kappa 완결 가정과 Gamma8은 제한된 연구 정의입니다.
전체 습윤 열역학·상변화 에너지, 실제 PSD 관측 타당성, 원 LUT 생성 PSD,
공통 PBL host 물수지, RFMIP/LBLRTM FAIL, 일반 입력·경계·혼합상·장시간/관측
정확도는 이번 통합 PASS로 승인되지 않습니다.
