# 고정 CO₂ 원자료 목록 → LNFL TAPE3 전달 검증

기준 main은 PR162 병합 커밋 `8c2bc9e6f914db34895b8a1395319bb5e6129505`, tree `40dcab22257abea8aeff6904e458973d318ad6e1`이다. 이번 자료는 다음 미완료 중 LNFL에 공급한 목록의 전달을 조사한다. 필요한 모든 물리적 mixing partner의 존재·적용성, LBLRTM 내부 유효 범위·cutoff, 음의 최종 OD의 수용성은 승인하지 않는다.

## 실제 수행

Root가 고정 publisher combined ASCII 908,403,720바이트(8,992,860줄)와 실제 historical run-v6 TAPE3 122,157,832바이트를 전부 직접 열었다. TAPE3의 6,259개 순차 레코드와 3,129개 block을 앞뒤 marker까지 검사했다. 첫 전체 판독은 multiset과 집계를 계산했고, 두 번째는 같은 판독에서 공개 가능한 해시 목록을 함께 보존했다. 두 판독은 RC0이다. Compiler·WRF·LNFL·LBLRTM 실행은 0회이다.

요청 범위는 475–2275 cm⁻¹이다. CO₂ 일반 선 180,771개 중 coupling flag1 선은 127,543개, flag0은 53,228개이다. 원자료와 실제 TAPE3의 비교 필드 multiset은 누락0·추가0으로 정확히 같다. 전체 TAPE3 일반 선은 선택된 일곱 분자를 합쳐 648,464개이며, 전체 sidecar128,015개에는 CH₄472개도 포함된다. 이 수치들을 CO₂ 개수와 혼동하지 않는다.

비교 필드는 VNU, encoded molecule/isotopologue, IFLG, air/self width, lower energy, `1−TDEP`, pressure shift, 인접 Y/G 및 sidecar flag이다. 원래 F100의 single 변환과 zero self-width 정책을 반영했다. **정규화 strength, quantum label, 추가 broadener/speed dependency를 전체 목록에서 비교하지 않았다.** 그러므로 전체 record bytes나 upstream 전역 transition identity가 동일하다는 주장이 아니다.

서로 다른 원 record가 비교 필드에서 같을 수 있다. 180,771개는 178,430개 고유 fingerprint로 표현되며 각 multiplicity를 보존했다. 집합 크기만 비교해 중복을 제거하지 않는다. 25 cm⁻¹ 집계에서는 1575/1600/1625/1650에서 시작하는 네 구간에 원자료 CO₂ 일반 선이 없다. 이 빈 목록은 흡수나 wing 기여가 0이라는 뜻이 아니다. 최초 saved 검사기의 모든 구간 점유 가정을 수정했고, scientific readback은 변경하지 않았다.

PR161의 실제 포함된 TAPE3 block260/record521/slot124는 전체 hashed roster에서 정확히 한 번 나타난다. 이전 선택 line 검증과 이번 전체 목록을 이 지점에서 연결한다.

## 실제 rejection 설정과 남은 범위

Historical run-v6의 실제 TAPE5 HOLIND는 blank이다. F100이며 NOCPL·REJ token이 없다. 보존 TAPE6의 22개 분자 행 모두 strength rejection이 0이다. 소스에도 `SR`는 0으로 초기화하고, REJ를 명시한 뒤 음수 값을 제공한 경우만 `SRD`로 대체한다. **SRD가 소스에 있다는 이유로 이 실행에 CO₂ 기본 하한1.873E−29가 적용됐다고 설명하면 안 된다.** 과거 sealed plan/receipt는 고치지 않고 실제 설정을 별도로 기록한다.

LBLRTM의 `LNCOR1` SPEAK 약선 거부는 IFLAG0 분기에 있다. 선택 CO₂ flag1은 그 검사에 진입하지 않는다. 다만 invalid species/isotope, SUI0, `HWF3*ALFV+VNU < VFT` 등의 다른 조건은 남는다. Root가 다시 읽은 보존 LBLRTM TAPE6에는 DPTMIN2E−4, DPTFAC0.001, layer21에서 DV0.00376889/BOUNDF3 1.9297 및 HIRAC1 NLIN633337/LINCNT143494가 인쇄돼 있다. 인쇄된 값은 내부 binary 값의 정확한 관측이 아니며, 두 aggregate count는 CO₂만의 수치도 아니다. 이번 작업에서 층별 coupled-line survivor 목록은 동적으로 수집하지 않았다.

25 cm⁻¹ LNFL 외곽 margin, LNFL strength rejection, LBLRTM layer-specific weak-line rejection 및 finite-support는 서로 다른 경계이다. 원 ASCII에서 실제 TAPE3까지 목록이 같다는 결과는 원 mixing 모델에 필요한 선이 publisher 목록에 모두 있음을 증명하지 않는다. Y/G 계수에 이미 집약된 partner 효과와 각 선의 합성이 어떤 물리 가정을 쓰는지 별도 근거가 필요하다.

## 저장 CI와 재현 범위

`source-roster.bin.gz`와 `TAPE3-roster.bin.gz`는 projection SHA25632바이트+uint32 multiplicity의 정렬 목록이다. literal publisher ASCII/TAPE3와 원 scalar 목록은 재배포하지 않았다. 두 roster의 현재 gzip bytes가 같아 Git은 같은 blob으로 보존한다.

`verify_saved.py`는 해시 목록의 모든 entry·multiplicity, full-root-readback 집계·hash, actual TAPE5/TAPE6, 이전 포함 TAPE3의 선택 member를 검사한다. Manifest는 정확한 package roster와 bytes를 고정한다. **CI는 private publisher ASCII와 전체 TAPE3를 다시 열지 않으며, root의 원문 해석을 독립적으로 재수행하지 않는다.** 이 한계를 metadata PASS로 숨기지 않는다.

여섯 반례는 fingerprint 누락, 같은 개수의 다른 fingerprint 교체, 사용하지 않은 SRD 하한 주장, bin 누락, 다른 selected slot 연결, physical-partner 승인 승격을 거부한다.

Root reader 원본은 `source/read_census.py`에 있다. Private 원자료를 보유한 workspace에서 원래 `build/udm37-line-selection-v1/read_census.py` 위치로 복원한 뒤 실행할 수 있다. 스크립트의 고정 원자료·실행 pin과 출력 위치를 임의 변경한 실행을 당시 재현으로 취급하지 않는다.

## 다음 종료 경계

공급된 CO₂ 목록의 LNFL 전달은 명시한 projection에서 완료이다. 다음은 original mixing model의 partner 정의·적용 범위, 층별 실제 surviving line과 finite-support inventory, 허용 cutoff/격자 변화의 수렴성, 독립 분광/flux 기준이다. Coupling이나 signed 기여를 제거/clipping해 승인하지 않는다. AER는 CO₂ continuum 생성과 coupling의 일관성을 요구한다([공식 설명](https://rtweb.aer.com/lblrtm_code.html)).

REF-LBL FAIL, 기존 selected OD−0.009028119955355695, RFMIP strict21, 기존15개 제한적 완료·7개 물리/최종 미완료, production_accepted=false를 유지한다. 생산 WRF·UDM·RTE, Registry, 초기화·단위·광학계수·UDM27 gate·허용오차는 변경하지 않았다.
