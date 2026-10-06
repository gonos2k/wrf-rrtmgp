# 공식 LBLRTM 예제 기준 출력 비교

공식 v12.17 예제 압축파일의 원본 입력으로 선 파일을 한 번 생성하고 stock LBLRTM을 한 번 실행했다. 두 프로그램은 실제 `RC=0`으로 종료했지만, **공식 기준 출력과의 엄격 비교는 FAIL**이다. 결과를 정상 차이 또는 WRF 포팅 오류로 단정하지 않는다.

| 항목 | 방출복사 TAPE27 | 밝기온도 TAPE28 |
|---|---:|---:|
| 각 출력의 비교 점 수 | 800,904 | 800,904 |
| 파수 격자 불일치 | 0 | 0 |
| 출력값 불일치 | 794,103 | 790,312 |
| 최대 절대차 | 9.73107e-9, 원본 radiance 단위 | 0.0727 K |
| 최대 상대차 | 약 0.135695% | 약 0.0247751% |
| RMS 차이 | 6.70746e-9, 원본 radiance 단위 | 0.0528059 K |

전체 유한성·단조 격자 검사를 적용하고, 원본 출력 정밀도에서 Decimal 값이 같은지 비교했다. 새로운 atol/rtol을 추가하지 않았다. 세대 시각과 공백을 제외한 두 스펙트럼 header context는 같지만, raw 파일 바이트와 수치 값은 다르다. 비교 reader의 실제 `RC=1`을 보존했다.

## 기준 출력의 구성 불일치

압축파일 이름은 v12.17이지만, 보존된 `TAPE6_ex`는 2023년 생성 시각과 **MT_CKD 4.1**을 기록한다. 이 파일의 continuum 이력은 LBLRTM 12.15까지다. 현재 실행의 실제 source/data 핀은 LBLRTM 12.17/MT_CKD 4.3이다. 현재 source 이력의 MT_CKD 4.2 변화 범위 600–1400 cm⁻¹는 이번 1000–1200 cm⁻¹ 구간과 겹친다.

| 실행 기록 | 선 파일 최대 파수 | 전체 선 수 |
|---|---:|---:|
| 보존 기준 출력 | 3499.995 cm⁻¹ | 3,508,352 |
| 원본 archive LNFL deck의 이번 실행 | 5000 cm⁻¹ | 3,893,964 |

이는 동일한 역사적 executable·continuum·TAPE3 구성이 확인된 회귀 비교가 아니다. 변경된 continuum과 선 파일 구성이 위 수치 차이에 각각 얼마나 기여하는지는 계산하지 않았다. 기준 자료의 역사적 실행파일·TAPE3·외부 continuum 해시는 archive에 없다. **버전 차이를 확인한 사실이 엄격 FAIL을 PASS로 바꾸지는 않는다.**

## 실행과 자료 범위

원본 archive의 0–5000 cm⁻¹ `LNOUT EXBRD NLTE` LNFL 입력과 built-in US-standard atmosphere의 1000–1200 cm⁻¹ `EM=1` 입력을 수정 없이 사용했다. archive 스크립트와 바이너리는 실행하지 않았다. 기존 GNU single LNFL과 GNU double stock LBLRTM, AER v3.8.1 및 MT_CKD 4.3 자료를 사용했다. 67개 입력/source/runtime-library 핀은 실행 전에 검증했다.

프로그램별 실제 종료 코드를 fsync로 보존한 뒤 output inventory와 비교를 시작했다. 종료 중 예외나 reap 미완료 상태는 후처리를 차단한다. 모델 재시도·새 컴파일·WRF 실행은 없었다. 초기 v1/v2 정적 검토 차단 기록도 보존했으며 실행에는 수정된 v3만 사용했다.

큰 선 데이터·TAPE3·실행파일·기준/현재 전체 스펙트럼·TAPE6 원문은 공개하지 않는다. 패키지에는 작성한 runner/reader, 작은 원본 입력 deck, 핀·종료 기록·요약과 독립 검토만 있다. 절대/로컬 경로가 기록된 자료는 당시 실행의 provenance이며, 필요한 외부 자료 없이 공개 패키지만으로 계산을 재실행할 수 있다는 뜻이 아니다. manifest는 이 패키지의 저장 무결성을 확인한다. `.gitattributes`의 네 literal 경로 규칙은 원본 입력 두 개와 Fortran stderr 두 개의 바이트·고정 형식을 보존하며, 전체 저장소의 whitespace 정책을 변경하지 않는다.

## 남은 판정

이 예제는 방출복사와 밝기온도 비교이며, `IEMIT=0` optical-depth 기준 검증이 아니다. 기존 음수 광학두께 FAIL과 같은 상태의 WRF 4↔37 잔차는 계속 OPEN이다. 다음 단계는 역사적 기준 구성의 독립 핀을 확보하거나, 현재 구성과 같은 입력·자료를 사용하는 별도 기준을 마련하고 차이를 인과 분해하는 것이다.

자료: [AER LBLRTM v12.17 release](https://github.com/AER-RC/LBLRTM/releases/tag/v12.17), [LBLRTM source](https://github.com/AER-RC/LBLRTM/tree/a85ac73447c1e62401a57a34bbcb040683345dca).
