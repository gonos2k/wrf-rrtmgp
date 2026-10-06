# UDM27 → RRTMGP37 입력 계약

개발·평가 범위는 `mp_physics=27`, `ra_lw_physics=37`, `ra_sw_physics=37`, `use_mp_re=1` 조합이다. 다른 미세물리 및 4/37 또는 37/4 혼합 복사를 초기화에서 거부한다. 기존 4/4는 기존 UDM 반경 제공 플래그를 유지한다.

## 공개 소스와 수정

UDM 기준은 공개 WRF `06d4240ae989cc3e50af412bb472df3d9048783c`의 `phys/module_mp_udm.F`이다. 원본 파일 SHA256은 `c76e37d6ad81dd0fd86064857fc8a352bc9075b1370262713a6b4abb53ef50b4`이다. NOAA 내부 production 코드와 동일하다는 뜻은 아니다. 이식본은 반경 계산 직전 `den1d(k)=den(i,k,j)`를 추가한다. 원본에서는 이 배열을 초기화하지 않고 `udm_mp_effective_radius`에 전달했다.

실제 outer `udm`와 초기화 함수를 사용하는 독립 시험은 signaling-NaN 초기화와 bounds/FPE 검사를 켠다. 밀도 복사 한 줄만 제거한 대조 소스는 반경 계산에서 실패해야 한다. 실제 UDM·radar 소스를 컴파일하며 테스트 환경의 로그 함수만 대체한다.

## 수상체 매핑

| UDM 변수 | 복사 경로 | 크기 |
|---|---|---|
| qc | liquid cloud LUT | UDM re_cloud (µm 반경) |
| qi | ice cloud LUT | UDM re_ice → 2×반경 유효직경; ice LUT 범위 제한 |
| qr | pinned CCPP rain precipitation optics | 질량 경로, 별도 반경 불필요 |
| qs | pinned CCPP snow precipitation optics | UDM re_snow (µm 반경), ice LUT로 보내지 않음 |
| qg | grid 질량 및 제외량 진단 | 광학 미지원, snow에 합치지 않음 |
| qh | 양의 질량이면 WRF fatal | 광학 미지원; 근거 없는 허용 하한 없음 |
| qnc/qnr/qnn | UDM 미세물리 내부 | qnc는 native liquid radius 계산에 사용 |

`rrtmgp_build_udm_inputs`의 6개 phase 열은 L/I/R/S/G/H 순서다. production 37은 native 건조층 질량으로 `WP_grid=q×Mdry×1000` (g/m²), `cf>0`에서 `WP_in=WP_grid/cf`를 계산한다. `Mdry=-DNW×(C1H×MUT+C2H)/g`이며 moisture-loaded `P8W` 차분을 질량분모로 쓰지 않는다. 직접 historical builder 호출의 배열 생략만 과거 `Δp/g` 근사를 유지한다. [분모·전달·독립 검사](NATIVE_DRY_MASS.md)를 따른다. 크기와 질량을 RRTMG의 0.99 계수, 130 µm 제한, Fu 크기 배율로 다시 보정하지 않는다. builder는 qg의 준비 경로도 계산하지만 production wrapper가 실제 `GWP_RADIATION=0` 및 `GWP_OMITTED=GWP_GRID`로 기록한다.

음수 입력은 [UDM process-scale 계약](NEGATIVE_INPUT_CONTRACT.md)에 따라 37번의 복사 입력 복사본에서만 제한적으로 0으로 보정한다. 원래 음수값과 phase별 수분경로 보정량을 보존하며 상한 이상의 음수와 모든 양의 hail은 계속 거부한다. 이는 부동소수점 오차가 입증됐다는 의미가 아니다.

유효반경 플래그는 UDM+37/37에서만 활성화된다. UDM 첫 미세물리 호출 후에는 native radii를 전달한다. 첫 복사 호출이 미세물리보다 먼저 실행되어 wet/cloudy 입력이 정확히 `RE_*_BG`인 경우에만 기존 초기 host 반경 보완을 허용한다. 이는 startup 예외이며 다른 미세물리 반경 mapping을 지원한다는 뜻이 아니다. UDM 최소값 2.51/5.01/25 µm는 WRF 배경값 2.49/4.99/9.99 µm와 다르다.

## 강수 광학의 출처와 합성

공개 NCAR/ccpp-physics 커밋 `3e6660c6df54e95a0871e990c2294dd397ae3860`의 `physics/Radiation/RRTMGP/rrtmgp_{lw,sw}_main.F90` 및 cloud-optics 계수를 사용한다. LW 16 / SW 14 밴드의 순서와 파수 경계를 정확히 검사한다. CCPP suite 전체 또는 NOAA 내부 UDM adapter를 재현했다고 해석하지 않는다.

LW는 rain `0.33e-3 × RWP`, snow `1.5 × 1.05756 × SWP / r_s` 광학두께를 합한다. SW는 원본 rain/snow 밴드 계수로 τ, τω, τωg를 합한 뒤 원본 delta scaling을 한 번 적용한다. cloud LUT 출력에도 delta scaling을 한 번 적용하고, 두 성분을 RRTMGP의 optical-properties `increment`로 합성한 뒤 동일 McICA mask로 표본화한다. 이미 delta-scaled precipitation을 다시 delta-scale하지 않는다. snow 식의 원본 `r_s>10 µm` 조건은 UDM의 25–999 µm 유효 범위에서 만족한다.

이 구현은 WRF의 기존 CLDFRA를 cloud와 rain/snow occurrence fraction에 함께 사용한다. CCPP의 cloud-fraction cutoff를 이식해 질량을 제거하거나 임의의 cf 하한을 도입하지 않는다. `cf=0`에서 수상체가 남는 WRF 예외는 optical path 0으로 처리하고 L/I/R/S별 제외 grid 질량을 기록한다. 이 제외가 복사적으로 무시 가능하다고 검증한 것은 아니다. qg 제외량과 LW/SW 중복 진단은 별도로 해석해야 한다.

UDM 내부 `cldf_diag`의 마지막 실제 분율과 source step을 37 전용 진단 상태로 export한다. radiation의 기존 CLDFRA는 그대로 사용하며 현재 상태의 재계산 분율도 별도로 계측한다. 같은 상태의 4/37 표본 평균, 분율·광학 합성 대조 실험은 [PHYSICS_AUDIT.md](PHYSICS_AUDIT.md)를 따른다. 장시간 비교 없이 분율 기본값을 바꾸지 않는다. 이 두 분율의 일치, rain/snow precipitation fraction, 시간 고정 McICA seed는 후속 물리 검증 대상이다.

## 저장 및 재생

production UDM capture는 `RRTMGP_REPLAY_V4`이다. 기존 ICE_ROUGHNESS 및 SW_BAND_PARTITION 뒤에 `PRECIPITATION_OPTICS=1`, `RWP(ncol,nlay)` (in-cloud g/m²)를 기록한다. `.raw`는 qc/qr/qi/qs/qg/qh, 밀도, native source radii와 L/I/R/S/G/H의 GRID/RADIATION/OMITTED 경로를 보존한다. `.result`의 PRECIP_TAU 및 SW PRECIP_SSA/G는 별도 성분이며 CLOUD/PREPARED는 합성 광학량이다. V4 `DS_USED`는 snow 반경 µm로 해석한다; 구형 V1–V3의 DS_USED 직경 의미와 다르다.

standalone reference는 production input-builder와 adapter를 호출하지 않고 저장된 물리 입력으로 gas/cloud optics, precipitation 식, mask, RTE를 계산한다. 강수 식은 같은 고정 공개 식을 독립적으로 작성한 것이므로 이것은 포팅·합성의 검증이며, 식 자체의 관측 정확도를 검증하지 않는다. V1–V3의 historical replay 및 standalone backend fixtures는 기존 의미를 유지하며 production 미세물리 지원 범위와 구분한다.

## 검증 명령과 한계

```bash
cmake -S WRF/test/rrtmgp -B build/udm-columns
cmake --build build/udm-columns --parallel 2
ctest --test-dir build/udm-columns --output-on-failure
python3 WRF/test/rrtmgp/test_udm_scm.py build/udm-scm --reference-executable build/udm-columns/reference_column
```

수상별 질량/반경 계약, 실제 outer UDM 밀도 회귀, rain/snow 광학 및 actual-column replay를 검증한다. 수정 전 4/4 결과와 bitwise 비교하려면 동일 초기 입력을 가진 실제 baseline 실행 디렉터리를 제공해야 한다. 같은 새 실행 파일의 반복 실행만으로 수정 전 보존을 주장하지 않는다.

짧은 SCM, 자체 flux/energy 계약 및 독립 replay는 예보 정확도나 NOAA 운영 동등성 증거가 아니다. 이전 기본 mode-0 37번 장기 시도는 strict-negative QI 입력에서 중단된 기록으로 보존한다. 이후 #26은 UDM의 SR 행 전달 문제를 수정했고, #31은 그 소스 기준으로 RA4 legacy/RA37 mode-1 24시간 비교 및 자기 arm별 재시작 연속성을 통과했다. 이전 4/4 비교는 SR 행 전달 수정 전 결과이므로 corrected 비교와 구분한다. 두 기록을 같은 실패 원인의 설명으로 합치지 않는다.

기본 `rrtmgp_udm_frozen_optics=0` 계약은 그대로다: qg는 복사에서 제외량을 계측하고 양의 qh는 거부한다. 명시 실험값 `=1`은 동질 얼음 구형 G/H 모델을 선택하며 기본 지원 정책이나 NOAA 물리 parity가 아니다. PR20은 MPI4 mode-1 24시간 실행을 기록한다. PR31의 corrected pair는 RA37만 mode 1이며 RA4는 legacy 4/4다. 두 결과는 해당 mode-1 runtime evidence이며 default mode-0 qh 지원을 검증하지 않는다. PR31 자기 arm 12시 체크포인트 재시작은 같은 arm 연속 13시 배열과 수치 단위로 일치했으며 `START_DATE` 메타데이터 차이는 남아 있다.

현재 공개 후속 증거의 범위는 각 PR head와 artifact에 연결해 읽는다. PR30(`bb56ec0ad5a0fbd2ef2027a291554fc40d6c7291`)은 GNU workspace의 동일 MPI/OMP 배치 parity를 보였지만 MPI 분해 간 동등성을 뜻하지 않는다. PR27(`f7f0ad164b50684bb170b729f0836c0e8404a8e0`)은 pristine WRF의 bounded 한 스텝 분해 차이(63/202 변수, 원인 미확정)를 따로 기록한다. PR33(`0f1ae2967281df3cfa4d8ec5c0f6764fe025158d`)은 부모 보간 초기장을 사용한 제한적 nested smoke다. PR34(`958cf46b074b3927e9ca939ad9d7c371ac11e17b`)는 FPK/DRA 두 관측점의 하루 복사 비교로 지표별 결과가 섞여 있으며 cloud field나 예보 정확도를 평가하지 않는다. PR35(`7ea36677ae085e8edc61b9161c075bdeda8441d2`)는 Intel serial 1분 smoke로, 이 실행에서 512 MiB master stack은 실패하고 1 GiB는 통과했다; 보편 stack 요구량이 아니다. 이 인용은 각 검증 revision을 식별하며 현재 main의 병합 상태를 단정하지 않는다.

남은 검증은 다중일 예보·예보 skill, cross-layout MPI 원인과 동등성, 고해상도 child/중첩 restart, 실험 G/H 광학의 관측 물리 타당성, 다중 기둥 production packing/batching 및 그 전체 CMake/CI 통합이다. UDM 내부 cloud-fraction 장기 통계도 제한된 진단 자료를 넘어 평가하지 않았다. [native 수상체 진단](NATIVE_HYDRO_DIAGNOSTICS.md), [OpenMP/MPI 근거](CPU_OPENMP.md), [실험 광학 설명](UDM_FROZEN_EXPERIMENT.md) 및 해당 PR의 범위를 함께 확인한다.

## Opt-in frozen precipitation experiment

The default contract above still omits graupel with diagnostics and rejects
positive hail. `rrtmgp_udm_frozen_optics=1` selects a separate homogeneous-ice
sphere exponential-PSD table for G/H with uniform occurrence=1, preserving
positive grid paths without a cloud-fraction divisor. This is an explicit
research configuration; see [UDM_FROZEN_EXPERIMENT.md](UDM_FROZEN_EXPERIMENT.md)
for table identity, size reconstruction, optics and replay contracts.
Default mode and RRTMG4 behavior are preserved and tested separately.

PR20's explicit mode-1 executable completed a four-rank 24-hour real-data
trial with positive graupel and hail. PR31 later records a corrected paired
24-hour run based on PR26's SR-row source and same-executable own-arm restart
continuity. The earlier strict-negative mode-0 QI failure and the pre-SR-fix
coupled comparison remain separate historical records; neither should be
used as the current mode-1 result or as proof that the other failure caused
it. These runs do not establish observational accuracy, default mode-0 hail
support, or long-term G/H optical fidelity. See the [actual-domain receipts](../../../validation/rrtmgp37/realdata-parallel/README.md) and the open [PR31 evidence](https://github.com/gonos2k/wrf-rrtmgp/pull/31) at head `360cbf6668c84ef7d00c163fdce0d8dd54daca44`.
