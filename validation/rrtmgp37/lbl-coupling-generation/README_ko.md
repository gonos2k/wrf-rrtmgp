# 선택 CO₂ line의 coupling 계수 생성 관측

PR160의 선택 R3 최초 음수 전환을 만드는 피연산자 생성 경계를 실제 LBLRTM12.17 GNU13.3 double 실행으로 연결했다. 생산 WRF/UDM/RTE·Registry 단위·초기화 정책·광학계수·strict 허용오차를 변경하지 않았다. 음의 signed 항을 제거하거나 clipping하지 않았다. **LBLRTM 전체 물리 reference는 FAIL을 유지한다.**

## 연결한 입력과 계수

실제 TAPE3 전체 122,157,832바이트의 SHA256은 `56bd55fa256ed3b3a672bd4bcd88034cd7086d4fbef2a1def9480199dab2b388`이다. Root가 6,259개 sequential Fortran 레코드의 앞·뒤 marker를 확인했다. 선택 line은 data record521(block260)의 slot124, coupling sidecar는 같은 레코드의 slot125다. Header record520 및 file header1과 함께 실제 payload를 발췌해 보존했다. 번호는 이 TAPE3 안의 1-based 물리 레코드이며 upstream 데이터베이스의 고유 line ID가 아니다.

| 경계 | 실제 기록 |
|---|---|
| 원 line | `VNU=618.023668 cm⁻¹`, encoded MOL102, IFLG1 |
| 분자·동위원소 | molecule code2, TAPE3 header `CO2`, isotopologue code1 |
| 압력 보정 후 | `VNU=618.0235026348411 cm⁻¹` |
| Sidecar의 Y 계수 | 200/250/296/340 K: −4.6030402184, −3.7154300213, −3.1464600563, −2.7390499115 |
| 선택 층 온도 | 228.3152 K, 200–250 K 사이 보간 |
| 보간한 YI | −4.1003830133132935 |
| SP / SPPI | `4.4169257354574224e-4` / `−6.226697078218338e-4` |
| SPPSP=SPPI/SP | −1.4097355154135263 |
| Baseline STRF3 | `1.1768853472463064e-2` |
| Coupling STRF3 | `−5.3091106290652755e-4` |

따라서 선택 음의 계수는 마지막 반올림이나 임의의 확률 제한으로 설명하는 대상이 아니다. 이번 입력에 저장된 signed Y 계수의 보간, 압력 항, `SPPI/SP`, CF3 보간 및 `CLC3`를 통해 이어진다. **계수 생성의 구현 재현과 계수의 분광학적 수용성은 별개다.**

입력 excerpt→RDLIN 변환→LNCOR1의 Y/G 보간·pressure shift·halfwidth·strength→CNVFNV의 baseline/coupling STRF3→선택 F3 lookup 및 ZF3L51회 증가→PR160 최초 음수 전환을 검사한다. 40개 일반 binary64 산술·경계 연결은 비트 재생되고 pow/exp/asin을 포함한 3개 계산은 선언한 8 ULP 이내에서 비교한다. 이번 실행의 세 차이는 모두 0이었다. 다른 libm의 비트 동일성을 요구하지 않는다.

## 실제 실행과 관측 범위

관측기는 PR160의 원래 R3 observer에 읽기·기록 블록만 추가한 사본이다. 새 marker 블록 제거와 추가 USE 제거로 PR160 observer bytes가 정확히 복원된다. PR160 검사는 다시 원 stock 산술을 확인한다. 원래 대입문의 계산식이나 순서는 변경하지 않았다. RDLIN의 실제 읽기 순서로 data record 번호를 세며, 물리 주파수 target 및 실제 CNVFNV 입력 위치와 연결한다. 선택된 계수 trace는 5개 레코드다.

두 build/네 solver 프로세스 모두 RC0이다. 첫 관측기에는 이후 LNCOR1 호출에서 사용하지 않는 지역 `XKT0`를 읽는 잘못된 필드가 들어 있었다. 첫 소스·trace·실행 기록은 보존했으나 최종 coefficient 증거로 사용하지 않는다. 두 번째 관측기는 그 필드를 제거했다. 최종 증거는 두 번째 OFF/ON 실행이다. 서로 다른 독립 기상 사례 네 개로 집계하지 않는다.

성공 빌드에서 `oprop.o`만 변경됐고 다른 object20개는 stock bytes와 같다. 최종 입력38개는 실행 전·후 hash가 유지됐다. 최종 R3 trace는 PR160 실행의 trace 전체 bytes와 동일했다. Root가 실제 45개 OD 파일을 판독했으며 FILHDR 이후53,279개 panel·OD 기록은 OFF/ON·PR160 모두 같다. **전체 파일 bytes는 날짜·시각 영역 차이로 FAIL을 보존**하며 해당 레이아웃의 header offset1336–1351만 예외다. 다른 레이아웃에 이 offset을 일반화하지 않는다.

## 저장 검증

```bash
python3 -I -S validation/rrtmgp37/lbl-coupling-generation/verify_saved.py
python3 -I -S validation/rrtmgp37/lbl-coupling-generation/test_saved.py
```

CI는 포함된 TAPE3 payload 발췌·계수 trace·소스 사본·receipt와 기존 PR160 패키지를 검사한다. 전체 TAPE3·OD·실행파일을 다시 열거나 모델을 새로 실행하지 않는다. 다섯 반례는 species 변조, sidecar 한 binary64 ULP 변조, 다른 record 연결, STRF3 변조 및 LNC 생성 기록 누락을 거부한다. 내부 manifest는 외부 publisher 인증이 아니다. 보존 runtime scripts는 해당 local build/data 경로를 전제로 한 실행 기록이다.

## 완료·잔존 경계

**완료:** 이 TAPE3 안의 분자·동위원소 code와 실제 line/sidecar 레코드 식별; 선택 분기의 입력·온도/압력 보정·coupling STRF3·F3/ZF3L 연산 연결. [결과](result.json)와 [root raw 판독](line-readback.json)을 분리한다.

**미완료:** upstream HITRAN/AER 원 데이터베이스 record 및 mixing 계수의 실험·계산 계보; WK/partition SCOR/ALFD1와 AVRAT/CF3 table 생성의 독립 물리 검증; 필요한 주변 line/R1/R2/continuum의 최종 분광 상쇄와 음의 OD 수용성. 이번에 이 모든 operand ancestry가 완성됐다고 주장하지 않는다. 선택된 IFLG1·zero extra broadener·no width clamp·JRAD0 경로 이외의 일반 branch 검증도 아니다.

남은7개 물리·최종 부모 항목, RFMIP strict FAIL21 및 `production_accepted=false`를 유지한다. QNN 초기화·수농도 단위·PSD/LUT·Thompson37 지원의 판정도 바꾸지 않는다. 다음은 이 line의 upstream mixing 계수 근거와 실제 최종 OD 성분 합성에 집중한다.
