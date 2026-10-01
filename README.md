# WRF–RRTMGP 37

공식 WRF v4.8.0의 장파·단파 복사 옵션 `37/37`에 RTE+RRTMGP CPU 계산을 연결하는 개발 저장소입니다.

## 현재 상태

37번을 실제 WRF 복사 초기화와 LW/SW 호출 경로에 연결했습니다. 기존 RRTMG 전처리를 재사용하고, RRTMGP 기체·구름 광학 및 RTE 플럭스와 가열률을 WRF 출력·온위 경향에 전달합니다. 장파와 단파는 함께 37로 선택합니다. 에어로졸과 화학 복사 피드백은 명시적으로 거부합니다.

독립 컬럼 시험과 GNU serial `em_scm_xy` 실행으로 개발 이식본을 검증합니다. 실제 예보, 관측 비교, MPI/OpenMP, GPU, 전체 WRF CMake 빌드는 아직 검증하지 않았습니다. 사용 설정·지원 범위·재현 명령은 [WRF 이식 안내](WRF/doc/rrtmgp/README.md), [검증 기록](WRF/doc/rrtmgp/VALIDATION.md), [NOAA 적용 사례](WRF/doc/rrtmgp/NOAA.md)에 있습니다.

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
