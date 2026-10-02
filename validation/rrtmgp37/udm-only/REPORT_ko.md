# UDM27 전용 RRTMGP37 검증

평가 범위는 UDM `mp_physics=27`, 장·단파 `37/37`, `use_mp_re=1`이다. 기준은 이전 포팅 main `9d7b5922079654d890454e4e1cbd5cccee28ff0b`이며, 다른 미세물리의 이전 결과를 UDM 결과로 사용하지 않는다.

## 반영한 코드

- 실제 UDM 반경 계산에 쓰이는 `den1d`에 밀도를 복사했다. signaling-NaN 대조 시험은 그 한 줄을 제거하면 실패한다.
- UDM native liquid/ice/snow radius를 37/37에서만 활성화했다. qc/qi는 cloud LUT, qr/qs는 공개 CCPP 강수 광학으로 처리한다. snow 반경은 ice LUT에 넣거나 직경으로 두 배 하지 않는다.
- SW cloud optics와 precipitation optics의 delta scaling을 각각 한 번 수행한 뒤 광학량을 합성한다. 12850–16000 cm⁻¹ 전이 밴드의 지면 알베도·VIS/NIR 진단은 절반씩 나눈다.
- 6종 질량 경로를 기록한다. qg는 광학 입력 0 및 전량 제외 진단, 양의 qh는 명시 거부다. 음수 qg도 builder 검사에 전달하고 거부한다.
- V4 actual-column capture와 production builder/adapter/precipitation module을 링크하지 않는 standalone reference를 비교한다. reference가 같은 RTE/RRTMGP 코어와 계수를 쓰므로 관측 정확도 또는 독립 분광모델 검증은 아니다.

상세 입력 계약과 출처는 [UDM_ONLY.md](../../../WRF/doc/rrtmgp/UDM_ONLY.md), [강수 식 출처](../../../WRF/phys/rrtmgp_precip_source.json)에 있다.

## 실행 근거

최종 상태와 실행 파일·로그의 SHA256은 [validation.json](validation.json)에 보존한다. 전체 NetCDF history와 큰 광학 capture는 로컬 `build/` 시험 디렉터리에 있으며, GitHub CI에서는 해당 capture와 로그를 artifact로 저장한다.

| 검사 | 검증 범위 |
|---|---|
| standalone CTest 45개 | 입력/질량/반경, rain/snow 광학, V4 및 구형 저장본 재생, 기존 backend 회귀 |
| 실제 outer UDM | density packing, native size 범위, density/number 반응, 누락 density 대조 실패 |
| Registry 및 코어 | 생성/등록 보존, 고정 gas optics 에너지 계약 |
| GNU serial em_scm_xy | 전체 WRF 빌드와 실제 UDM SCM 실행 |
| control/mixed 각 1분 | 같은 초기 입력의 4/4·37/37, 10초 출력, 첫·두 번째 실제 장·단파 기둥 독립 재생 |
| 수정 전 UDM4 비교 | control/mixed 각 history 배열 208개 비트 단위 일치; 공식 원본 WRF 실행파일과의 비교는 아님 |
| 부정 시험 | 잘못된 미세물리/혼합 복사/native radius 비활성/positive hail/negative graupel 거부 |
| 지면/CF 시험 | 알베도 0/0.2/0.99/1, 플럭스 계약, swint 1/2 거부, cf=0 phase별 제외 진단 |

## RRTMG4와의 차이 해석

초기 WRF 파일은 각 4↔37 쌍에서 SHA256이 같다. 아래는 2×2 직렬 SCM의 첫 유효 출력(10초) 및 10–60초 여섯 출력의 공간·시간 평균 차이 `37−4`이며 단위는 W/m²다. 초기 출력의 0 값은 평균에서 제외했다.

| UDM 사례 | SWDOWN 첫 출력 | SWDOWN 1분 평균 | GLW 첫 출력 | GLW 1분 평균 | OLR 첫 출력 | OLR 1분 평균 |
|---|---:|---:|---:|---:|---:|---:|
| control | −0.519 | +45.262 | +0.248 | −1.445 | +0.939 | +5.107 |
| mixed | +2.790 | +45.792 | +2.554 | +0.397 | −1.872 | +4.544 |

OLR는 `LWUPT` 진단이다. 전체 지면 플럭스·가열률 통계는 [radiation-comparison.json](radiation-comparison.json)에 있다. 이 수치는 coupled 적분의 차이이며 시간마다 동일 상태를 두 엔진에 동시에 넣은 offline 비교가 아니다. native radius·snow/rain 광학 선택, McICA 표본 및 상태 피드백이 함께 포함된다.

따라서 **검증한 기둥의 포팅·광학 합성 경로는 독립 재생으로 확인했지만, 약 45 W/m²의 평균 차이를 모두 정상적인 물리 차이라고 판정하지 않는다.** 다음 인과 분해는 UDM의 동일 시각 상태를 4/37 양쪽에 재입력하고 복수 시드 평균과 고정 시드 표본을 분리하는 것이다. 짧은 성공 적분으로 정확도 우열을 판단하지 않는다.

## 남은 범위

현재 v1은 qc/qi/qr/qs 광학을 지원한다. qg/h 광학, UDM 내부 cloud fraction export 및 CLDFRA 비교, 강수 발생분율, McICA 시간/도메인 seed 정책, host 상수 통일, MPI/OpenMP/restart/nest, real-data 24–48시간 및 관측 검증, batching은 완료되지 않았다. 특히 graupel이 많은 UDM 사례와 hail이 발생하는 일반 예보를 현재 지원 완료로 선언하지 않는다.
