# Cloud-input 검토 후속 항목

기준 main은 `6e7353a096267007892d7960458a86f310c4b38d`이다. 이번 PR은 이 기준에서 구름 입력을 분리한다. 37번 `SWDOWN`은 실제 하향 단파를 반환하고, `GSW`는 순흡수다. 회색 알베도 보간과 FARMS 덮어쓰기는 제외하고 `swint_opt=0`을 요구한다.

## 구름·눈 전처리: 일부 수정, 물리 검증 남음

RRTMGP 전용 input builder는 층 압력과 qc/qi/qs에서 구름 안 경로를 직접 만들며, MP5 10% ice/90% snow partition과는 별개로 legacy flag 5가 적용하던 0.99 factor 및 130 µm 초과 snow mass 감소를 RRTMGP에는 적용하지 않는다. 직접 builder/adapter API는 `cf=0`과 양의 응축수를 엄격히 거부하고, 양의 작은 cf는 overflow하지 않는 한 그대로 쓴다. WRF wrapper만 명시적 `allow_clear_condensate` 정책으로 `cf=0` 입력을 허용한다: 해당 층의 cloud optical paths를 0으로 설정하고 debug level 100에서 생략된 원래 grid-box 경로 및 reason code 6을 층별 출력한다. 양의 cf에서는 수상 mass를 보존하지만 WRF 예외의 trace condensate는 radiative optical input에서 생략되어 질량 보존으로 간주하지 않는다. 최종 debug SCM의 5분 적분 로그에서 LW/SW 각각 reason code 6을 793회 기록했고, 최대 생략량은 층·호출당 0.1037024 g/m²였다. P3 qi→snow 변환 및 위의 legacy snow 보정은 RRTMG 경로에만 남겨 두었다. 공통 미세물리 source는 유지된다.

눈 반경이 없는 경우 현재 RRTMGP 경로는 진단 빙정 반경을 눈 반경 proxy로 쓴다. 이는 임시 대리값이며 물리적으로 검증된 눈 크기 처리가 아니다. 실제 WRF 기둥 replay와 독립 광학 진단으로 MP5/P3 및 flag 3/4/5 입력을 확인하고, 큰 눈 입자와 빙정·눈 분리에서 경로와 광학두께를 비교해야 한다. 임의의 새 질량 보정은 추가하지 않는다.

현재 계수의 액체 축은 유효반경 2.5–21.5 µm, 빙정 축은 유효직경 10–180 µm이다. 이는 `diamice_lwr/upr`, `radliq_lwr/upr` 및 [RRTMGP 공식 cloud optics 인터페이스](https://earth-system-radiation.github.io/rte-rrtmgp/reference/rrtmgp-fortran-interface/sourcefile/mo_cloud_optics_rrtmgp.f90.html)로 확인한다. 액체 입력은 반경으로 유지하고 ice/snow 반경만 유효직경으로 한 번 변환하며 optical LUT만 clip한다. WRF wrapper는 일반 유효반경을 넘기고 Fu 1.0315 배율을 적용하지 않는다. Fu-special flag 3 conversion은 direct backend API compatibility path에만 있다.

남은 확인은 양의 cf에서 수상 mass closure, WRF의 의도된 cf=0 omission 진단, 큰 눈 입자와 빙정·눈 분리 사례의 독립 입력 재생 및 optical sensitivity다. 임의 보정계수는 추가하지 않는다.

## 입력과 표본 정책: 검증 보강, WRF packing 미완

Backend 공통 validator가 입력 shape, finite 값, 물리 범위, 압력층의 감소 순서와 layer/interface 일관성, 음수 q/path, 구름분율, 활성 수상 반경을 검사한다. 비활성 수상의 유한한 0 반경은 허용된다. 직접 backend API는 양의 경로에 cf=0을 거부한다. builder의 기본 모드도 `cf=0`과 양의 응축수를 거부하며 overflow를 감지한다; WRF wrapper만 clear-path omission 모드를 선택한다. 전 컬럼 글로벌 계수 경로는 초기화 후 변경할 수 없다.

Backend의 선택적 `column_seeds(:)`는 컬럼별 표본 시드를 받아 packing/reordering으로 결과가 달라지는 것을 막는다. 현재 WRF driver는 기존 scalar-seed 정책을 유지하며 도메인 P2 항목으로 남아 있다. 실제 WRF 컬럼 packing 또는 32–256 컬럼 batch 연동은 아직 구현·측정하지 않았다. 날짜 경계, restart, 타일/MPI 분할, 다중 시드 통계도 남아 있다. 60초 SCM의 CFL 문제 원인을 McICA로 단정하지 않는다.

## 검증 계층: 미해결

최종 standalone suite는 28/28 통과했고 64컬럼 batch aggregate maximum difference는 0이었다. GNU serial full build 후 수정된 backend/helper/wrapper 4개 모듈을 incremental recompile/relink했다. 37 및 baseline 4 SCM, 6-time cloud diagnostics SCM, 회색표면 4개 및 `swint_opt=1,2` 거부 시험이 모두 통과했다. 이전 SWDOWN-fix 4 run과 새 출력 공통변수 204개는 bitwise identical였다. batch 허용치는 `1e-3 + 1e-5 × max(1, |reference|)`이며 bitwise 비교는 batch 경로 사이에 주장하지 않는다. 개발 시험은 입력 변환과 backend 동작을 확인할 뿐 완전한 물리 검증을 뜻하지 않는다.

- 같은 입력·계수·광학·표본을 사용하는 독립 RRTMGP 기준 출력과 비교한다.
- 실제 WRF 전처리 기둥을 저장하고 독립 계산에 재입력하여 상태 변환을 검증한다.
- LUT 경계 clip 전후 유효 크기와 optical property를 기록하고, 눈 반경 proxy 및 MP5/P3 사례의 광학 영향을 진단한다.
- 실제 WRF에서 컬럼 packing, batch 크기 32–256, 할당량과 실행시간을 측정한다.
- 실제 호출·재사용·restart 규약에 따라 누적 에너지의 시간적분을 검사한다. 양수 검사만으로 적분을 입증하지 않는다.
- 수정 전 공식 4/4와 수정 후 4/4를 비교하여 기존 기능 보존을 확인한다. 이번 변경의 직전 실행파일 4/4 비교는 공식 upstream 회귀와 구분한다.
- 24–48시간, restart, 실제 예보·둥지, MPI/OpenMP와 실패 시 집단 종료 계약을 검증한다.
- SSiB 전체 결합 및 지형·경사면의 동일 기준면 플럭스 비교를 수행한다. 이번 분광 시험은 독립 어댑터의 네 알베도 경로이며 전체 SSiB 운용 검증이 아니다.

이 항목들은 완료된 시험으로 주장하지 않는다. 짧은 SCM 성공은 일반 예보영역의 물리 정합성이나 예보 정확도 확보를 의미하지 않는다.
