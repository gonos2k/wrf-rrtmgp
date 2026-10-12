# 생산 정책 결정표: 연구 계약과 과학 승인 분리

기준은 PR166 main d74f8e9b185bbc407156b6a7dd930dd2f1c03929이다. 이 문서는 기존 사실을 다시 실험하자는 계획이 아니라, 지원할 정책과 미확정 정의를 구분해 검토할 수 있는 결정표다. 제안 연구 범위는 기존 상수 CCN 경로이며, 외부 수농도 보존을 추가한 생산 패치나 NOAA 원래 규약의 인증이 아니다. 최초 과학 승인 범위의 선택은 아직 별도 결정이다.

| 계약 | 현 코드에서 확인된 사실 | 이 v1 연구 profile의 선택 | 과학 승인을 위해 필요한 결정 |
|---|---|---|---|
| QNN 초기화 | cold-start 첫37 driver는ccn_conc를 대입; 확인한60초 checkpoint restart는 건너뜀 | 기존 대입 유지. Cold 입력의 공간분포 활용·민감도 실험으로 해석하지 않음 | 기존 상수와 외부 입력 보존 중 지원 범위, 유효0/결측 구분, restart 표현 호환성 |
| Host number | Registry는kg-1; generic scalar는 건조질량 가중; UDM 호출·반환은 직접 배열 전달 | 세 number를UNRESOLVED_NATIVE_RAW로 취급 | 변수별 질량 분모·전체/구름내 집단·시점·변환 위치를 하나의 계약으로 확정 |
| CCN 제한 | 내부 입구clip과 일부 후속 제한은 별도 연산 | 기존5e7–2e10 raw 입력 제한 유지. 모든 과정의 최종 범위 불변량으로 선언하지 않음 | 체적/질량당 기준을 정한 후 같은 기준의 제한값·증감 수지와 물리 의미 |
| 최종 크기 | native helper가반환한 크기를 사용하고 LUT는effective-radius API를 사용 | 반경에 경험적 계수나 새rho/CF 배율을 넣지 않음 | 최종 PSD 모멘트·population과 정확한 pinned LUT의 생성 모멘트/재료 연결 |
| L/I/R/S 발생분율 | 현 경로는 공유CF; 실제 LW/SW caller는allow_clear_condensate=true | 해당 omission 정책을 연구 가정으로 공개 | 종별 발생분율과CF0 양성 질량의 광학 처리·수지·독립 검증 |
| G/H | mode0는graupel optics를 소비하지 않고 양성hail은 거부. mode1은 실험 경로 | 확인한 snapshot의qg=qh=0 범위만 인정. 양성G/H는 이 profile 밖 | 재료·습성·PSD·발생분율 및 어느 frozen 모드를 첫 승인 범위로 삼을지 |
| 수송/병렬 | 실제 연결 근거는scalar_adv_opt0/RK3/5차수평·3차수직/periodic serialREAL32 | 정확히 보존된 cold/restart 설정을 참조 | 다른 운영 옵션을 선택하면 해당 source/limiter·수지·양성 조건·병렬 구성의 적용 범위 |

## 단위 가설을 새 정책으로 채택하려면

같은 집단에 대해 η가건조질량당 number라는 **자체 가설**을 채택할 수는 있다. 그 경우 체적량n=ρ_dη와 체적기준clip L/U의 질량당 등가범위[L/ρ_d,U/ρ_d]가 함께 필요하다. cloud number의grid/구름내 변환에는 별도로clear-air 집단과CF 진단 시점이 필요하며 CCN에자동으로같은CF 변환을 적용할 수 없다.

이 가설은 다음 모든 경계를 함께 명시해야 시험 가능한 정책이 된다: 외부 단위→초기/경계 입력→저장·수송→UDM 입구→입자 집단별 과정/제한→최종 모멘트→반환·checkpoint. 일부 경계에만 배율을 넣는 생산 변경은 이번에 하지 않았다. 원 개발자 회신 없이 자체 규약을 채택한 경우에는 자체 정책 버전으로 남기고 NOAA 의도 확인과 구분한다.

## 일곱 종료 조건을 고정

[closure-conditions.json](closure-conditions.json)은 기존 일곱 항목의 종료 조건을 그대로 고정한다. 새 하위 시험을 새 필수 gate로 추가하지 않는다. 관련 정의와 연구 구성의 선택은 서로 다른 결정이고, greenCI나자체label로물리 승인으로 바꾸지 않는다.

- PHY-NC: 위 number 계약과 집단/시점·전체 변환 연결. 기존 실제 host 연결은 다시 요구하지 않는다.
- PHY-SIZE: 최종 PSD 모멘트와 LUT의 생성 정의·같은 입자 집단 연결.
- PHY-OCCURRENCE: CF0와종별발생분율·G/H 재료/습성/지원범위 및독립근거.
- REF-RFMIP: published strict21 FAIL 보존. 원래 publisher prewrite/생성환경과 혼합정밀도 판정을 분리.
- REF-LBL: 음수와interstitial grid 차이의 구분, 승인 가능한 독립 기준. 이미 완료한 계보·161/321 판독은 반복 조건으로 만들지 않음.
- FINAL-IDENTITY: 최종 선택된 정책 버전·source·binary·library·inputs·coefficients·outputs의 같은 실행 연결.
- FINAL-FORECAST: 동일 상태의engine차이와결합예보피드백 차이를 분리하고, 관측/불확실성과 결과 전 수용 기준을 정한 장시간 평가.

최종 정량 수용기준은 현재 자료에서 사후에 만들지 않았다. 기준과 평가 자료가 없는 항목은OPEN/FAIL/NOT_RUN으로 남긴다. 이 v1은 연구용으로만 사용할 수 있으며, 체크리스트의label을임의로PASS로바꿔도physical 요청은 거부한다.
