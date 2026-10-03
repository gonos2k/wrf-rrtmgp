# WRF–RRTMGP 37

현재 37번 기본 개발 범위는 **UDM(`mp_physics=27`) 전용**입니다. 장·단파 `37/37`, `use_mp_re=1`을 요구합니다. 기본 frozen-optics 모드 0은 qg 제외량을 계측하고 양의 qh를 거부합니다. 별도 실험 모드 1은 명시적인 동질 얼음 구형 입자 가정 아래 G/H 광학을 계산하며 기본값이 아닙니다. [UDM 입력 계약](WRF/doc/rrtmgp/UDM_ONLY.md)과 [검증 기록](WRF/doc/rrtmgp/VALIDATION.md)을 먼저 확인하십시오.

## 2026-10-03 후속 검증 상태

이 문서의 소스 기준은 `de312b7a53cefc2f69024e8b96de4bd586f00816`이며 이는 PR #32 head와 같다. 아래 SHA는 공개 PR head를 고정하고, 해당 revision의 실행파일·설정·시험 범위만 가리킨다. 링크는 이 문서 기준에 없는 후속 결과도 참조하므로 main 병합 상태를 주장하지 않는다.

| PR / head | 범위와 제한 |
|---|---|
| [#26](https://github.com/gonos2k/wrf-rrtmgp/pull/26) `792f36b6bbc442f0db37b5cb9fdf19dd33600082` | UDM legacy SR 인자를 j 행별로 전달. 이후 비교의 소스 기준. |
| [#27](https://github.com/gonos2k/wrf-rrtmgp/pull/27) `f7f0ad164b50684bb170b729f0836c0e8404a8e0` | 한 스텝 MPI 분해 진단. pristine WRF MPI1/MPI4에서 63/202 공통 변수가 달랐으며 원인은 미확정. |
| [#28](https://github.com/gonos2k/wrf-rrtmgp/pull/28) `fdafa534d5641fa2251ad5b02d294d57167b81fb` | 선택 기둥 감사와 실제 입력의 독립 LW/SW 재생. 제한된 기둥 재생이지 전체 상태·예보 검증은 아님. |
| [#29](https://github.com/gonos2k/wrf-rrtmgp/pull/29) `74c5b5f9dbff835883dcbd678e0cb092e2145c8b` | 계수/표 오류에서 bounded MPI collective 종료를 검사. |
| [#30](https://github.com/gonos2k/wrf-rrtmgp/pull/30) `bb56ec0ad5a0fbd2ef2027a291554fc40d6c7291` | GNU tile-owned workspace 및 같은 MPI/OMP 배치끼리의 byte parity. 서로 다른 MPI 분해 간 동등성 증거는 아님. |
| [#31](https://github.com/gonos2k/wrf-rrtmgp/pull/31) `360cbf6668c84ef7d00c163fdce0d8dd54daca44` | #26 SR 수정 소스로 4-rank 24시간 RA4 legacy/RA37 mode-1 실행, 각 arm의 12→13시 재시작 연속성 확인. 앞선 SR 수정 전 비교는 혼입되어 별도 역사 기록으로 유지. |
| [#32](https://github.com/gonos2k/wrf-rrtmgp/pull/32) `de312b7a53cefc2f69024e8b96de4bd586f00816` | 수상별 제외 경로와 LUT 크기 clipping을 계측. 복사 오차나 총 물 손실을 뜻하지 않음. |
| [#33](https://github.com/gonos2k/wrf-rrtmgp/pull/33) `0f1ae2967281df3cfa4d8ec5c0f6764fe025158d` | 2시간, 부모 보간으로 초기화한 자식 도메인 smoke. 고해상도 입력, nested restart, skill 검증은 아님. |
| [#34](https://github.com/gonos2k/wrf-rrtmgp/pull/34) `958cf46b074b3927e9ca939ad9d7c371ac11e17b` | FPK/DRA SURFRAD 한 날짜의 점 복사 플럭스 비교. 일부 지표는 RA37 오차가 작고 일부는 커서 우열을 보이지 않음. |
| [#35](https://github.com/gonos2k/wrf-rrtmgp/pull/35) `7ea36677ae085e8edc61b9161c075bdeda8441d2` | Intel serial 1분 RA37/RA4 실행. 이 시험에서 512 MiB stack은 실패했고 1 GiB 설정은 통과했음; 보편 최소 요구량이나 Intel MPI/장기 실행 검증은 아님. |

세부 상태, 재현 자료 및 변경 전 실패 이력은 각 PR과 [검증 문서](WRF/doc/rrtmgp/VALIDATION.md)에 연결한다. 위 PR들은 당시 공개 head를 가리키며 병합 상태나 `main` 포함을 주장하지 않는다.

싸락눈·우박의 [동질 얼음 PSD 수치 기준](validation/rrtmgp37/frozen-optics-reference/README.md)과 실험 설정은 [명시적 frozen 모드](WRF/doc/rrtmgp/UDM_FROZEN_EXPERIMENT.md)를 참조합니다. 2026-10-03 현재 공개 근거에는 PR20의 mode-1 24시간 실행과 PR31의 #26 기반 corrected pair가 있습니다. PR31에서는 RA37 arm만 mode 1이고 RA4는 legacy 4/4입니다. 앞선 strict-negative 37 실행 실패와 SR 행 전달 문제가 포함된 이전 4/4 비교는 서로 다른 과거 결과이며 혼동하지 않습니다. Mode 1은 실험적 균질 얼음 가정이고, default mode 0의 qh fatal을 바꾸지 않습니다.

[오프라인 조회·보간 검사](validation/rrtmgp37/frozen-optics-lookup/README.md)는 외삽 거부, 단위·질량 계약과 크기 격자 세밀화 결과를 기록합니다. 9개 크기 노드의 시험 중간점에서 최대 차이는 소광 정규화 기준 약 0.440%이며, 전체 오차 상한이나 예보 정확도를 의미하지 않습니다.
기체 광학의 건조공기량도 WRF native 층 질량에서 변환하도록 보완했습니다. [native gas-column 계약](WRF/doc/rrtmgp/NATIVE_GAS_COLUMNS.md)과 실행 근거에서 적용 범위를 확인하십시오.



공식 WRF v4.8.0의 장파·단파 복사 옵션 `37/37`에 RTE+RRTMGP CPU 계산을 연결하는 개발 저장소입니다.

## 현재 상태

37번을 실제 WRF 복사 초기화와 LW/SW 호출 경로에 연결했습니다. 압력·온도·기체의 기존 전처리를 재사용하고, 구름·빙정·눈은 RRTMGP 전용 입력 함수에서 준비합니다. 양의 구름분율에서는 수상별 질량을 보존합니다. WRF가 분율을 0으로 진단한 층은 명시적으로 청천 처리하며 제외 질량을 진단합니다. 장파와 단파는 함께 37로 선택하고 에어로졸·화학 피드백은 거부합니다.

WRF 복사 호출은 계속 `ncol=1`입니다. PR33은 부모 보간 초기 상태를 쓰는 제한된 nested runtime smoke이며 고해상도 자식 입력이나 예보 skill을 검증하지 않습니다. 생산 경로의 다중 기둥 packing/batching과 해당 full CMake/CI 통합은 후속 작업입니다. 관측 점 복사 비교는 PR34의 두 관측소, 하루 범위로 제한됩니다.

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
