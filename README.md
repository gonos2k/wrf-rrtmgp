# WRF–RRTMGP 37

현재 37번 개발·평가 범위는 **UDM(`mp_physics=27`) 전용**입니다. 장·단파 `37/37`, `use_mp_re=1`을 요구합니다. UDM native radii, qc/qi cloud optics, qr/qs precipitation optics를 연결하며 qg는 제외량 계측, qh는 명시적 미지원으로 처리합니다. [현재 UDM 입력 계약과 검증 한계](WRF/doc/rrtmgp/UDM_ONLY.md) · [UDM 실행·비교 검증 기록](validation/rrtmgp37/udm-only/REPORT_ko.md)를 먼저 확인하십시오. 아래 다른 미세물리 결과는 이전 버전의 검증 기록입니다.

싸락눈·우박에는 [동질 얼음 PSD 수치 기준](validation/rrtmgp37/frozen-optics-reference/README.md)과 [명시적 실험 모드](WRF/doc/rrtmgp/UDM_FROZEN_EXPERIMENT.md)를 연결했습니다. 기본 모드의 qg 제외·양의 qh 거부는 유지합니다. 실험 모드 1의 PR20 실행파일은 실제 자료로 MPI 4개 rank에서 24시간을 완료했으며, 12시간 체크포인트에서 재시작한 13시간 출력의 모든 수치 배열이 연속 적분과 일치했습니다. 메타데이터 `START_DATE` 차이는 별도로 기록합니다. [실행·비교 근거](validation/rrtmgp37/realdata-parallel/README.md)는 수치 실행 검증이며, 젖은 얼음 입자·관측 정확도 또는 PR21 코드의 24시간 검증을 뜻하지 않습니다.

[오프라인 조회·보간 검사](validation/rrtmgp37/frozen-optics-lookup/README.md)는 외삽 거부, 단위·질량 계약과 크기 격자 세밀화 결과를 기록합니다. 9개 크기 노드의 시험 중간점에서 최대 차이는 소광 정규화 기준 약 0.440%이며, 전체 오차 상한이나 예보 정확도를 의미하지 않습니다.
기체 광학의 건조공기량도 WRF native 층 질량에서 변환하도록 보완했습니다. [native gas-column 계약](WRF/doc/rrtmgp/NATIVE_GAS_COLUMNS.md)과 실행 근거에서 적용 범위를 확인하십시오.



공식 WRF v4.8.0의 장파·단파 복사 옵션 `37/37`에 RTE+RRTMGP CPU 계산을 연결하는 개발 저장소입니다.

## 현재 상태

37번을 실제 WRF 복사 초기화와 LW/SW 호출 경로에 연결했습니다. 압력·온도·기체의 기존 전처리를 재사용하고, 구름·빙정·눈은 RRTMGP 전용 입력 함수에서 준비합니다. 양의 구름분율에서는 수상별 질량을 보존합니다. WRF가 분율을 0으로 진단한 층은 명시적으로 청천 처리하며 제외 질량을 진단합니다. 장파와 단파는 함께 37로 선택하고 에어로졸·화학 피드백은 거부합니다.

WRF 호출의 기본 묶음 크기는 `ncol=1`이며, CPU에서는 `WRF_RRTMGP_BATCH_SIZE=32/64/128`로 여러 기둥을 묶어 계산할 수 있습니다. MPI 4개 rank·OpenMP 2개 thread의 동일 실행파일 시험에서 1·32·64·128개 묶음의 40분 출력과 체크포인트가 일치했습니다. 이는 해당 구성의 수치 회귀 검증이며, 성능 향상·장시간 restart·둥지·실제 예보 정확도는 별도 검증 대상입니다. [묶음 계산 구현과 검증 범위](validation/rrtmgp37/column-batching-source/README.md), [WRF 이식 안내](WRF/doc/rrtmgp/README.md), [검증 기록](WRF/doc/rrtmgp/VALIDATION.md), [NOAA 적용 사례](WRF/doc/rrtmgp/NOAA.md)에 설정과 근거를 기록합니다.

초기 범용 포팅 단계에서는 로컬 CTest 29개, 2,048개 시드의 작은 구름분율 시험, 실제 WRF 기둥의 독립 재생과 GNU serial SCM을 검사했습니다. WSM5(4)·Ferrier(5)의 5분 SCM 성공, ETAMPNEW(95)의 후속 적분 실패 및 이전 4/4 공통 변수 204개 일치는 그 단계의 기록입니다. 현재 UDM27 지원 범위나 최신 실험 모드의 검증으로 확대하지 않습니다.

동일 실행 파일과 초기 상태로 기존 RRTMG 4/4와 37/37의 7개 조건을 새로 비교했습니다. 14개 5분 SCM이 통과했으며, 청천 지표 하향 단파 차이는 −0.80 W/m², 구름 조건의 차이는 +30.67~53.48 W/m²였습니다. 층별 경향과 10초 누적량 계약도 검사했습니다. 관측 정확도 우열을 뜻하지 않으며 큰 격자 SCM 탐색의 양쪽 NaN 실패는 유효 통계에서 제외했습니다. [비교 보고서·그림·수치](validation/rrtmgp37/rrtmg-comparison/REPORT_ko.md)에 조건과 한계를 기록했습니다.

## 기준 소스와 자료

- WRF v4.8.0: `06d4240ae989cc3e50af412bb472df3d9048783c`
- NCAR/rte-rrtmgp: `41c5fcd950fed09b8afe186dede266824eca7fd3`
- WRF 실행 계수: earth-system-radiation/rrtmgp-data `ea788bb39876948fa8d2c235665ccff19b4686b5`, LW 128 / SW 112 g점 및 밴드 구름 LUT

WRF에서 사용하는 라이브러리는 `WRF/external/rte_rrtmgp/`, 계수는 `WRF/run/rrtmgp-*.nc`에 있습니다. 출처, 로컬 로더 변경, 자료 URL·SHA256 및 라이선스를 함께 보존합니다. `config/registration37.json`은 현재 WRF 연결 상태와 이식 파일 해시를 기록합니다.

기존 `external/`, `port/`의 독립 clear-sky 수치 부품 및 검증 경로는 유지합니다. 이 경로의 자료 버전은 v1.8.1 (`aafa333a60c06fca2fbf219fbd17e7f432b43e3f`)이며, WRF 실행용 구름 LUT와 구분됩니다. `config/imported-sources.json`은 최초 상류 소스 반입 기록이고, 그 뒤의 WRF 변경은 등록·이식 기록으로 추적합니다.

## 검증

```bash
python3 tools/register37.py --check
python3 tools/validate.py registry
python3 tools/validate.py core
cmake -S WRF/test/rrtmgp -B build/rrtmgp-columns \
  -DNETCDF_INCLUDE_DIR="$NETCDF/include" \
  -DNETCDF_LIBRARY_DIR="$NETCDF/lib"
cmake --build build/rrtmgp-columns -j 8
ctest --test-dir build/rrtmgp-columns --output-on-failure
```

NetCDF C·Fortran 개발 파일과 GNU Fortran이 필요합니다. 비표준 라이브러리 위치에서는 `LD_LIBRARY_PATH`를 설정합니다. Registry/core 검증은 WRF 실행 검증과 별도로 보고합니다. CI는 PR에서 Registry/core, 연결된 컬럼 시험과 실제 WRF SCM 실행을 수행하며 로그와 결과를 보관합니다.

### Fatal-message reporter patch status

A follow-up patch improves the WRF fatal diagnostic emitted by the RRTMGP LW/SW wrappers. The previously recorded RA37 OMP=2 MPI abort had no explicit temperature cause; the separate pre-patch OMP=1, one-hour run exposed a graupel LW lookup at 179.996 K below the table's 180 K minimum. The component worker test passes and the adapter library compiles, but the full WRF executable has not yet been rebuilt with this reporter patch. The proposed table extension has not been generated, and neither this diagnostic patch nor the evidence below constitutes a completed 48-hour RA37 run. The preserved terminal receipts and logs are in [the fatal-diagnostic evidence bundle](validation/rrtmgp37/matthew-fatal-diagnostic/README.md).
