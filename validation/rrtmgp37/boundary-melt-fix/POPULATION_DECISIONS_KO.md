# 부분구름 population 판정 — 다음 PHY-NC/PHY-SIZE 작업 범위

이번 수정은 소거 순서와 지원하지 않는 경계 실행만 처리한다. 아래 판정은 소스의 동작과 그 정의에 대한 미확정을 구분한다. 기존 일곱 종료 조건을 유지하며 생산 승인은 false다.

| 경계 | 확인한 동작 | 판정 / 다음에 필요한 결정 |
|---|---|---|
| UDM wrapper 입구 | 정책1의 host η에 같은 호출의 건조 밀도를 곱해 ncr 체적 number 구성 | bridge 완료 범위 유지. grid-mean 입자 집단은 선택 계약이며 원 개발자의 population 인증이 아니다 |
| cldf_diag와 CF 조건화 | qci/qrs를 양의 CF로 나누고 ncr은 즉시 변환하지 않음 | 질량은 in-cloud, number는 이전 값. 같은 집단 모멘트라는 해석은 미승인 |
| slope_cloud / slope_rain | CF 조건화한 q와 ncr을 함께 소비 | 부분 CF에서 q/n은 grid-mean q/n보다 1/CF배. 동일 PSD의 조건화라는 가설과 자동 동등하지 않음. 액체/비 경계부터 선택 또는 기각할 것 |
| 순간 빙정 융해 | in-cloud qi로 기존 Ni fit 진단, NC에 더함; 잠열은 qi×CF | 이번 CF=1에서 소거 순서 수정 검증. CF<1의 Ni 집단·증분 복원 규약은 여전히 OPEN. 이 수정으로 number에 임의 CF 배율을 추가하지 않음 |
| CF 복원 | qci/qrs에 CF를 곱함; ncr에 같은 즉시 복원 없음 | 수상체 질량과 number의 과정별 발생영역을 판정해야 함. 모든 ncr에 일괄 CF 나눗셈/곱셈 적용하지 않음 |
| 활성화 | 질량 CF 복원 뒤 RH 기반 분율로 free-CCN→cloud-number 과정, 가용량 제한 | 기존 partial activation 관측 재사용. 활성화 분율과 선행 CF는 동일 개념이라고 가정하지 않음 |
| 최종 wrapper 반환·크기 소비 | 최종 native ncr로 radius/reflectivity, 같은 호출의 밀도로 host η 반환 | 입·출구 단위 bridge 유지. native 액체 평균체적 모멘트와 LUT 유효반경의 동등성은 별도 PHY-SIZE |

근거: `WRF/phys/module_mp_udm.F`의 wrapper, `udm2d`의 “obtain in-cloud properties”, slope 호출, “melting/freezing”, CF 복원, activation, 최종 ncr1 반환. 기존 `partial-activation-observation`과 `dry-number-grid-v1` 증거는 해당 당시 소스에서 재생한다.

종별 PSD/LUT 판정은 PR170의 `PSD_LUT_BINDING_STATUS.json`을 유지한다. 액체 평균체적 반경, 얼음 온도/질량 fit, 눈 characteristic size를 별개로 취급한다. 고정 LUT 생성 집단·모멘트의 독립 근거 없이 액체 Gamma 배율을 얼음/눈에 적용하지 않는다. 이번 수정은 PHY-NC/PHY-SIZE/PHY-OCCURRENCE의 최상위 승인을 하지 않는다.
