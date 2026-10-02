# WRF 37 光学 구성과 고정 UFS/CCPP 비교

기준은 PR #4를 병합한 `4f7d006e5f378ac8f151c5318172d84ef23c5e5a`이다. 이전 `c705c44` 검토 이후 small-cf 2,048-seed 시험, 실제 WRF 컬럼 replay, 미세물리 분류 계약과 4/4–37/37 동일 초기 상태 비교가 이미 추가됐다. [기존 RRTMG 비교 결과](../../../validation/rrtmgp37/rrtmg-comparison/REPORT_ko.md)는 7조건·14회 GNU serial 5분 SCM 결과이며 관측 정확도 평가가 아니다.

## 출처를 고정한 비교

UFSATM commit `6f461419f091c109d18b826ab88595da00ab336c`은 CCPP `3e6660c6df54e95a0871e990c2294dd397ae3860`, RTE-RRTMGP `41c5fcd950fed09b8afe186dede266824eca7fd3`를 사용한다. RTE 핀은 현재 WRF 포팅과 같다. 아래의 UFS 선택을 모든 NOAA suite의 선택으로 일반화하지 않는다.

| 항목 | WRF 37 | 고정 UFS/CCPP 경로 |
| --- | --- | --- |
| Ice roughness | 명시 namelist 1/2/3; 기본 1로 기존 결과 보존 | `rrtmgp_nrghice=3` 기본, LUT에 실제 전달 |
| Cloud ice | ice 유효직경 LUT | cloud ice LUT, 별도 roughness 선택 |
| Snow | 현재 ice LUT에 별도 SWP와 `2*r_s` 입력 | Fu 계열 별도 강수 광학식 |
| Rain/graupel | 별도 rain/graupel 광학 입력 없음 | rain/snow+graupel 광학 경로 |
| 강수 발생 분율 | snow를 cloud fraction과 같은 McICA mask로 표본화 | `precip_frac` 인자는 있으나 이 고정 main 식은 cloud fraction으로 gate |

1=none/smooth, 2=medium, 3=high이다. UFS host 기본 3은 [GFS_typedefs.F90](https://github.com/NOAA-EMC/ufsatm/blob/6f461419f091c109d18b826ab88595da00ab336c/ccpp/data/GFS_typedefs.F90#L3659)에 있다. SW/LW의 선택 전달은 [SW cloud loader](https://github.com/NCAR/ccpp-physics/blob/3e6660c6df54e95a0871e990c2294dd397ae3860/physics/Radiation/RRTMGP/rrtmgp_sw_cloud_optics.F90#L241), [LW cloud loader](https://github.com/NCAR/ccpp-physics/blob/3e6660c6df54e95a0871e990c2294dd397ae3860/physics/Radiation/RRTMGP/rrtmgp_lw_cloud_optics.F90)에 구현돼 있다. 기본 2를 “NOAA와 일치”라고 부르면 안 된다.

새 WRF 설정은 전역이며 초기화 후 변경하면 fatal이다. LUT load 뒤 LW/SW 모두 `set_ice_roughness`를 명시 호출한다. 새 V2 replay 파일에도 선택을 기록하고 독립 reference에 전달한다. 기존 V1 replay는 당시 category 1로 재생한다. 1/2/3 민감도는 유한성, 청천 불변성 및 cloudy flux/heating 변화를 검증하며 어느 category가 관측에 더 정확한지 판정하지 않는다.

## Snow 식과 이식 계약

[고정 SW main](https://github.com/NCAR/ccpp-physics/blob/3e6660c6df54e95a0871e990c2294dd397ae3860/physics/Radiation/RRTMGP/rrtmgp_sw_main.F90#L445)에서 SWP>0이고 snow radius>10 μm일 때

`tau_snow = SWP * 1.09087 * (a0s + a1s/(1.0315*r_s))`, `a0s=0`, `a1s=1.5`.

SW 14개 밴드에서 `b0s=.460`(밴드 1–8, 이후 0), `b1s=1.62e-5`(밴드 9–10, 나머지 0), `c0s=.970`(밴드 1–10) 또는 `.700`(밴드 11–14)이다. `ssa_snow*tau_snow = tau_snow*(1-(b0s+b1s*1.0315*r_s))`이고 `g*ssa*tau`에는 `c0s`를 곱한다. Rain과 cloud 성분을 τ, ωτ, gωτ로 합산하고 delta scaling한다. [계수 출처](https://github.com/NCAR/ccpp-physics/blob/3e6660c6df54e95a0871e990c2294dd397ae3860/physics/Radiation/RRTMGP/rrtmgp_sw_cloud_optics.F90#L252).

[고정 LW main](https://github.com/NCAR/ccpp-physics/blob/3e6660c6df54e95a0871e990c2294dd397ae3860/physics/Radiation/RRTMGP/rrtmgp_lw_main.F90#L399)의 snow 흡수 τ는 같은 활성 조건에서 `1.5 * 1.05756 * SWP/r_s`이며 모든 LW 밴드에 더한다. Rain은 SW `3.07e-3*RWP`, LW `.33e-3*RWP`다. Snow/graupel은 이 경로에서 같은 식을 공유한다.

이 공식의 경로 단위는 g/m², 반경은 μm다. 그러나 WRF의 snow radius와 Fu 정의, grid/in-cloud 경로와 발생 분율, 10 μm threshold 및 14-band 순서는 각각 확인해야 한다. 현재 WRF builder는 양의 cf에서 SWP를 cf로 나눈다. 고정 CCPP main의 강수 식에는 이 나눗셈이 없으며 상류 host 처리까지 함께 비교해야 한다. 계수식을 그대로 교체해도 NOAA 결과 재현을 증명하지 못한다. 이번 변경에서 기존 snow 광학은 유지하고 위 소스·계수·계약을 다음 이식의 기준으로 고정한다. 새 경험계수는 만들지 않는다. 재사용 시 CCPP Apache-2.0 출처·저작권을 보존해야 한다.

## 희박한 cf와 transparent layer의 해석

`P(no cloudy g-point)≈(1-cf)^Ng`는 독립 Bernoulli 표본의 근사다. 기존 2,048-seed 결과는 cf=.001에서 SW 89.70%, LW 88.28%의 clear samples를 보였고, cf>=.001의 평균은 두 상태 ICA 기대값과 허용 범위 안에서 일치했다. cf=1e-6의 0회 표본은 수렴을 입증하지 않는다. 작은 cf에서 미표본 확률이 크다는 사실 자체를 복사 평균의 편향이나 큰 예보 오차로 동일시하지 않는다. 가중 ICA 복사 영향, 분산 및 고정 시드의 시간 상관을 함께 평가해야 한다. 새 cf floor는 도입하지 않는다.

Maximum-random은 현재 cloud fraction으로 cloudy-layer 연속성을 정한다. [cf=.5,0,.5]와 [.5,.5,.5]에서 중간 광학 경로가 모두 0인 시험을 추가해, 외곽 두 층의 동시 cloudy 비율이 각각 약 .25와 .5임을 확인한다. 이것은 CF-only 계약을 수치로 드러내는 시험이다. Zero optical path를 반드시 clear gap으로 바꿔야 한다는 물리 결론은 아직 내리지 않는다. Host cloud fraction의 의미와 응축수 cutoff를 확인한 뒤 별도 정책 변경으로 다룬다.

## 남은 범위

WRF/RRTMGP의 g/cp/분자량 통일, phase별 cf=0 제외량과 LUT clipping 질량가중 통계, 음수 수상체의 장시간 분포, snow 강수 광학 이식·검증, delta-scaled direct와 DNI의 구분은 남아 있다. 기존 독립 replay는 연결/변환 검증이며 독립 분광 기준 정확도 검증을 대신하지 않는다. WRF ncol=1, MPI/OpenMP/restart/nest 및 24–48 h 실예보 검증도 남아 있다.

새 `compare_snow_optics` 실행 파일은 cf=1, SWP=50 g/m²에서 입력 반경 10/30/60/130 μm, roughness 1/2/3을 비교한다. 방정식은 wp 배정도로 계산하며 CCPP의 default-real literal 반올림을 비트 단위로 재현하는 시험은 아니다. LW SSA/g의 CSV NaN은 흡수 전용 API에 해당 값이 없다는 표기이며 플럭스 비유한값을 뜻하지 않는다.

## 재현 명령

```bash
cmake -S WRF/test/rrtmgp -B build/optics-test -DRRTMGP_DATA_DIR="$PWD/WRF/run"
cmake --build build/optics-test -j 8
ctest --test-dir build/optics-test --output-on-failure
build/optics-test/compare_snow_optics WRF/run > build/optics-test/snow-optics-source-comparison.csv
python WRF/test/rrtmgp/plot_optics_comparison.py build/optics-test
python WRF/test/rrtmgp/test_make_reproducibility.py --netcdf-prefix "$NETCDF" \
  --output-dir build/make-reproducibility
```

플롯 명령은 CTest가 만든 category별 CSV와 snow 비교 CSV를 읽는다. 실제 WRF replay는 `test_column_replay.py NEW_CASE_DIR REFERENCE_EXE --cloud-fixture --ice-roughness 2` 또는 `3`으로 실행한다. GNU/NetCDF 실행 라이브러리 경로는 사용 환경에 맞춰 지정한다.

Make wrapper는 compiler/version, FCFLAGS, include/NetCDF 경로, kernel 및 명시 object 목록이 달라지면 자신이 소유한 생성 파일을 무효화한다. 같은 설정의 반복 호출은 재컴파일하지 않는다. `libwrf.a`에 추가하는 목록은 `print-wrf-objects`의 명시 25개 객체이며 unrelated `*.o`를 포함하지 않는다. 단일 make의 `-j` 병렬 빌드를 검사했다. 서로 다른 설정을 같은 build directory에서 동시에 빌드하는 것은 지원하지 않는다. WRF 전체 Registry 변경에는 생성 모듈을 정리한 표준 전체 재빌드가 필요하다.
