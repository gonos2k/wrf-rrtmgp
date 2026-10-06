# UDM27 독립 기준과 precipitation 지원 근거

고정 upstream executable과 이 저장소의 vendored RRTMGP를 같은 공식 RFMIP 입력으로 비교했다. **청천 계산 엔진의 실행 일치**와 **공개 reference 출력에 대한 정확도 검사**를 별도로 보고한다. UDM 수상체의 광학적 타당성은 이 청천 시험으로 판정하지 않는다.

## 독립 청천 비교

상류 소스 `41c5fcd950fed09b8afe186dede266824eca7fd3`, 자료 `ea788bb39876948fa8d2c235665ccff19b4686b5`, GNU Fortran 13.3.0 serial `-O0`, 내부 double precision, 공식 RFMIP 1,800 profiles를 사용했다. 상류 driver와 IO/helper 객체를 그대로 사용하고 연결 library만 바꿨다. 기존 기록의 vendored library는 PR #10의 `ca33525`에서 빌드됐다. 별도 fresh g128/g112 시험은 현재 vendored 소스를 새로 빌드했으며, 새 `independent-rfmip` CI가 같은 절차를 반복한다.

| 비교 | LW 하향·상향 | SW 하향·상향 |
| --- | --- | --- |
| 고정 upstream ↔ vendored CPU, g256/g224 | 두 배열 bitwise 일치 | 두 배열 bitwise 일치 |
| 같은 입력, production gas g128/g112 | 두 배열 bitwise 일치 | 두 배열 bitwise 일치 |
| 공개 reference, `atol=1e-5 W/m²`, `rtol=0` | 모두 정확히 일치, PASS | FAIL: 최대 차이 0.00061035 / 0.00018311 W/m² |

SW 잔차는 수정하지 않은 upstream에서도 동일하다. 이 자료로 그 잔차를 WRF 포팅 때문에 생긴 오류라고 분류할 근거는 없다. 공개 reference의 `RTE-RRTMGP-181204`는 CMIP6 source ID이며 정확한 생성 소스 SHA는 확인되지 않았다. 후속 단파 실험은 실행파일·기체 계수·입력을 고정하고 태양 스펙트럼만 과거 저장 벡터로 바꿨다. 하향·상향 평균 절대차는 각각 `7.4672560e-5 → 5.0376239e-8`, `2.3464896e-5 → 2.2313200e-8 W/m²`로 감소했지만, 고정 허용오차를 넘는 값이 각각 116개·39개 남아 두 검사 모두 FAIL이다. 남은 잔차의 원인은 미확정이며 허용오차를 넓히지 않았다. [원본 provenance·대조군·반사실 계산·실패 보존](../../../validation/rrtmgp37/reference-residual-audit/README.md)을 참고한다. 이 청천 g224 실험은 UDM 구름 조건의 큰 차이나 예보 정확도를 판정하지 않는다.

공개 reference 비교는 gas g256/g224다. 별도 g128/g112 실행도 양쪽 엔진의 bitwise 일치를 확인했지만, cloud-band LUT와 실제 WRF 입력 변환을 검증하지 않는다. 공식 RFMIP 기체 구성과 상류 기본 상수를 사용하므로 WRF의 6기체 부분집합·host constants 검사도 아니다. 수정하지 않은 공식 all-sky loader는 고정 자료의 `diamice_lwr/upr`와 구름 필드명을 읽지 못해 실패하며, 그 실패 로그를 보존한다. 별도 all-sky 검사는 band 자료에 맞춰 정확히 8개 dataset 문자열만 변경하고, 같은 공식 driver·loader를 upstream과 현재 vendored CPU 구름 계산부에 각각 연결한다. 라이브러리의 구름 객체가 실제로 분리됐는지는 linker map으로 검사한다. 24기둥·72층, roughness 2의 제조 구름 상태에서 저장된 25개 상태·플럭스 배열을 bitwise 대조한다. 광학 배열, UDM 반경·수상체 변환, precipitation·McICA·WRF 상수 및 관측 정확도를 판정하는 시험은 아니다. [all-sky 재현과 검사 범위](../../../validation/rrtmgp37/upstream-reference/ALLSKY.md)를 참고한다. [명령·비교기·원본 해시](../../../validation/rrtmgp37/upstream-reference/README.md)에 재현 방법과 결과를 보존했다.

## Graupel과 hail의 지원 경계

고정 CCPP generic `cloud_mp_uni`에는 snow+graupel path를 snow 크기 하나로 처리하는 경로가 있다. 같은 파일의 Thompson mapper는 snow만 사용한다. 따라서 generic 경로는 host별 근사의 선례이며, UDM에 그대로 적용해도 물리적으로 동등하다는 검증은 아니다.

UDM native snow radius는 `qs`, 밀도, 온도로 계산하며 `qg/qh`를 입력받지 않는다. 그 반경을 `qs+qg` 또는 hail의 크기로 간주하면 추가적인 광학 모델 가정이 된다. 조사한 고정 CCPP RRTMGP API에는 hail 광학 입력·계수가 없다. 공개 Mie 기반 연구도 UDM→RRTMGP에 검증된 계수표를 제공하는 것은 아니다. [소스 pin·행·해시·연구 근거](../../../validation/rrtmgp37/precip-support/udm27-precip-support-inventory.md)를 참고한다.

현재 production은 qc/qi/qr/qs를 지원하고 qg는 제외 경로를 진단하며 양의 qh를 거부한다. 실제 3-D MPI 시험은 10분 호출을 통과했으나 20분에 양의 hail 때문에 중단됐다. 같은 시각의 RRTMG4 대조군에도 hail이 있었다. 이는 명시된 미지원 상태가 실제 UDM에서 발생한다는 증거이며, 전체 UDM 예보 성공이나 hail 제외의 타당성 증거가 아니다. [실제 종료와 같은 시각 대조 기록](../../../validation/rrtmgp37/negative-input/README.md)을 함께 읽어야 한다.

Graupel/hail을 지원하려면 UDM PSD와 size convention, 물질·입자 형태, LW/SW band 광학 계수, occurrence fraction을 명시하고 독립 검증해야 한다. 현재 중단을 피하기 위해 snow로 임의 매핑하거나 작은 양의 hail을 버리지 않는다. 이 문서화로 해당 물리 지원 과제를 완료 처리하지 않는다.
