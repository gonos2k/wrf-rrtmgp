# 실제 layer 21 선 선택·선폭·R3 기여 연결

기준 main은 PR163 병합 `784e831c1c7f3fc6e823f93a0d6ae7cf21d2d19b`, tree `b7383329120ad8bdd3f00ecb5557889e3388778b`이다. 생산 WRF/UDM/RTE·Registry·초기화·광학계수·허용오차·UDM27 gate를 변경하지 않았다.

이번 root 실행은 기존 PR162 최종 관측 소스를 확장하여 GNU13.3 double LBLRTM을 다시 빌드하고 같은 TAPE5/TAPE3/continuum 입력의 OFF/ON을 실행했다. 최종 실행에서 `oprop.o`만 달라졌고 다른 object20개는 같다. 새로운 관측 블록을 제거하면 PR162 소스 bytes가 복원된다. 자식 실행 종료·회수 이후 출력과 입력 hash를 판독했다.

## 닫힌 경계

- [x] Layer21, panel13/14에서 원래 선 중심이 문제 파수 ±25 cm⁻¹ 안인 실제 LNCOR1 진입을 TAPE3 record/slot·원 encoded molecule·flag·strength와 연결.
- [x] 실제 계산용 DV, unclamped/clamped width, 하한/상한 작동 여부, 유한 범위와 SPEAK 통과·탈락 사유 기록 및 재생.
- [x] 같은 물리 파수 `618.6144711111115 cm⁻¹`의 R3 CN write1976개 모두를 해당 선의 통과 결과에 연결. 관측 밖 기여는 하드 오류로 처리.
- [x] 같은 write 연산 순서와 기존 MIN_R3 trace 피연산자·상태 연결 비트 재생.
- [x] 원시 OD45개/arm과 PR162를 root가 다시 읽어 과학 record53279개 동일, MIN_R3/LINE_COEFF/FINAL_OD trace bytes 동일 확인.
- [x] 같은 실행의 실제 OD panel 발췌와 최종 trace를 PR162 합성 검사로 재생. 선택 OD 음수 유지.

| 실제 관측량 | 결과 |
|---|---:|
| LNCOR1 진입·고유 TAPE3 선 | 9253 |
| 통과 | 5337 |
| Flag0 SPEAK 약선 거부 | 3916 |
| 전체 관측 선폭 하한/상한 작동 | 11 / 0 |
| 문제 R3에 실제 기여한 선 | 1007 |
| 기여 선 flag1 / flag0 | 969 / 38 |
| 기여 선 width clamp | 0 |
| 기여 선 원래 계산 폭 범위 | 0.0180704444–0.0395844881 cm⁻¹ |
| 실제 DV | 0.0037688888888888906 cm⁻¹ |
| Baseline / coupling write | 1007 / 969 |
| 모든 line write 뒤 선택 R3 | −2.5643980319365688×10⁻⁵ |
| 선택 최종 OD | **−0.009028119955355695** |

선택 CO₂ record521/slot124는 flag1이며 SPEAK 검사를 우회했다. 원래 폭과 사용 폭은 둘 다0.03752230843288326이다. 이번 구성에서 해당 선의 약선 거부나 width clamp를 음수 원인으로 볼 근거는 없다. 전체 관측 CO₂5814개 중5159개 통과/655개 약선 거부이며, 이를 물리적으로 필요한 partner가 모두 포함됐다는 승인으로 확대하지 않는다.

`line-use.csv.gz`는9253개 관측 진입의 압축 CSV이다. Record/slot/species/flag, 원·이동 중심, 원·제한 폭, DV, 거부 사유, 실제 target baseline/coupling 기여를 담는다. CSV의 기여는 기록 피연산자의 곱이며, 최종 OD나 전체 선 흡수가 아니다. 단위가 있는 R3 분할 성분을 W/m² 플럭스로 해석하지 않는다. reason0은 통과, reason5는 실제 flag0 SPEAK 거부다. 다른 거부 분기의 실행 결과는 이번에 관측되지 않았다.

## 실행·판독 범위

최종 적격 실행은 make1회, solver2회(OFF/ON)이다. 전체 시도는 make2회, solver4회다. 최초 ON은 지나치게 넓은 panel 관측이32MiB trace 상한을 넘어 종료·회수됐으며 최종 근거에서 제외했다. 첫 OFF는RC0이지만 최종 패시비티는 수정된 최종 OFF/ON 쌍만 사용한다. 준비 스크립트의 anchor/plan 경로 실패도 `attempts.json`에 분리했다. 최초 실패를 production 물리 결함으로 집계하지 않는다.

실제 TAPE3 입력 hash는`56bd55fa256ed3b3a672bd4bcd88034cd7086d4fbef2a1def9480199dab2b388`이다.9253개 진입과 연결되는58개 data payload 및58개 block header와 file header1개를 실제 파일에서 발췌했다. 전체 record marker를 순회했지만180771개 CO₂ 공급 roster를 다시 전수 인증한 것은 아니다. 그 전달 경계는 PR163의 완료 상태를 유지한다.

관측 OUTCOME은 거부된SP가0으로 대입된 뒤, SPPSP의 마지막0 대입 직전에 기록한다. 이번9253개 진입은 모두 coefficient 단계까지 도달했고, 실제 거부3916개는 flag0/SPPSP=0이 이미 정의된 경우다. 미사용·미정의 지역변수나 초기 탈락 분기의 피연산자를 증거에 합산하지 않는다.

과학 데이터는 비트 같지만 전체 OD bytes는 날짜·시각 헤더 차이로 **FAIL을 보존**한다. 이번 레이아웃의 변경은 header1416bytes 중1336–1351 offset에 한정된다. 다른 compiler/precision 레이아웃에 이 offset을 일반화하지 않는다.

## 저장 CI와 다음 경계

`python3 -I -S validation/rrtmgp37/lbl-layer-line-use/verify_saved.py`

`python3 -I -S validation/rrtmgp37/lbl-layer-line-use/test_saved.py`

저장 CI는 sealed payload·소스 복원·실제 발췌·실행 영수증과9253개 선택/폭/계수·1976개 R3 연산을 재생하고6개 반례를 거부한다. **새 solver 실행, 전체 TAPE3/OD 재판독은 하지 않는다.** 원시 전체 OD에 대한 패시비티는 root 판독 기록이며, CI에서는 포함한 실제 panel payload와 trace만 직접 재생한다.

- [ ] 고정 입력에서 실제 DV 변화와 선폭 clamp/support·기여 선 목록을 동반한 격자/절단 수렴성.
- [ ] 원 mixing 근사의 적용성, 필요한 물리 partner와 coefficient 근거.
- [ ] 모든 직접 R1/R2 stencil 기여와 전체 band·45층 reference 수용성.
- [ ] 승인된 기준의 플럭스·가열률·최종 예보 평가.

현재 target R3의 기여 선에 clamp가 없다는 사실을 다른 격자의 기여 목록 불변성으로 일반화하지 않는다.9253은 관측한 두 panel의 LNC 진입 수이며, 전체 ±25 cm⁻¹ 입력 roster나 독립 기상 사례 수가 아니다. Coupling/continuum 제거, signed contribution clipping, 허용오차 완화는 하지 않았다. **REF-LBL FAIL, 기존15개 제한적 완료/7개 물리·최종 미완료와 `production_accepted=false`를 유지한다.**
