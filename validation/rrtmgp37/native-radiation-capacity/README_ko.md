# Native 층 열용량 후보와 실제 양의 구름 Gamma8 소비

기준 main `eff9ced5798583b48b4fa651338aef596babb6b0`, tree `6cd13be1c18edb54567409376fab43c081219c2b`.

**한 개의 명시적 열역학 완결 가정 `native-constant-kappa-source-v1`을 연구 후보로 선택하고, private WRF 어댑터에서 실제 적용했다.** 같은 플럭스의 층별 폐합과 60초 적용을 확인했다. 양의 구름이 유지되는 별도 WRF에서 Gamma8 최종 모멘트→반경→LUT→광학량→가열률도 연결했다.

생산 WRF·UDM·RTE 소스, namelist 정책·기본값, 생산 반경·계수는 변경하지 않았다. 아래 환경변수는 **개인 연구 실행파일에만 존재**한다. 일반 WRF에서 지원하는 옵션이 아니다. 기존 일곱 조건과 `production_accepted=false`를 그대로 유지한다.

## 1. 선택한 열용량과 근거

검토한 실제 소스는 `module_model_constants.F`, `calc_p_rho`/`phy_prep` 및 `conv_t_tendf_to_moist`다. 현재 dynamics는 고정된 `kappa=Rd/cpd`, `theta_m=(1+Rv/Rd*qv)*theta`, dry density EOS를 사용한다. [WRF 기술문서](https://www2.mmm.ucar.edu/wrf/users/docs/technote/v4_technote.pdf)의 식 2.11·2.15·2.16과도 대응한다.

**EOS만으로 열용량을 유일하게 결정할 수는 없다.** 이번에는 고정 조성의 consistent constant-kappa 열역학을 추가 가정으로 선택한다. 이 가정은 [Eldred, Taylor & Guba (2022), §4.1, 식 79](https://arxiv.org/html/2204.00534v2#S4.SS1)의 열용량 근사에 해당한다. 이것이 원 WRF 전체 physics의 유일한 의도였다고 인증하지 않는다.

건조공기 1 kg을 기준으로 `R*=Rd+Rv*qv`를 두고 `cp*/cv*=cpd/cvd`, `cp*−cv*=R*`를 함께 요구하면,

\[
 c_p^*=c_{pd}(1+(R_v/R_d)q_v),\quad
 C_k=m_{d,k}c_p^*.
\]

고정 압력·조성에서 radiation source는 `Tdot=Q/C`다. 따라서 `theta_m`에 대한 열원은

\[
 m_dc_{pd}\Pi\dot\theta_m=Q
\]

로 환산된다. 이를 EOS와 연결한 선택된 caloric potential은 고정 조성에서 `u*=cvd*theta_m*Pi + u_ref(q)`로 쓸 수 있다. WRF의 고정 gamma EOS를 대입하면 `∂u*/∂theta_m|alpha_d,q=cpd*Pi`, `−∂u*/∂alpha_d|theta_m,q=p`다. 따라서 위 source 계약은 이 **선택한 potential의 열원과 압력 일에 대한 conjugacy**를 함께 만족한다. EOS만 확인하고 열용량을 가정 없이 역인증한 것이 아니다. 실제 source ledger에서는 acoustic 압력 일을 별도로 합산하지 않으므로 이 유도 자체를 전체 적분 에너지 수지의 PASS로 사용하지 않는다.

이는 **온도 등가 장부의 `md*cpd`만 선택하는 것과 다르다.** 이 constant-kappa 완결에서는 응결물 열용량을 무시하고 수증기의 근사 열용량도 실제 `cpv`와 다르다. 실제 혼합물 현열, 잠열, 압력 일, 전체 WRF physics가 하나의 potential을 공유한다는 승인은 아니다. UDM의 기존 `cpm`·과정식을 바꾸지 않았다.

**채택 범위:** 현재 warm-periodic, 고정 조성 복사 source 경계의 명시적 연구 후보. 전체 모델의 caloric consistency나 관측 정확도를 승인하지 않는다.

## 2. 기존 플럭스 재사용: 기주 배율이 아닌 층별 환산

PR178의 내부 wp 플럭스를 그대로 사용해 각 native 층 `Q_k`를 재구성하고 위 `C_k`로 나눴다. 2,832개 native layer/phase/column/time 조합을 검사했으며, `C*Tdot−Q` 최대 절대값은 `8.88e−16 W/m²`다. 새 RTE 실행은 없다. 개별 층 source에 동일한 정의를 적용했으며 기주 총합에 맞춘 배율을 사용하지 않는다.

같은 기존 가열률을 이번 constant-kappa 장부로 평가하면 60초 차이는 약 **+22.16946 J/m²**다. 앞서 dry-cp 장부의 **−38.00 J/m²**와 부호도 다르다. **기준을 바꾸면 숫자가 달라지므로 과거 38 J/m²를 실제 열 손실이라고 부르거나, 이를 없애는 보정만으로 물리적 정답을 선택할 수 없다.**

## 3. 실제 어댑터 후보

PR178의 read-only observer archive를 개인 복사하고, RRTMGP adapter와 LW/SW wrapper의 세 객체만 추가 교체했다. 실제 컴파일 3회·archive·link의 PID/RC와 소스·객체 범위를 보존한다. production tree와 원 archive는 그대로다.

- Wrapper가 동일 시점의 **native dry mass와 실제 host qv**를 전달한다. 가스 VMR나 분자량 비에서 qv를 역추정하지 않는다.
- Native 첫 59층의 `heat=Q/C`만 바꾼다. LW/SW, clear/all-sky에 같은 helper를 사용한다. native 밖의 확장층은 기존 pressure-based helper를 유지한다.
- 광학량·기체 column·플럭스·McICA·number·PSD·생산 반경을 heat-only 대조에서 유지한다.
- 기존 held-theta 방식은 바꾸지 않는다. 열용량과 유지 변수 변경을 한 실험에 섞지 않는다.
- Scalar serial warm 연구 실행에 한정한다. 이 private setter는 thread/MPI/general model 경로로 배포하지 않는다.

Heat-only 세 실행은 PR176/178의 같은 초기 파일을 그대로 사용했다. 모든 실행이 60초 정상 종료했다.

| 0–60초 장부, J/m² | Legacy, 매 step | C 후보, 매 step | C 후보, 30초 호출 |
|---|---:|---:|---:|
| 해당 실행 native flux 수렴 | 4160.176581 | 4160.182745 | 1271.296699 |
| 호출 C로 환산한 실제 source 적용량 | 4182.345917 | 4160.182726 | 1271.308080 |
| 호출 C 적용량−flux | **+22.169336** | **−0.00001949** | **+0.0113813** |
| 각 physics step의 현재 C 적용량−flux | +22.169453 | +0.00009685 | +0.0507247 |

Candidate native 각 층의 내부 `C*heat−Q` 최대 절대값은 `1.71e−13 W/m²`다. 실제 K/day·theta·THM·RK source add의 REAL32 산술과 채택된 RK3의 acoustic 시간만 재생했다. 에너지 장부는 해당 physics step의 Exner/qv를 고정한 국소 source 환산이며, 동역학 압력 일을 포함하지 않는다.

매 step 대조에서는 호출 C 기준과 현재 C 기준의 작은 차이도 구분한다. Native dry mass가 wrapper에서 REAL32로 공급된 값과 동역학 질량식의 고정밀 재평가 값이 다르고, 각 source 변환에도 반올림이 있다. 원래 38 J/m²와 이 수준을 혼동하지 않는다.

30초 호출에서는 theta 경향이 유지된다. 이후 Exner·qv·질량이 달라지므로 호출 C 장부와 현재 C 장부가 각각 달라진다. **30초 결과의 차이를 heat-capacity helper의 층별 폐합 실패로 분류하지 않는다.** 호출 시점의 flux를 계속 일정하게 적용하는 새 정책을 추가하지 않았다.

같은 첫 호출의 input 전 필드, all/clear flux, gas optics와 mask가 legacy/C 후보에서 동일하다. Native 밖 HR/HRC도 비트 동일하다. Clear native heating은 저장 flux의 REAL32 반올림 상계로 별도 확인한다. Legacy private 실행의 **211개×7시각 history 배열 bytes는 PR176/178과 전부 동일**하다. 이후 후보와 legacy의 상태 차이는 실제 가열률 변경에 따른 피드백이므로 비트 일치를 요구하지 않는다.

## 4. 양의 cloud에서 Gamma8의 실제 소비

기존 NetCDF seed producer의 같은 pressure/EOS/Phi 재구성식을 재사용했다. Low-level qv는 명시한 saturation 식으로, QC는 `5e−4 kg/kg`, cloud 체적 number는 `1e8 m−3`로 설정하고 THM·T_BASE·η도 함께 생산했다. 새 ideal 실행은 없다. 별도 NetCDF 재생 시험은 **실제 실행한 입력의 전체 파일 bytes**와 일치한다. 연구 범위는 2×2×59 warm 기주로 그대로다.

원 실행 producer receipt의 설명 문자열에는 예전 `5e7` cloud number가 남아 있었다. 실제 코드·배열은 `1e8`이다. 원본 receipt/source를 보존하고 재생기의 설명만 고쳤다. 수정된 재생기가 생성한 실제 NetCDF bytes가 동일함을 시험했다. 숫자 표현이나 과거 실행을 다시 표기한 것은 아니다.

별도 두 WRF 실행(native radius / Gamma8 optical consumer)도 같은 새 입력에서 60초 정상 종료했다. **Gamma8 실행은 열용량 후보를 끈 채** 수행해 두 정책을 분리한다. 60초 최대 QC는 각각 약 `4.68402e−4`, `4.68310e−4 kg/kg`다.

실제 source time **10초**, UDM 완료 이후 양의 cloud가 있는 22층에서:

1. 같은 raw QC·η·dry rho·발생영역으로 local `M0`, `M3`를 구성한다.
2. number-Gamma shape 8의 lambda, `M2`, `reff=M3/M2`를 계산한다.
3. 그 값이 **실제 public-column REL로 전달된 REAL32 값**과 일치한다.
4. 같은 물경로·원 LUT에서 SW raw extinction, LW absorption+별도 precip τ를 재구성해 실제 광학량과 대조한다. 생산 계수 수정이나 Mie 재실행은 없다.
5. 같은 호출의 mask·총 광학량·UP/DN/HR를 보존한다.

| source 10초 실제 소비 범위 | Native 반경 실행 | Gamma8 소비 실행 |
|---|---:|---:|
| REL 범위, μm | 10.5335–11.0309 | **11.7524–12.3073** |
| LW cloud τ 최대 | 4.65508 | 4.16463 |
| SW cloud τ 최대 | 3.95197 | 3.48857 |

22층의 발생분율은 약 0.99845–0.99873이며 선택한 액체 LUT 범위의 clipping은 비활성이다. 처음의 별도 UDM fixture와 달리 이번 값은 실제 WRF의 10초 source에 연결돼 있다.

두 실행은 앞선 복사 효과로 10초 상태도 조금 달라진다. **위 τ 최대값 차이를 순수한 같은-state 반경 민감도로 부르지 않는다.** 여기서 닫은 것은 각 실행의 같은 시점 `q,η→M2,reff→실제 광학 소비`다. 고정 상태 민감도·독립 광학에 관한 PR177의 결과와, 원 LUT 생성 PSD·실제 구름 관측의 타당성은 별개다. 생산 `re_cloud`는 변경하지 않았다.

## 5. 판정과 다음 종료 범위

- 층 열용량: constant-kappa **열역학 완결 가정 하나를 명시적으로 선택**하고, 동일 플럭스 층별 폐합·실제 source 적용을 확인했다. EOS만으로 원 WRF의 유일한 열용량을 증명했다고 주장하지 않는다.
- Gamma8: 양의 실제 WRF source의 모멘트와 optical REL/LUT/가열률 연결을 확인했다. 과거 cloud-free 성공을 이 근거로 쓰지 않았다.
- Production 기본값·새 policy 번호·경험적 배율·UDM 밀도·number 보정은 추가하지 않았다.
- 기존 PBL 물리 질량 규약과 reference FAIL은 그대로 남는다. 같은 YSU matrix나 PSD 교차차이를 이번 새 과학 계산으로 반복하지 않았다.
- **다음 통합 결정:** 이 명시적 열역학 근사를 첫 연구 구성의 실제 열원 계약으로 받아들일지 판단한 뒤, 받아들인 것만 metadata/restart와 함께 최소 연결한다. 현재 코드 전체가 동일 caloric model을 공유한다는 증거가 없으므로 production correction으로 자동 승격하지 않았다.
- 전체 에너지·원 LUT PSD·관측·혼합상·일반 입력/경계·장시간 최종 예보는 미승인이다. 기존 일곱 조건은 byte 그대로다.

## 재생과 실행 수

실제 적격 실행: **WRF 5회**, private 객체 컴파일 3회. 새 standalone UDM/RTE/Mie/LBLRTM/ideal 계산은 없다. RTE는 실제 WRF 안에서 실행됐다. 하나의 제조 기주와 별도의 양의 구름 variant이며 독립 기상 사례 다섯 개가 아니다.

```sh
python -I -S validation/rrtmgp37/native-radiation-capacity/verify_saved.py
python -I -S validation/rrtmgp37/native-radiation-capacity/test_saved.py
# NetCDF 의존성이 있는 로컬 producer 재생:
python validation/rrtmgp37/native-radiation-capacity/test_make_positive_input.py
```

CI는 저장 자료 재생이며 새로운 모델 계산이 아니다. 원본 source, private 후보, archive 변경 범위, 실제 명령·PID·RC, NetCDF/packet/capture, 결과와 해석 제한을 함께 보존했다.
