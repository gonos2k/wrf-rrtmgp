# WRF–RRTMGP 37

현재 37번 개발·평가 범위는 **UDM(`mp_physics=27`) 전용**입니다. 장·단파 `37/37`, `use_mp_re=1`을 요구합니다. UDM native radii, qc/qi cloud optics, qr/qs precipitation optics를 연결하며 qg는 제외량 계측, qh는 명시적 미지원으로 처리합니다. [현재 UDM 입력 계약과 검증 한계](WRF/doc/rrtmgp/UDM_ONLY.md) · [UDM 실행·비교 검증 기록](validation/rrtmgp37/udm-only/REPORT_ko.md)를 먼저 확인하십시오. 아래 다른 미세물리 결과는 이전 버전의 검증 기록입니다.


공식 WRF v4.8.0의 장파·단파 복사 옵션 `37/37`에 RTE+RRTMGP CPU 계산을 연결하는 개발 저장소입니다.

## 현재 상태

37번을 실제 WRF 복사 초기화와 LW/SW 호출 경로에 연결했습니다. 압력·온도·기체의 기존 전처리를 재사용하고, 구름·빙정·눈은 RRTMGP 전용 입력 함수에서 준비합니다. 양의 구름분율에서는 수상별 질량을 보존합니다. WRF가 분율을 0으로 진단한 층은 명시적으로 청천 처리하며 제외 질량을 진단합니다. 장파와 단파는 함께 37로 선택하고 에어로졸·화학 피드백은 거부합니다.

로컬 CTest 29개, 2,048개 시드의 작은 구름분율 시험, 실제 WRF 기둥의 독립 재생, GNU serial SCM과 알베도·청천 처리 시험이 통과했습니다. WSM5(4)와 Ferrier(5)의 구름 사례는 5분 SCM까지 통과했습니다. ETAMPNEW(95)는 초기 기둥의 분류·재생만 통과했고 후속 SCM 적분 실패를 별도로 기록합니다. 기존 포팅본과의 4/4 공통 변수 204개가 비트 단위로 일치했습니다. WRF 호출은 계속 `ncol=1`이며 실제 예보·성능·MPI/OpenMP·restart는 후속 검증 대상입니다. 설정과 근거는 [WRF 이식 안내](WRF/doc/rrtmgp/README.md), [검증 기록](WRF/doc/rrtmgp/VALIDATION.md), [NOAA 적용 사례](WRF/doc/rrtmgp/NOAA.md)에 있습니다.

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
