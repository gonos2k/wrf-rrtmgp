# 미완료 해소 체크리스트 — PR167 이후

기준: main `c1ebe4a5e95a20398921d377bcf44ddb14703698`. 기존 15개 제한적 완료와 연구 profile 감사는 유지합니다. 일곱 최상위 종료 조건은 `closure-conditions.json`에 원문·bytes 그대로 고정했습니다. 아래는 같은 조건 안에서 진행 상황과 다음 산출물을 정리한 것입니다. 항목 수를 완성도 백분율로 사용하지 않습니다.

## 이번에 해소한 PHY-OCCURRENCE 하위 공백

- [x] 기존 생산 capture 기능으로 실제 호출의 시각·step·기주를 확인.
- [x] 같은 호출의 source Q/QNC, actual CF와 supplied UDM CF를 구분하고 history와 대조.
- [x] 동시 dry layer mass로 grid/in-cloud/omitted path를 재생.
- [x] CF0 빙정 12셀의 경로·반경·LUT 좌표와 실제 zero hydrometeor optics 연결.
- [x] Cell count·무가중 Q 합 대신 dry-mass 기반 column-path 비율을 집계하고 영향 범위를 명시.
- [x] Capture 이후 70초 history까지 OFF/ON 전체 파일·변수·속성 동일성 확인.
- [x] 원시 capture, NetCDF, 과정 종료 기록, 소스·입력·library 식별정보와 재생 검사를 저장하고 기존 CI에 연결.

이 완료는 발생분율의 물리적 승인이나 flux-loss 산정이 아닙니다. 광학 입력에서 실제로 제외된 경로를 관측할 수 없었던 공백을 닫았습니다.

## 최상위 일곱 항목 — 상태 유지, 다음 산출물 고정

| 항목 | 상태 | 다음 완료 근거 |
|---|---|---|
| PHY-NC | OPEN | 기존 상수 초기화를 포함한 첫 승인 정책의 number 단위·분모·population·변환 계약과 고정 종료 조건 실험. 외부 QNN 보존은 별도 확장으로 둘 수 있음. |
| PHY-SIZE | OPEN | UDM 최종 PSD 모멘트와 고정 LUT 생성 population·크기 정의를 primary evidence로 연결. 이번 radius 산술 replay만으로 승인하지 않음. |
| PHY-OCCURRENCE | OPEN | 이번 actual-call 자료를 이용해 CF0·종별 발생분율·지원 상태의 물리적 선택과 독립 광학/관측 평가. 이번과 같은 개수·경로 연결을 다시 요구하지 않음. |
| REF-RFMIP | FAIL | 원 publisher 생성환경·prewrite/저장 정밀도 계보와 고정 strict 조건. 기존 21 FAIL을 유지. |
| REF-LBL | FAIL | 현재 음의 OD를 보존하며 승인 가능한 분광·복사 기준과 수용 근거 확보. 완료된 선 목록·합성·격자 분석을 반복하지 않음. |
| FINAL-IDENTITY | OPEN | 승인한 최종 정책·실행환경·소스·입력·계수·결과를 하나의 실제 실행으로 연결. 이번 짧은 진단 실행과 구분. |
| FINAL-FORECAST | NOT_RUN | 위 고정 정책의 장시간 4/37·관측 평가. 같은 상태의 engine 차이와 coupled feedback 차이를 분리. |

다음 우선순위는 **PHY-NC/PHY-SIZE/PHY-OCCURRENCE의 첫 승인 범위 결정**과 **독립 기준 확보**입니다. 이번 실제 호출 관측은 재사용할 근거로 두고, 이후 실험은 그 결정이나 독립 정확도 질문을 판별하는 데 사용합니다. 미확정 정의를 label 변경·floor·임의 밀도/CF 배율로 승인하지 않습니다.

`production_accepted=false`. 이 체크리스트의 신규 하위 완료는 최상위 일곱 항목을 자동으로 PASS로 바꾸지 않습니다.
