# UDM27 상수·오류 처리와 구름 광학 원인 분리

37/37은 UDM27 및 `use_mp_re=1` 계약을 유지한다. 이번 반영은 WRF 상수 연결과 계수파일 실패 경로를 정리하고, 기존 4↔37 차이의 구름 광학 원인을 실험으로 분리한다. 기존 4/4 계산과 생산 경로의 CF·graupel·hail·SW delta 정책은 변경하지 않는다.

## Host 상수와 재생

WRF 초기화는 `g`, `cp`, `mwdry*1.e-3`을 `rrtmgp_init`에 넘긴다. 기체 분자 기둥량과 복사 가열률은 수분경로·WRF 열역학에 사용한 상수계와 일치시킨다. 선택적 host 인자가 없는 독립 실행은 upstream 배정도 기본 상수를 정확히 보존한다. 나중 domain의 path·roughness·상수 변경은 거부하며, process 전체의 동일한 설정만 허용한다.

새 V5 capture는 중력(m/s²), 건조 정압비열(J/kg/K), 건조공기 분자량(kg/mol)을 배정도로 기록한다. 독립 재생도 같은 값을 로드 전에 설치한다. V1–V4는 그 저장본의 기존 기본값을 유지한다. 시험은 수증기를 포함한 hydrostatic dry molecular column, 장·단파 flux divergence와 K/day, 비기본 상수 독립 재생, 기본값의 정확한 보존, 재초기화 불일치 거부를 검사한다. 상수 통일의 효과를 수십 W/m²의 구름 차이 원인으로 해석하지 않는다.

## 계수파일 오류

NetCDF helper와 기체·구름 계수 로더는 하나의 fatal callback을 사용한다. 독립 라이브러리는 기본 `error stop`을 유지하고, WRF 초기화는 파일을 읽기 전에 `wrf_error_fatal3` callback을 설치한다. 이로써 WRF의 MPI 종료 경로를 호출하도록 연결했다. 라이브러리 자체는 WRF 모듈에 의존하지 않는다. callback이 잘못 반환해도 계산을 계속하지 않는다.

없는 파일과 구조가 깨진 NetCDF의 기체/구름 네 경우 및 adapter의 WRF fatal 표식을 검사한다. 다중 rank에서 실제 collective 종료를 확인하는 것은 별도 MPI 실행 검증이며, 독립 시험만으로 통과를 선언하지 않는다.

## RRTMG 구름 광학 교체

다음은 GNU serial WRF를 먼저 빌드한 뒤 실행한다.

```sh
python3 WRF/test/rrtmgp/build_rrtmg_optics_bridge.py \
  --netcdf-prefix "$NETCDF" --output-dir build/rrtmg-cloud-bridge
python3 WRF/test/rrtmgp/test_rrtmg_optics_attribution.py \
  --data-dir WRF/run --reference-executable build/replay-reference/reference_column \
  --bridge-executable build/rrtmg-cloud-bridge/rrtmg_sw_optics_bridge \
  --captures build/udm-native4-audit/control/audit-on/capture/sw_000002.input \
             build/udm-native4-audit/control/audit-on/capture/sw_000006.input \
  --audit-csv build/udm-native4-audit/control/audit-on/audit/same_state.csv \
  --output-dir build/rrtmg-cloud-bridge/attribution-control
```

현재 시험 범위는 cf=1인 얼음만의 기둥이다. 같은 대기·기체 광학·McICA mask·표면·RTE에서 준비된 구름 τ/ω/g만 RRTMG의 실제 cloud optics로 바꾼다. 기체·mask·청천 출력은 정확히 유지되어야 한다. 세 대조는 RRTMG native-wrapper 수치 반경, native 반경을 Fu generalized size로 변환한 경우, 기존 `reicalc(T)*1.0315` 경우다. 이를 생산 광학 선택으로 자동 채택하지 않는다.

WRF 상수 반영 후 같은 상태 자료에 적용한 5개 cloudy 호출에서 native-wrapper 교체는 하향 단파를 64.98–65.02 W/m² 줄였다. 같은 상태의 실제 native-radius RRTMG4와 RRTMGP37 차이는 약 61.86–61.88 W/m²였다. 구름 광학을 교체한 RRTMGP와 실제 RRTMG4 사이의 잔차는 약 −3.16~−3.12 W/m²였다. 기본 반경 대조의 교체 효과는 −58.06~−57.32 W/m²였다. 이는 입력 연결·seed 차이만으로 큰 차이를 설명하기보다 Fu/Yang 계열 광학 선택과 변환을 분리해야 함을 보여준다.

RRTMG와 고정 RRTMGP 첫 두 밴드의 공통 경계는 2600/2680 cm⁻¹로 다르다. 그 알려진 경계 차이에만 ordered-band 근사 대응을 사용하므로 위 수치는 정확한 분광 동등성 증명도, 관측 정확도 판정도 아니다. 남은 잔차에 기체·경계·RTE 차이가 섞이며 이 실험만으로 각 기여를 확정하지 않는다. 약 65 W/m²가 모든 구름과 실제 예보에 적용되는 오차율이라는 해석도 하지 않는다.

## 남은 운용 검증

UDM의 CF 정의, precipitation occurrence, graupel 광학과 양의 hail 미지원, 음수 수상체의 실예보 분포, seed 시간/도메인 정책, DNI, MPI/OpenMP·restart·둥지·24시간 예보 및 WRF batch packing은 별도 단계다. `em_scm_xy`의 upstream MPI 금지는 우회하지 않는다. MPI는 `em_real`로, OpenMP는 지원하는 별도 빌드로 평가한다. 독립 계산·계수 오류 시험 성공과 실제 예보의 물리 정확성을 구분한다.

## 공식 원본 RRTMG4 및 누적량 회귀

공식 WRF v4.8.0 `06d4240ae989cc3e50af412bb472df3d9048783c`를 같은 GNU 13.3 도구와 고정 submodule로 독립 빌드했다. UDM4 control/mixed 각각 7개 시각의 208개 공통 변수 배열은 기존 baseline과 이번 코드의 4/4 출력에 비트 단위로 일치했다. NetCDF 파일 전체 해시는 global metadata 차이 때문에 다를 수 있으며 배열 동일성과 구분한다. 이 결과는 두 짧은 SCM 사례의 기존 기능 보존 근거다.

누적량 검사는 DT=10초, 복사 주기 30초, 적분 120초에서 13개 history 시각의 12개 증분을 모두 검사한다. 초기 오프셋은 차분으로 상쇄하고 첫 구간도 포함한다. 매 구간 `ACC[n]-ACC[n-1]=F[n]*DT`를 확인하며 실제 flux 유지 8구간과 갱신 4구간을 포함했다. SW/LW 최대 오차는 각각 0.001526/0.000305 W·s/m²였고 첫 증분만 훼손한 음성 대조를 거부했다. restart 누적 규약은 후속 검증이다.

검증 결과와 원본 빌드 manifest는 `validation/rrtmgp37/runtime-contracts/`에 보존한다. 독립 54개 시험, fresh serial WRF 빌드, UDM37 실제 capture/replay 및 같은 상태 4/37 audit를 통과했다. MPI/OpenMP 실행 판정은 별도 PR의 검증으로 남긴다.

## 후속 실행 상태

[CPU OpenMP와 실제 실행](CPU_OPENMP.md)에 GNU smpar의 OMP1/2 SCM, 10분 real-data MPI1/2·MPI2/OMP2, 실제 MPI 계수 누락 종료 및 직렬 SCM restart 근거를 추가했다. 두 SCM의 checkpoint와 모든 후속 누적량 증분도 연속 적분과 일치했다. 이 범위의 계약은 통과했으며, MPI restart·둥지·장시간 적분·관측 정확도는 별도 조건이다.

24시간 실제 자료의 첫 37/37 시도는 음수 QI를 거부하여 종료됐다. [native 수상체 진단](NATIVE_HYDRO_DIAGNOSTICS.md)은 4번과 37번 양쪽의 복사 호출 입력을 읽기만 하며, 값과 위치를 기록한다. 현재의 엄격한 음수/hail 계약을 아직 완화하지 않았고, 작은 음수·graupel·hail·CF=0 제외량의 실제 분포를 다음 정책의 근거로 사용한다.
