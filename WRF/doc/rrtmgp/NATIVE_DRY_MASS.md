# UDM27 수분 경로의 native 건조질량 분모

UDM qv 및 여섯 수상체 질량혼합비의 분모는 건조공기 질량이다. 기존 `WP=q×Δp/g`의 radiation `P8W=grid%p_hyd_w`는 수증기와 수상체 하중을 포함하는 정역학 압력이다. 그 차분을 건조층 질량으로 사용하면 수분 경로에 하중을 다시 곱한다. 이는 기존 4번에서 상속한 근사였으며 큰 4↔37 플럭스 차이가 모두 이 근사 때문이라는 뜻은 아니다.

## production 37의 계약

```text
Mdry(k) = -DNW(k) * [C1H(k)*MUT + C2H(k)] / g     kg dry air m-2
WP_grid(x,k) = max(q_x(k),0) * Mdry(k) * 1000     g m-2
WP_in(x,k) = WP_grid(x,k) / CF(k)                CF > 0
```

`DNW<0`이고 이 physics 호출 시점의 `MUT=MU_2+MUB`다. `solve_em.F::rk_step_prep` → `module_em.F::calculate_full(mut,mub,mu,...)` → `module_big_step_utilities_em.F`의 `rfield=rfieldb+rfieldp` 연결로 확인한다. 같은 최초 호출의 실제 초기 NetCDF `MU+MUB`에서도 독립 재계산한다.

`module_first_rk_step_part1.F`는 37 선택 시에만 배열을 만들고 물리층을 계산한다. driver와 LW/SW wrapper가 전달하며 37 wrapper는 배열이 없으면 종료한다. builder는 길이·유한성·양의 질량을 검사한다. 음수 q 보정량과 hail 오류 경로도 같은 분모를 사용한다. 원본 q 및 기존 4번 산술은 변경하지 않는다.

직접 standalone builder 호출에서 배열을 생략한 경우에만 과거 `Δp/g` 근사를 유지한다. historical fixture 호환이며 production 37의 fallback이 아니다. 기체 column 계산, 가열률의 압력 분모, 광학표, 반경, CF, McICA seed는 이 수정의 대상이 아니다. 전체 에너지·질량 계약이 모두 native dry coordinate로 통일됐다고 주장하지 않는다.

상부 대기 확장층에는 native 질량을 추정하지 않는다. 실제 물리층만 전달하고 확장층 LWP/IWP/RWP/SWP는 계속 0이다. qg 제외, 모든 양의 qh 거부, CF=0 응축수 제외 및 제한적 음수 보정 정책도 유지한다.

## 독립 검증

`test_udm_native_mass.py`는 production builder를 호출하지 않는다. 실제 첫 LW/SW raw capture의 일곱 q 프로필을 같은 실행의 초기 NetCDF 값과 정확히 대조한 뒤 `MU`, `MUB`, `DNW`, `C1H`, `C2H`로 층 질량을 계산한다. raw CF와 sibling input CF도 일치해야 한다. 여섯 grid path·음수 보정량·in-cloud 및 제외 경로, LW 44/SW 1 확장층의 광학 경로 0을 검사한다.

사전에 정한 허용치는 `8×eps32×abs(expected)+2×minimum_float32_subnormal`이다. pressure-interface 차분 검사는 별도로 REAL32 직렬화·차분 정밀도 규모를 사용한다. raw 파일 자체에는 시각이 없으므로 시각 연결은 선택한 history 레코드와 초기 상태의 정확한 q·좌표 fingerprint를 근거로 한다. 첫 호출 fixture용이며 임의의 진화한 history가 초기 입력과 같다고 가정하지 않는다.

```bash
python3 WRF/test/rrtmgp/test_udm_native_mass.py \
  build/udm-scm/mixed/ra37-call1/capture \
  build/udm-scm/mixed/ra37-call1/wrfinput_d01 \
  --history build/udm-scm/mixed/ra37-call1/wrfout_d01_1999-10-22_19:00:00 \
  --time-index 0 --executable WRF/main/wrf.exe \
  --output build/udm-scm/mixed/native-dry-mass.json
```

실제 control/mixed에서는 native 건조 column 질량이 약 8080.05349 kg/m²이고 `Δp/g`와 건조질량의 column 차이는 약 9.8612/9.8712 kg/m²다. `Δp/g`는 `Mdry×(1+qv+qc+qr+qi+qs+qg+qh)`와 REAL32 차분 범위에서 일치한다. 캡처 질량과 독립 좌표 재계산의 최대 차이는 1.5259e−5 kg/m²다. 질량 하나를 0.1 kg/m² 바꾸거나 source QV를 바꾼 실제 파일 대조군은 거부됐다.

GNU 직렬 WRF 재빌드 후 standalone 66/66과 paired UDM SCM·독립 replay·지원 gate가 통과했다. 수정 전 frozen 실행파일과 수정 후 4/4는 control/mixed 각각 208개 배열이 bitwise 동일했다. 해당 수정의 회귀 근거이며 새 공식 pristine 빌드 비교 또는 병렬·restart 검증을 대신하지 않는다. 실행 해시와 측정값은 [실행 기록](../../../validation/rrtmgp37/native-dry-mass/README.md)에 있다. CI는 fresh serial SCM 뒤 같은 독립 좌표 검사를 수행한다.

UDM 반경과 RRTMGP ice LUT의 크기 metric 동등성, graupel/hail 광학, CF/seed 정책, 장시간 예보·관측 검증은 별도로 남아 있다.

기체 광학의 건조 molecular column은 후속 [native gas-column 계약](NATIVE_GAS_COLUMNS.md)에서 같은 native 질량을 사용한다. 위의 PR15 실행 기록은 해당 수정 전 범위를 그대로 유지한다.
