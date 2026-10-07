# UDM number 계약 확인 질문 초안

개발자에게 발송하지 않은 확인 질문이다. 아래 답이 없으면 밀도·구름분율 보정이나 Registry 재표기를 적용하지 않는다.

1. Host QNN/QNC/QNR와 UDM NN/NC/NR는 각각 체적당, 건조공기 질량당, 습윤공기 질량당 개수 중 무엇인가? Registry의 kg 분모와 내부 m⁻³ 주석 중 실제 저장·호출 규약은 무엇인가?
2. 각 변수는 초기화, 역학 수송/RK·지정경계, UDM 입구, in-cloud 변환 전후, 과정 경향, 침강, 반경 helper, 반환에서 격자평균인가 구름내 조건부 값인가? 필요한 밀도·분율 변환의 위치와 시점을 명시해 달라.
3. QNN은 구름 안팎의 미활성 CCN 전체인가, 구름 내 CCN인가? 맑은 부분의 CCN은 어떤 값/진단/보존식으로 처리하는가? QNC와 같은 분율 변환을 사용하는가?
4. Nc/Nr의 floor/cap, CCN activation의 source/sink와 number 침강 밀도 weighting은 어떤 단위/population에서 정의되는가? 실제 native 반경이 어떤 PSD 모멘트와 입자 집단을 나타내는가?

후속 식별시험은 두 dry density, 부분구름, 부분 activation, cap/floor 비활성 조건을 함께 사용하고 단계별 시점을 고정한다. 시험 결과에 맞추기 위한 rho/CF/Gamma 배율을 먼저 고르지 않는다.
