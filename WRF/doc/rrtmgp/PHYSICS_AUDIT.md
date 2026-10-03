# RRTMGP 물리 진단 감사 설계

이 문서는 RRTMG 옵션 4와 RRTMGP 옵션 37의 방사 계산을 같은 WRF 상태에서 비교하고, UDM 구름 분율 및 응결물 경로가 변환되는 과정을 진단하기 위한 opt-in 감사 기능을 설명한다. 감사 계산은 별도의 scratch 배열에 수행하며 그 결과는 WRF 예보 상태에 되돌려 쓰지 않는다. 이는 선택한 호출 상태에서의 방사 계산과 입력 변환을 조사하는 도구이며 장기 예보 검증을 대신하지 않는다.

## 실행과 산출물

`WRF_RRTMGP_AUDIT_DIR`를 기존 디렉터리로 지정하면 같은 상태의 paired-seed 감사가 켜지고, 그 디렉터리에 `same_state.csv`가 생성된다. `WRF_RRTMGP_AUDIT_SEEDS`는 표본 수이며 기본값은 128, 허용 범위는 2–8192이다. 감사는 직렬 실행 전용이다. MPI 빌드 또는 OpenMP 스레드가 둘 이상인 실행은 감사 시작 시 거부된다.

CSV에는 LW와 SW 단계별로 RRTMGP 37 및 RRTMG 4의 현재 출력, 표본 평균과 표준편차, 두 옵션 차이의 표본 표준편차가 기록된다. 진단 항목은 표면 하향 장파, TOA 상향 장파, 층별 장파 온도 가열률, 표면 하향 단파, TOA 상향 단파, 지표 순 단파, 직달 단파, 층별 단파 온도 가열률이다. 가열률은 `RTHRATEN*PI*86400` 또는 `RTHRATENSW*PI*86400`으로 환산한 K/day의 온도 경향이다.

Grid 행은 해당 타일의 실제 격자점별 결과다. `i=0,j=0` 행은 물리적 격자점이 아니라 타일 평균 요약이다. 평균과 표준편차는 고정된 결정론적 seed 집합에서 산출한 기술 통계다. 특히 표준편차는 실제 공간 평균의 seed별 변동을 나타내며, 신뢰구간이나 독립·동일분포 표본을 가정한 평균 오차 추정치로 해석하지 않는다.

입력 원시 호출 자료는 `WRF_RRTMGP_CAPTURE_DIR` 및 `WRF_RRTMGP_CAPTURE_CALL`로 선택 호출을 저장할 수 있다. `WRF_RRTMGP_CAPTURE_ALL=1`은 모든 방사 호출을 저장한다. 출력 파일의 호출 식별자는 `lw_000001`, `sw_000002`처럼 6자리 숫자를 사용한다. 전체 캡처 또한 직렬 전용이며, MPI 또는 OpenMP 스레드가 둘 이상이면 거부된다. 감사 실행기는 초기화 상태를 복제해 옵션 4와 37의 scratch 호출을 비교하고, baseline 호출과 감사 활성 호출의 WRF history 배열이 바이트 단위로 같은지 확인한다.

실행기 인자와 선택 가능한 입력은 다음 도움말에서 확인한다.

```sh
python3 WRF/test/rrtmgp/test_udm_physics_audit.py --help
```

## Seed 및 옵션 간 비교 해석

기본 운영 seed 정책은 RRTMG 4에서 LW=150, SW=1이다. RRTMGP 운영 seed는 도메인 ID·전역 격자 위치·현재 연도·일자·LW/SW 구분의 [고정 일별 계약](DOMAIN_CALENDAR_SEEDS.md)을 따른다. 감사의 명시적 seed override는 이 운영 hash를 대체하며 raw capture에 구분해 기록한다. 따라서 paired-seed 감사에서는 같은 표본 인덱스를 두 옵션에 대응시키지만, 이것이 두 엔진에서 동일한 구름 마스크를 만든다는 뜻은 아니다. 특히 마이크로물리 UDM(옵션 27)에서는 비교 시점의 `has_reqc/has_reqi/has_reqs` 설정도 다르다. RRTMG 4 scratch 경로는 해당 native-radius 입력 플래그가 0이고 RRTMGP 37 scratch 경로는 1이다. 이 설정 차이는 감사 조건의 일부이며 두 경로가 완전히 같은 광학 입력을 사용한다고 가정하지 않는다.

`WRF_RRTMGP_AUDIT_NATIVE4=1`은 scratch RRTMG4에만 세 반경 입력 플래그를 켜는 대조 실험이다. 기본값 0은 기존 generic 반경 경로다. CSV의 `radius_mode`에 0/1을 기록한다. 실행기의 `--native-rrtmg4-counterfactual`도 같은 설정을 적용한다. 4/4 예보 자체나 37/37 예보는 변경하지 않는다. 이 실험은 RRTMG의 기존 입자 변환·snow 보정까지 포함하는 반경 입력 경로의 차이를 조사하며, 두 엔진의 광학 입력을 완전히 일치시키는 시험은 아니다. 미세물리 첫 실행 전의 배경 반경과 이후 UDM 진단 반경을 구별해야 한다. 모드 1의 `value4`는 운영 4 출력이 아니라 반경 입력을 켠 대조 결과다.

## UDM 구름 분율과 경로 진단

37 전용 history 상태 `UDM_CLDFRA` 및 `UDM_CF_STEP`은 UDM 내부 `cldf_diag`가 마지막으로 실제 실행된 결과를 기록한다. 이번 UDM 호출의 모든 subcycle에서 진단이 실행되지 않은 열에는 sentinel `-1`과 `source_step=-1`이 남는다. 뒤 subcycle에서 실행이 생략되어도 앞 subcycle의 마지막 실제 진단은 보존한다. `cldf_diag`는 내부 `ktop`까지 값을 갱신하며, 그 위쪽은 호출 전에 설정한 1이 보존된다. 따라서 이 배열은 실제 UDM 알고리즘이 마지막으로 사용한 배열 전체를 나타내며, 위쪽 레이어를 사후에 0 또는 재계산 값으로 바꾸지 않는다.

`UDM_CF_TOP` records the exact diagnosed extent for that last actual call (`-1` not called, `0` empty extent, otherwise one-based `ktop`). Levels above the top remain part of the UDM working vector, but are not asserted to be diagnosed cloud fraction. See [UDM_CF_EXTENT.md](UDM_CF_EXTENT.md) for the field and replay contracts.

UDM 구름 진단의 길이 척도는 현재 소스에서 `dxmeter=10000.` m로 고정되어 있다. 따라서 이 결과는 WRF 도메인의 `DX`를 읽은 것이 아니라 UDM 내부에서 사용된 고정 10 km 설정을 반영한다.

방사 호출 trace에는 다음 값을 별도 필드로 저장한다.

- `CF`: 방사 입력 빌더가 실제 사용한 cloud fraction.
- `UDM_CF_USED` 및 `UDM_CF_SOURCE_STEP`: 마지막 실제 UDM 진단 배열과 그 시점. 실행되지 않은 열은 sentinel로 남는다.
- `UDM_CF_RECOMPUTED`: 호출 시점의 현재 열역학·응결물 상태에서 UDM `cldf_diag`를 다시 계산한 값. 이는 직전 microphysics subcycle에서 실제 사용된 값과 시점이 다르고, 모든 native 물리 레이어에 대해 계산하므로 `UDM_CF_USED`와 대체 가능한 동의어가 아니다.

기존 운영 방사 경로의 `CLDFRA`는 이 진단 기능으로 변경하지 않는다. 이 감사는 보존된 grid-box 응결물과 경로 변환을 비교하기 위한 부가 자료를 기록한다. 양의 cloud fraction이 있는 레이어에서는 응결물 질량을 보존하도록 경로를 구성한다. 실제 진단이 생략된 UDM 레이어는 B 분석에서 유효성 마스크로 구별한다. cloud fraction이 0인 상태에서 경로로 표현할 수 없는 질량의 생략도 별도 수량으로 보고한다. `qg`는 방사 경로에 포함하지 않으며, 양의 `qh`는 지원되지 않는 응결물 입력으로 거부한다.

분석기는 CF와 경로 조합을 구분해 보여준다. A는 기존 생산 경로의 현재 CF와 경로, B는 실제 마지막 UDM CF와 유효한 양의-CF 응결물 질량을 보존하는 재구성 경로, C는 기존 CF를 유지하면서 grid-mean 경로를 사용하는 비보존 counterfactual이다. C는 질량 보존 정책으로 제안되거나 선택된 구성이 아니다. 현재 상태에서 재계산한 CF는 `B_now` 대조 실험으로 별도 취급한다. 모든 A/B/B_now/C 재생은 모델 상단에 추가된 대기층의 입력을 보존한다. `--graupel-policy as-snow`는 같은 CF에서 grid graupel 경로를 snow 경로에 더하고 UDM snow 반경을 유지하는 별도 실험이다. 실제 캡처에 graupel이 없으면 이것으로 활성 graupel 검증을 했다고 주장하지 않는다.

## 단파 delta 정책 실험

세 가지 synthetic 조합을 고정 상태에서 비교한다. 여기서 `C`는 구름 광학량, `P`는 rain/snow 강수 광학량, `D(X)`는 광학량에 대한 delta-Eddington 변환이다. 덧셈은 τ, τω, τωg를 보존하는 광학 합성이다. 고정 CCPP 소스는 `C+D(P)`이며, 현재 포팅은 `D(C)+D(P)`이다. `D(C+P)`는 합성 후 한 번 변환하는 대조 실험이다.

1. `D(C)+D(P)` — 현재 사용되는 조합
2. `C+D(P)`
3. `D(C+P)`

이 실험은 성분별 delta 조합에 따른 결과 차이를 분리해 보는 통제 실험이다. 정책 선택을 새로 제안하거나 생산 계산을 변경하지 않는다.

## 범위와 미검증 항목

이 감사 결과만으로 24–48시간 예보 성능, MPI 실행, restart 재현성 또는 우박(`qh`)을 포함한 물리 구성을 검증했다고 볼 수 없다. 위 조건은 별도 검증이 필요하다. 본 문서는 감사 설계만 기술하며, 구체적인 실행 결과와 수치는 별도 검증 보고서에서 추가한다.
