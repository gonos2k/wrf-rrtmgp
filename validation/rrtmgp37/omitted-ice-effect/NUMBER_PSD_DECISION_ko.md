# 첫 number·PSD 정책의 채택과 기각

기준은 main `36301782b2372b28f942920d5ab7997801b16e3a`입니다. 기존 연구 baseline은 유지합니다. 아래는 **자체적으로 채택한 다음 구현 계약**과 **지금 기각할 해석**을 구분하며 NOAA 원래 의도의 인증이나 물리 정확도 승인으로 표현하지 않습니다. 이번 PR에서 생산 변환식을 바꾸지 않습니다.

## 채택: dry-number-grid-v1이라는 단일 구현 목표

| 변수 | Host 저장·수송·경계·checkpoint | UDM 과정 입력·내부·반환 | 입자 집단 |
|---|---|---|---|
| QNN | 건조공기 질량당 ηNN, kg⁻¹ | nNN=ρd·ηNN, m⁻³ | 활성화 전 자유 CCN reservoir; 총 aerosol이나 cloud number와 동일하지 않음 |
| QNC | 건조공기 질량당 ηNC, kg⁻¹ | nNC=ρd·ηNC, m⁻³ | 구름방울 grid-mean 총수; 구름내 조건부 number로 재명명하지 않음 |
| QNR | 건조공기 질량당 ηNR, kg⁻¹ | nNR=ρd·ηNR, m⁻³ | 빗방울 grid-mean 총수 |

모든 입력·반환은 동일 시점의 native dry density로 변환합니다. UDM 호출 전 작업배열에 n=ρdη를 구성하고, **모든 과정이 끝난 반환 n을 같은 density로 η=n/ρd**로 되돌립니다. 질량 분모를 moist air로 혼합하지 않습니다. Host q는 같은 dry-air 질량분모의 grid mean을 유지합니다. 물리/수송 분할을 거치는 시간 변환을 명시해야 하며, 수송된 η에 새로운 시각의 ρd를 쓰는 것은 체적 concentration의 물리 변화입니다.

첫 지원 범위는 기존 cold-start constant CCN을 유지합니다. 체적 배경값 n0=10⁸ m⁻³를 만들고 host에는 ηNN=n0/ρd를 저장하는 규약입니다. 외부 QNN 보존·Thompson37 확장은 첫 범위에서 제외합니다. 결측과 유효 0은 별개이며 restart는 재초기화하지 않고 η checkpoint를 복원합니다. 기존 raw checkpoint를 새 η checkpoint로 무조건 읽지 않습니다. 정책 버전을 다르게 식별하고 명시적 변환이 없으면 호환으로 승인하지 않습니다.

CCN 입구 제한은 clip(ρdηNN,L,U)/ρd, L=5×10⁷, U=2×10¹⁰의 체적 기준입니다. 첫 상수 초기화와 반복 입구 제한은 별개입니다. 최종 반환을 자동으로 같은 범위로 clipping하지 않습니다. 후속 활성화·증발 등 실제 과정의 최종 n을 반환합니다. Cloud/rain의 입구·과정 제한도 native 체적 기준으로 고정하고 host η에 같은 수치 상수를 직접 적용하지 않습니다. Number에는 CF를 임의로 곱하거나 나누지 않습니다. Cloud/rain 발생분율을 이용하는 별도 광학 population 계약은 q와 n을 같은 집단·시점으로 연결해야 합니다.

**이 계약을 생산에 채택하려면 전체 경계 변환과 wet activation 두-density 검증이 필요합니다. 현재 구현은 raw 직접 전달이므로 아직 이 계약을 구현했다고 표시하지 않습니다.** 고정 PHY-NC 종료 조건은 OPEN입니다.

## 근거와 이번에 기각한 해석

`module_mp_udm.F:slope_cloud`는 λ³=pidnc·N/(qρ)를 사용하며 pidnc=πρwater/6입니다. qρ가 kg/m³, pidnc가 kg/m³일 때 λ를 m⁻¹로 해석하려면 N은 m⁻³이어야 합니다. 최종 liquid helper도 (pidnc·NC/(qρ))^(1/3)를 씁니다. 이는 **소스 수식의 차원적 추론**이며 원 개발자의 전체 저장 규약 인증은 아닙니다. Activation은 ncr1 자유 CCN에서 ncr2 cloud로 number를 옮기고, 반환은 ncr1/2/3을 직접 되돌립니다.

Registry의 kg⁻¹ label, 건조질량 가중 generic scalar 수송과 native raw 직접 전달은 이 변환 경계를 저절로 구현하지 않습니다. 따라서 **Registry label만으로 현재 native 값을 kg⁻¹라고 승인하는 해석**, **내부 주석만으로 host 저장량을 m⁻³로 재명명하는 해석**, **초기화나 반경 한 곳에만 density를 넣는 수정**을 기각합니다. `UNRESOLVED_NATIVE_RAW`를 물리 단위로 승인하지 않습니다.

## Liquid 크기: 지금 승인할 수 없는 동등성

Clamp·floor가 비활성이고 동일한 population이라고 가정하면 native liquid helper는

r_native = 0.5 [ρd q/(a N)]^(1/3),  a=πρwater/6

입니다. 위 채택 계약 N=ρdη에서는 r_native=0.5[q/(aη)]^(1/3)로 정리됩니다. 이는 그 집단의 **평균체적 반경**과 연결되는 수식입니다. λ라는 변수명만으로 전체 Gamma PSD의 실제 slope를 뜻한다고 승인하지 않습니다.

Gamma PSD n(D)∝D^µ exp(−λD)를 가정하면 r_eff=M3/(2M2), r_v=0.5(M3/M0)^(1/3)이고

r_eff/r_v = [(µ+3)²/((µ+1)(µ+2))]^(1/3)

입니다. 따라서 일반적으로 평균체적 반경과 광학 유효반경은 같지 않습니다. 이 식은 명시된 PSD의 조건부 모멘트 관계이며, UDM 최종 상태의 PSD가 Gamma라는 새 승인이 아닙니다. 과정별 Gamma shape를 최종 복사용 PSD의 shape로 그대로 넘길 근거가 없습니다.

**기각:** m→µm→ice diameter 좌표 변환의 성공을 모멘트 호환성으로 승인하는 것, Thompson과 맞추기 위한 고정 배율, 임의 shape 하나를 모든 native 상태에 적용하는 것. Liquid radius, Wyser 계열 ice fit, snow characteristic size는 별도 population·모멘트 정의가 필요합니다.

**PHY-SIZE는 OPEN:** 정확한 고정 LUT의 생성 population·모멘트에 대한 primary evidence가 확보되지 않아 native 크기와의 동등성을 채택하지 않습니다. 첫 생산 수정은 이 근거와 PHY-NC 경계 검증 뒤에만 선택합니다. 이번 누락 빙정 계산은 현재 반경/LUT를 고정한 조건부 민감도이며 이 판단과 충돌하지 않습니다.

## 고정한 다음 구현 경계

이 문서는 수치를 조정하는 패치를 요청하지 않습니다. 다음 생산 후보는 이 계약 하나의 초기·경계·저장·수송·제한·과정·반경·반환·restart를 함께 구현해야 합니다. 필요한 두 dry-density/partial-CF/partial-activation 검증은 기존 PHY-NC 종료 조건 안에서 수행합니다. LUT 모멘트 근거가 확보되지 않으면 반경의 경험적 변경을 통합하지 않습니다. 이미 완료한 input 전달·범위시험·#168 관측을 새 gate로 다시 요구하지 않습니다.
