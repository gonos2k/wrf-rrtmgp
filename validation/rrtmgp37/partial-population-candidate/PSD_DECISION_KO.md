# 종별 PSD·광학 크기의 이번 판정

평균체적 반경과 optical effective size의 자동 동등성은 기각한다. 이번 판정은 실제 source·Gamma 계수·관측된 과정 상태를 연결하며, µm metadata의 추가 목록으로 대체하지 않는다.

| 종 | native 입자 집단/모멘트 | 실제 광학 소비 | 이번 결정 |
|---|---|---|---|
| Liquid | wrapper 최종 Nc와 질량으로 mean-volume radius. Warm autoconversion은 `N(r)=N0 r^ν exp(-λr)` 형태의 별도 Gamma 적분, ν=min(nint(1e9/N)+2,15) | 고정 band cloud LUT의 liquid effective-size 인자 | Native volume radius=effective radius 자동 동등성 기각. 후보 연구 population에 대한 Γ 모멘트는 연결했으나 최종 PSD와 LUT 생성 분포의 일치는 미승인 |
| Rain | 두-moment exponential slope, cloud/rain 동일 점유영역은 이번 후보의 명시 가정 | `module_ra_rrtmgp_precip.F`의 고정 rain path 계수. 인터페이스에 NR/rain radius가 없음 | Cloud LUT 직접 매핑 기각. NR 변화는 현재 rain optics에서 독립적으로 소비되지 않으며 질량 path를 통해서만 영향. 별도 rain optical PSD 적용성 필요 |
| Ice | 온도·질량밀도 fit, 이번 bridge에 prognostic ice number 없음 | Ice effective-size / roughness 기반 고정 cloud LUT | Liquid Γ 배율 사용 기각. Native fit의 면적/체적 정의와 LUT habit·size 연결이 필요 |
| Snow | 온도별 intercept, 질량 기반 characteristic λ, native `.5/λ` 크기 | 별도 precip snow radius 계수 | Cloud ice와 동일 처리 기각. Characteristic size→적절한 광학 모멘트·snow 입자 재료 연결이 필요 |

## Liquid의 실제 Γ 모멘트

위의 명시적 Gamma 분포에서 `M_j=N0 Γ(ν+j+1)/λ^(ν+j+1)`이다. 따라서

`r_v = [(ν+1)(ν+2)(ν+3)]^(1/3)/λ`, `r_eff = M3/M2 = (ν+3)/λ`.

실제 적격 warm 후보에서 ν=4이며 `r_eff/r_v≈1.177673606`이다. 관측 λ를 사용한 Γ 반경은 두 밀도에서 약 13.8885/16.1468µm(volume), 16.3561/19.0157µm(effective)다. 이들은 **warm autoconversion 시점의 명시적 Γ 해석**이며, 전체 과정 종료의 native 반경이나 LUT 생성 PSD를 대신하지 않는다. 현재 경로는 CF에 따라 ν=4/6/10도 달라져 같은 구름내 분포라는 가정을 만족하지 않는다. 그러므로 공통 경험적 배율로 반경을 맞추지 않는다.

Native final helper는 같은 최종 Q/N으로 mean-volume radius를 계산함을 별도로 확인했다. 관측된 λ의 이상적 Γ M3가 입력 L_c에 대해 약1.0019307인 진단도 기록했다. Source의 유한 정밀도 Γ coefficient/table과 rounded λ를 사용하는 비교이며, 모델의 물 손실이나 새 생산 결함으로 해석하지 않는다. 이 차이까지 무시하고 Γ 모멘트가 모든 경계에서 엄밀히 같다고 선언하지 않는다.

## 고정 LUT 원파일의 연결과 남은 경계

`publisher/binding.json`의 정확한 파일은 official `rrtmgp-data` commit `8ba21ca40c506d886fac5c8d3be1e812b4b8cc54`의 두 band 파일과 bytes가 같다. [LW 원파일](https://github.com/earth-system-radiation/rrtmgp-data/blob/8ba21ca40c506d886fac5c8d3be1e812b4b8cc54/rrtmgp-clouds-lw-bnd.nc), [SW 원파일](https://github.com/earth-system-radiation/rrtmgp-data/blob/8ba21ca40c506d886fac5c8d3be1e812b4b8cc54/rrtmgp-clouds-sw-bnd.nc).

공식 데이터 설명은 과거 RRTMGP commit `74a0e09`에서 복사/rename한 계보를 제시한다. [고정 README](https://github.com/earth-system-radiation/rrtmgp-data/blob/8ba21ca40c506d886fac5c8d3be1e812b4b8cc54/README.md). 현재 프로젝트 frontend는 liquid Mie, ice Yang(2013) 및 roughness 기반이라고 명시한다. 이 정보와 파일의 NCO history만으로 liquid 분포의 variance/shape, ice habit ensemble, native fit과 동일한 모멘트를 인증할 수 없다.

따라서 첫 liquid optical 후보가 필요하면 명시적 PSD의 `M3/M2`를 제안할 수 있으나, 그것은 기존 LUT 생성 분포의 인증이 아니며 독립 광학 대조를 필요로 한다. 이번 PR에서는 생산 radius/계수에 배율을 넣지 않는다. PHY-SIZE와 PHY-OCCURRENCE는 OPEN이다.
