# WRF–RRTMGP 37

공식 WRF를 기준으로 장파·단파 복사 옵션 `37/37`에 RTE+RRTMGP를 연결하는 개발 저장소입니다.

## 현재 상태

저장소 초기 구성 중입니다. 기존 선택 Registry 및 수치 부품의 검증 결과를 전체 WRF 예측 검증으로 취급하지 않습니다. 실제 backend 연결·통합 검증 전에는 `37/37` 실행을 명시적으로 차단합니다.

## 기준 소스

- WRF v4.8.0: `06d4240ae989cc3e50af412bb472df3d9048783c`
- NCAR/rte-rrtmgp: `41c5fcd950fed09b8afe186dede266824eca7fd3`
- earth-system-radiation/rrtmgp-data v1.8.1: `aafa333a60c06fca2fbf219fbd17e7f432b43e3f`

상류 원본의 저작권·라이선스를 유지합니다. 구현과 검증 로그를 구분하여 기록합니다.
