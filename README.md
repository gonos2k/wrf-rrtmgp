# WRF–RRTMGP 37

검증 기준선은 [PR #203 병합 main](https://github.com/gonos2k/wrf-rrtmgp/commit/d2223f13c28f06d9886f5d5febaeb2ad18b3a5a0)이다. **아래 고정 직렬 연구 구성의 공학적 포팅은 1차 완료이며, Sterling 오후 구름 지속성과 전천 단파일사 예측의 정량적 적용성은 미승인이다.**

| 현재 범위 | 완료 근거 또는 남은 판단 |
|---|---|
| 검증한 설정 | UDM27/LW37/SW37, 단일 specified 영역·serial·one tile, number1/population0, scalar_adv_opt0, capacity0/liquid-size0, experimental frozen1, dt60s/rad600s |
| 경계·number·재시작 | [지정경계 계약](WRF/test/rrtmgp/UDM_SPECIFIED_NUMBER.md), [원래 675쌍 재시작 수정](validation/rrtmgp37/restart-first-step/README.md), [수정 cold와 checkpoint 450쌍](validation/rrtmgp37/vapor-first-operation/README.md) |
| 수치 상태·강수·복사 전달 | [KF Eta 강수율 수명](validation/rrtmgp37/kfeta-precipitation-lifetime/README.md), [최종 음수 수증기 해소](validation/rrtmgp37/vapor-first-operation/README.md), [SW 호출·반환·held source 마감](validation/rrtmgp37/native-sw-phase-closeout/README.md) |
| 실제 예보·관측·구름 소실 | [내부영역 24시간 및 SOLRAD 평가](validation/rrtmgp37/sterling-interior-day-evaluation/README.md), [PBL 재분배·수송·후속 증발 귀속과 1,800쌍 대조](validation/rrtmgp37/sterling-cloud-loss-operation/README.md) |
| 독립 대기관측 | [실제 발사시각의 radiosonde·METAR 대조](validation/rrtmgp37/sterling-independent-atmosphere/README.md): 저층 온도·습도·역전 구조의 불일치, PBL 단독 계수 오류는 미확정 |
| 입력 계보·저층 상태 | [기존 입력과 시간별 온습도 구조 대조 완료](validation/rrtmgp37/sterling-low-level-evolution/README.md): 실제 발사에 가까운11·23시 및13–16시 보완, 초기·경계와 예보 발달 연결 |
| 층별 실제 경향 | [12–17 UTC native5–12층의 온도·수증기 연산 귀속](validation/rrtmgp37/sterling-thermodynamic-tendencies/README.md): 12시 기존 오차 보존, 6층 물리 냉각과7–8층 수송 온난·건조화 구분, cold와1,350쌍 동일 |
| 남은 과학적 판단 | [원래 일곱 종료 조건](validation/rrtmgp37/research-policy-contract/closure-conditions.json) 유지: population/PSD/발생분율, frozen 물성·밀도 계약, RFMIP/LBLRTM 참조, 전체 물·에너지, 용도별 독립 예보 정확도 |
| 다음 작업 | native7–8층 수직수송과 인접 온위·수증기 기울기, 좌표 정의에 맞는 수직운동 상태를 기존 구동·독립 대기 근거와 대조. 12시 기존 상태 오차와 원 점수는 보존하며 PBL·광학 계수는 조정하지 않음 |

이 범위는 Gamma8·capacity1의 warm-periodic 연구 옵션이나 일반 MPI/OpenMP·둥지·운영 예보 승인으로 확대하지 않는다. [PR166의 15/22 역사 장부](validation/rrtmgp37/acceptance/review-resolution-checklist.json)는 당시 snapshot을 보존한 기록이며 현재 전체 완료율이 아니다. 아래 설명의 PR20 등 이전 실행은 각 당시 구성의 근거로 읽는다.

현재 37번 개발·평가 범위는 **UDM(`mp_physics=27`) 전용**입니다. 장·단파 `37/37`, `use_mp_re=1`을 요구합니다. UDM native radii, qc/qi cloud optics, qr/qs precipitation optics를 연결하며 기본 frozen0에서는 qg를 제외량 계측, 양의 qh를 명시적 미지원으로 처리합니다. [현재 UDM 입력 계약과 검증 한계](WRF/doc/rrtmgp/UDM_ONLY.md) · [UDM 실행·비교 검증 기록](validation/rrtmgp37/udm-only/REPORT_ko.md)를 먼저 확인하십시오. 아래 다른 미세물리 결과는 이전 버전의 검증 기록입니다.

싸락눈·우박에는 [동질 얼음 PSD 수치 기준](validation/rrtmgp37/frozen-optics-reference/README.md)과 [명시적 실험 모드](WRF/doc/rrtmgp/UDM_FROZEN_EXPERIMENT.md)를 연결했습니다. 기본 모드의 qg 제외·양의 qh 거부는 유지합니다. 실험 모드 1의 PR20 실행파일은 실제 자료로 MPI 4개 rank에서 24시간을 완료했으며, 12시간 체크포인트에서 재시작한 13시간 출력의 모든 수치 배열이 연속 적분과 일치했습니다. 메타데이터 `START_DATE` 차이는 별도로 기록합니다. [실행·비교 근거](validation/rrtmgp37/realdata-parallel/README.md)는 수치 실행 검증이며, 젖은 얼음 입자·관측 정확도 또는 PR21 코드의 24시간 검증을 뜻하지 않습니다.

[오프라인 조회·보간 검사](validation/rrtmgp37/frozen-optics-lookup/README.md)는 외삽 거부, 단위·질량 계약과 크기 격자 세밀화 결과를 기록합니다. 9개 크기 노드의 시험 중간점에서 최대 차이는 소광 정규화 기준 약 0.440%이며, 전체 오차 상한이나 예보 정확도를 의미하지 않습니다.
기체 광학의 건조공기량도 WRF native 층 질량에서 변환하도록 보완했습니다. [native gas-column 계약](WRF/doc/rrtmgp/NATIVE_GAS_COLUMNS.md)과 실행 근거에서 적용 범위를 확인하십시오.



공식 WRF v4.8.0의 장파·단파 복사 옵션 `37/37`에 RTE+RRTMGP CPU 계산을 연결하는 개발 저장소입니다.

## 현재 상태

기본값 OFF인 `rrtmgp_capacity_policy=1`과 `rrtmgp_liquid_size_policy=1`로 native constant-κ 복사열용량과 최종 Gamma8 액체 광학크기를 각각 선택할 수 있습니다. 단일 주기영역·serial·all-warm 연구 범위와 파일/restart 식별 규약은 [연구용 복사 옵션](WRF/doc/rrtmgp/RESEARCH_RADIATION_OPTIONS.md)에 명시합니다. [통합 실행 근거](validation/rrtmgp37/research-radiation-integration/README_ko.md)는 동일 양의 구름 입력의 네 조합과 복사 호출 사이 checkpoint를 다룹니다. 물리적 생산 승인은 별도입니다.

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

### Frozen-optics temperature coverage

PR #65의 오류 로그 수정은 CI 8개 작업을 통과했습니다. 로컬 복사 기반 증분 WRF 빌드와 MPI4/OpenMP2 중단 재현에서 기존 표의 180 K 하한 초과가 실제로 기록됐습니다. [확장 Planck 온도표 검증](validation/rrtmgp37/frozen-planck-coverage/README.md)은 150–330 K의 수치 조회 범위, 기존 지점 값 보존, 중간 온도 직접 계산 비교와 Python–Fortran 일치를 제공합니다. 새 표는 명시적으로 선택하는 실험 자료이며, 현재 자료에는 완료된 Matthew 48시간 RA37 비교나 관측 정확도 판정이 없습니다.
