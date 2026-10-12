# #168 누락 빙정만의 고정 상태 복사 영향

**PASS_SCOPED_OMITTED_ICE_SENSITIVITY**. #168의 실제 60초 기주 입력을 공통 CF·기존 다른 수상체의 질량/반경/mask·기체·온도·지표·태양조건을 그대로 두고 계산했습니다. 기존 공개 `rrtmgp_lw_column` / `rrtmgp_sw_column`을 사용하는 isolated diagnostic build입니다. 누락 빙정의 grid path만 occurrence=1인 별도 광학 성분으로 추가합니다. 생산 WRF/UDM/RTE·Registry·초기화·계수·허용오차는 변경하지 않았습니다.

기준 main: `36301782b2372b28f942920d5ab7997801b16e3a`, tree: `0dc41a63e89c8ed77d405aee0805a414474161a4`. 원시 input/반경은 #168의 조건 그대로이며 입자 정의의 물리적 승인이 아닙니다. 이미 완료한 #168 상태/경로 관측을 다시 새로운 미완료 조건으로 만들지 않았습니다.

## 결과와 정책 판단

최종 네 기주에서 LW는 원 seed와 +1/+2의 3쌍, SW는 그 3쌍과 hash로 넓게 분산한 32개 추가 stream, 총 **기주당 35쌍**입니다. 같은 쌍의 Z/B는 같은 seed/mask를 사용합니다. 공간 기주 4개는 같은 제조 SCM 사례의 작은 표본입니다.

| 조건부 차이 | LW | SW |
|---|---:|---:|
| 최대 native 층 가열률 절대차, K/day | **0.1085023695** | **0.01170304264** |
| 최대 층 경계 플럭스 절대차, W/m² | **0.3684560284** | **0.09742455996** |
| Solver TOA 상향 플럭스 차이 범위, W/m² | −0.009874013 ∼ −0.009873137 | +0.007921930 ∼ +0.015019114 |
| 지표 하향 solver flux 차이, W/m² | 0 ∼ +4.956901×10⁻⁷ | −0.009326254 ∼ −0.0005007245 |
| WRF convention으로 재구성한 지표 SWDOWN 차이, W/m² | 해당 없음 | **−0.005939444 ∼ −0.0005007245** |

최대 가열률 차이는 두 phase 모두 native layer 53입니다. 원 seed에서 첫 기주의 signed 차이는 LW +0.1084949284 K/day, SW +0.01169813352 K/day입니다. LW model 위 padding을 포함한 backend는 103층, SW는 60층이며 native는 59층입니다. Solver TOA와 native model-top interface를 결과 JSON에 따로 기록했습니다.

**정책 판단:** 작은 0.0905% ice-path 비율을 근거로 omission이 복사에 무시 가능하다고 승인하는 해석을 기각합니다. 이 상태에서 내부 가열률 영향은 직접 계산으로 확인됐습니다. 그러나 occurrence=1이 물리적 정답이라는 결론은 내리지 않습니다. 기존 CF0 omission과 uniform-ice 가설을 다음 독립 발생분율·광학/관측 판단의 두 조건으로 유지합니다. 단일 비산란 흡수층의 상한을 이 다층 SW/LW 결과의 일반 상한으로 전용하지 않습니다.

## Sampling과 정밀도 불확실성

SW의 지표 solver-down paired difference 평균은 기주별 약 −0.0005245∼−0.0009092 W/m²이고 sample std는 약 0.0001276∼0.0015819 W/m²입니다. 모든 쌍은 음의 차이였지만, 이 매우 작은 지표값의 정밀한 평균은 seed에 민감합니다. 반면 최대 층 가열률 영향은 약 0.0117 K/day로 유지됩니다. 세밀한 지표 평균이 수렴했다고 선언하지 않습니다.

`result.json`의 기주별 mean/std/range/standard-error 진단을 함께 보십시오. 35개의 distinct RNG seed를 사용했으며, theoretical independence를 증명하지 않았습니다. 표준오차 수치는 독립 표본을 가정한 경험적 진단이고 formal confidence interval은 주장하지 않습니다. 이 finite-seed 범위는 전체 모델·다른 발생분율·다른 PSD의 오차 상한이 아닙니다. 반경·PSD·계수·관측 불확실성은 아직 정량화하지 않았습니다.

공개 column의 native REAL32 출력과 별도로 동일 solver의 WP64 up/down/heating을 기록했습니다. 작은 지표 LW 차이가 native 출력에서 0으로 반올림되는 경우와 내부값을 구분합니다. Flux 차이로 다시 구성한 heating 차이의 최대 잔차는 약 7.8×10⁻¹⁴ K/day입니다. 이는 같은 solver의 에너지 산술 연결이며 독립적인 정확도 승인이 아닙니다.

## A / Z / B 실험 분리

- A: 수정하지 않은 production adapter의 독립 column executable. 원 seed의 여덟 기주/phase에서 #168과 공통 모든 기록이 **비트 일치**했습니다.
- Z: 진단 executable, 동일 sidecar를 읽되 ice path scale=0. A의 모든 원 기록과 비트 일치했습니다.
- B: 같은 진단 executable, 누락 ice path scale=1. CF와 기존 component/mask는 Z와 동일합니다. 새로운 ice raw band optics를 구하고 기존 sampling 이후 occurrence-one로 더합니다.

LW는 별도 scalar ice opacity를 그대로 추가합니다. SW는 새 ice의 raw τ, τω, τωg를 기록하고 **그 새 성분만 한 번 delta scale**한 뒤 기존 gas+sampled-cloud/precip mixture에 더합니다. 기존 이미 scaling된 광학량을 다시 scaling하지 않습니다. Band→g-point τ 및 scattering/asymmetry moment 합성 폐합을 검사했습니다. 기존 masks·cloud/prepared/precip optics·radii·clear-sky flux는 변하지 않습니다.

SW의 native diagnostics에는 비축소 raw extinction 직달 경로가 별도로 있습니다. 새 ice raw opacity를 그 경로의 masked/unmasked 두 분기에 모두 occurrence-one로 포함했습니다. 따라서 ΔSWDOWN은 새 raw-direct difference + 새 diffuse difference로 재구성하고, RTE의 delta-scaled down flux와 구분합니다. 이는 고정 상태의 현재 WRF output convention 재구성이며 새로운 WRF/LSM 실행은 아닙니다. `ICE_DIAG_PREDELTA64` / `ICE_DIAG_DIRECT64`가 실제 구현 기록입니다.

Seed variant의 prepared input은 header seed를 변경하고 public driver가 필요한 state 인자만 읽습니다. 캡처에 있던 cached SW direct/mask 자료는 driver의 입력 인자가 아니며 사용하지 않습니다. 각 실행의 normalized `.input`에는 production column이 해당 seed로 다시 만든 실제 mask가 기록돼 있고 Z/B bytes가 같습니다. 이 prepared file을 다른 generic replay reader가 그대로 소비했다고 주장하지 않습니다.

## 실행·실패를 구분한 기록

전체 standalone Fortran process는 **393회**입니다. 392회 RC0; 1회는 진단 runner가 만든 INTEGER seed overflow로 input parse 중 RC2였고 public column에 도달하지 않았습니다. 이를 제외한 final evidence는 **312 public-column process**입니다. 이전 개발 계산 80회는 prototype/precision/direct-path 정리 단계이며 final 통계에 합산하지 않습니다. WRF·ideal·LBLRTM·LNFL 새 실행은 0회입니다. RTE는 public column 안의 clear/all-sky 계산으로 실제 실행했습니다.

처음 component build는 `.F` free-form 옵션 누락으로 RC2였습니다. GNU `-ffree-form`을 명시하고 수정한 뒤 baseline/diagnostic, WP64 records, raw-direct linkage의 세 build command가 RC0였습니다. 최초 오류 로그와 두 configure 성공도 보존했습니다. 이런 진단 준비 오류를 생산 코드 결함으로 등록하지 않습니다.

세 seed의 최초 WP64 계산은 새 ice의 raw-direct linkage를 포함하지 않았으므로 최종 SWDOWN 근거에서 제외했습니다. 이후 올바른 최종 source로 재계산했습니다. 추가 hash-seed 실행의 input overflow는 bounded seed mapping으로 수정했습니다. 이미 성공한 66쌍을 재사용하고 미완료 62쌍만 실행했습니다. 모든 actual subprocess journal의 RC와 counts는 `saved/process-accounting.json`에 그대로 있습니다.

## 저장 자료와 CI 재생

`runtime-index.json` + `runtime-blobs.tar.gz`는 원시 capture를 **전체 bytes 그대로 재구성**합니다. 중복 record를 제거해 저장량만 줄였으며 numerical values를 변환·양자화하지 않았습니다. 재구성 파일마다 원 전체 SHA/length를 검사합니다. 원 capture 1,458개 파일의 exact chunks가 약 12 MiB로 저장됩니다. Source/compiled binary/build logs/입력·계수 식별 및 parse 실패도 보존했습니다.

```sh
python3 -I -S validation/rrtmgp37/omitted-ice-effect/verify_saved.py
python3 -I -S validation/rrtmgp37/omitted-ice-effect/test_saved.py
```

`results/layers.csv`: 모든 native/padding 층의 signed Δheating. `interfaces.csv`: 모든 경계의 Δup/down/net-down. `ice-optics.csv`: 기주·층·band별 raw/scaled extinction/scattering/asymmetry moments. `result.json`: native 최대차·위치·표면/TOA·seed별 집계. CI는 저장 자료 재생이며 새 Fortran build/model run이 아닙니다.

## Number/PSD 결정과 남은 gate

`NUMBER_PSD_DECISION_ko.md`에서 **dry-number-grid-v1을 다음 구현 목표로 채택**했습니다. Host dry-mass number와 native volume number의 전체 경계 변환이 필요하며 현재 raw 직접 전달을 그 구현으로 승인하지 않습니다. Registry label만의 승인, 부분 density 보정, native mean-volume radius와 LUT effective-size의 자동 동등성, Thompson 경험 배율을 기각했습니다. 원 NOAA 의도는 인증하지 않았습니다.

현재 fixed radii/LUT sensitivity는 그 정의 선택을 기다리지 않고 수행한 조건부 연구입니다. 정확한 PSD/LUT primary evidence와 새로운 number bridge의 wet/density 검증은 여전히 필요합니다. 생산 정책과 물리 정확도는 아직 승인하지 않습니다.

기존 일곱 종료 조건을 bytes 그대로 보존했습니다. PHY-NC/SIZE/OCCURRENCE 및 FINAL-IDENTITY는 OPEN, REF-RFMIP/LBL은 FAIL, FINAL-FORECAST는 NOT_RUN, `production_accepted=false`입니다. 이번에 완료한 것은 **누락 ice만의 ΔF/Δheating·sample spread와 정책 판단 근거**입니다.

## 이후 opt-in 생산 후보와 증거 적용 범위

이 계산의 기존 source hash는 그대로 유지합니다. 변경된 소스는 `../historical-source/`의 당시 bytes에 대조하여 이 저장 실행을 재생합니다. 새 number 후보의 현재 소스·실행 근거는 `../dry-number-grid-v1/`에서 별도 검증하며, 과거 민감도 실행을 새 정책 실행으로 재명명하지 않습니다.
