# 후보 구현과 병행한 판단 범위

`PSD_LUT_BINDING_STATUS.json`은 실제 고정 LW/SW band LUT의 좌표 metadata와 현재 native/frontend 소스를 읽은 기록입니다. LUT 좌표의 μm 표기는 확인했지만 생성 PSD 모멘트와 population을 인증하지 않습니다. 따라서 액체 native 평균체적 반경을 optical effective size로 자동 승인하는 경로는 지원하지 않으며, ice fit·snow characteristic size에는 액체 Gamma 배율을 적용하지 않습니다. 종별 미확정 경계를 분리해 PHY-SIZE를 유지합니다.

발생분율은 #169의 occurrence-one 민감도를 반복하지 않습니다. 별도 빙정 발생분율 후보는 그 집단의 정의와 독립적인 구름/빙정 근거를 확보한 뒤 기존 A/Z/B 틀에서 비교합니다. 작은 CF floor, 공통 CF 변경, occurrence one의 민감도를 서로 다른 정책으로 구분합니다. 이번 number bridge에는 occurrence·반경·광학계수 변경을 섞지 않았습니다.

Reference의 RFMIP strict 21개와 LBLRTM 음의 OD는 그대로 FAIL입니다. Number bridge의 native-volume control은 변환/과정/반경 연결을 평가하며 독립 분광 정확도 기준을 대체하지 않습니다. 최종 reference는 입력·분광 범위·모델 가정·불확실성과 사전 수용 기준에 연결되어야 합니다.

후속 최소 작업은 native 부분구름 과정의 population 가정과 첫 과학 지원 범위를 판정하고, 종별 LUT 생성 모멘트와 발생분율 근거를 연결하는 것입니다. 최종 정책이 확정되면 그 변경 경계의 회귀와 FINAL-IDENTITY/FINAL-FORECAST를 수행합니다. 기존 일곱 종료 조건 외의 새 gate는 추가하지 않습니다.
