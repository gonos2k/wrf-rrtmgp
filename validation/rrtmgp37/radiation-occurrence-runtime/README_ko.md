# 실제 복사 호출의 CF·물경로·반경·광학 입력 연결

**PASS_SCOPED**: 보존된 PR156 계열 SCM 입력을 현재 생산 소스와 같은 bytes의 실행파일로 실행해, source time 60초 / radiation step 7의 네 기주 LW·SW 입력을 연결했습니다. `PHY-OCCURRENCE`의 하위 관측 공백을 해소한 결과입니다. 발생분율의 물리 승인, 누락하지 않았을 때의 광학량·플럭스 차이, 최종 예보 승인은 아닙니다.

기준 main은 `c1ebe4a5e95a20398921d377bcf44ddb14703698`, tree는 `8b14585deaaae87ab0fafa38a9eac8608dfb69b2`입니다. WRF·UDM·RTE, Registry, 초기화·number 정책, 광학계수와 허용오차는 변경하지 않았습니다. 기존 생산 소스 5,910개 모두를 비교했고, 보존된 빌드 source의 observer block을 제거하면 현재 생산 bytes와 일치합니다. GNU 13.3 serial REAL32 SCM의 보존된 실행파일과 build receipt를 재사용했습니다. 이번 Fortran compile·ideal 실행은 0회입니다.

## 실제 실행과 무영향 검증

- 초기 대조: OFF 1회 + column capture ON 4회, 각각 70초. history는 60초 간격으로 남습니다. 이 출력은 선택 capture 이전이므로 capture 이후의 무영향 근거로 사용하지 않습니다. `initial-campaign/`에 그대로 보존했습니다.
- 최종 대조: OFF 1회 + ON 4회, 각각 70초. history를 10초 간격으로 기록해 capture 이후 70초 출력까지 포함했습니다. `saved/`에 보존했습니다.
- **전체 WRF 프로세스 10회**, 최종 증거 실행 5회. 최종 capture는 네 물리 기주 × LW/SW = **8 phase-call**이며, 같은 셀을 LW와 SW에서 두 번 기록했다고 물질량을 더하지 않습니다.
- 모든 프로세스는 실행 전·후의 durable journal이 있으며 TERMINAL/RC0, timeout 없음, WRF 성공 문자열이 있습니다. subprocess 번호·PID·실제 환경·입력 해시는 원본 기록입니다.
- 최종 OFF/ON 네 쌍의 history 211변수와 restart 643변수는 변수 bytes·정의·속성뿐 아니라 **전체 파일 bytes가 동일**합니다. history는 초기부터 70초까지 8시각, restart는 60초입니다. 70초 history가 capture 이후 갱신을 포함합니다.
- 런타임 `LD_DEBUG=libs`를 같이 기록했습니다. 실제 loader의 초기화 목록과 실행 후 library 파일 해시는 보존하지만, 모든 library bytes를 각 프로세스 안에서 수집했다고 주장하지 않습니다. 최종 물리 정책의 `FINAL-IDENTITY` 승인은 OPEN입니다.

최종 namelist는 seed와 `run_seconds: 0→10`, `end_second: 0→10`, `history_interval_s: 60→10`만 다릅니다. PR167의 정확한 namelist-byte 연구 profile 감사와 별도 진단 구성입니다. 입력 선별·캡처 시각·물리 상태를 조정해 통과시키지 않았습니다. 기존 connected-host 추가 observer 환경은 해제했고, 생산 column capture를 그대로 사용했습니다.

## 실제로 연결한 값

Native raw는 59층이며 LW backend는 모델 위 padding을 포함한 103층, SW는 60층입니다. native 59층과 backend의 대응을 명시적으로 검사합니다. source Q/QNC와 actual CF → dry layer mass → native grid/in-cloud/omitted paths → adapter radii → LUT에 사용된 좌표 → cloud/precip/prepared optical depth와 McICA mask를 같은 phase-call에서 확인했습니다.

**history CF, 공급된 UDM CF, 실제 radiation CF는 구분합니다.** 각 기주에서 history CF와 실제 CF가 다른 층은 31개입니다. `UDM_CF_USED`라는 기존 record 이름은 UDM CF 배열을 기록하며 실제 소비 CF의 별칭이 아닙니다. `RAD_CF_SOURCE`와 `CF`, backend CF는 일치합니다. 공급된 UDM CF의 진단 step은 6이고, 실제 호출의 source time은 60초/step 7입니다. source 물질량과 QNC는 60초 history와 비트 일치합니다.

연구 packet 전체를 PR167 packet과 같다고 주장하지 않습니다. 이번 seed는 보존된 cold-number-input warm-cloud 사례이며, 이전 connected-host packet 대비 **QNRAIN 4셀만 다릅니다**. 나머지 9변수, 특히 QICE·CLDFRA는 같았습니다. 초기 입력은 그대로 재사용했고 이번 캠페인에서 number를 수정하지 않았습니다. 세부 비교는 `saved/readback.json`에 있습니다.

## 실제 호출의 CF0 빙정

각 phase에서 4×59 = 236 native 셀 중 양의 QICE 36셀, CF0 양의 QICE **12셀**을 확인했습니다. 위치·값·동시 dry mass·경로·반경·광학량은 `cf0-ice-call-cells.csv`에 있습니다. 이 CSV의 24행은 LW/SW 각각 같은 12셀을 기록한 것이며, 고유 물리 셀은 12개입니다.

| 실제 호출에서의 기주 경로 집계 | 값 |
|---|---:|
| 네 기주의 grid ice path 합 | 327.4193944274448 g/m² |
| 같은 기주의 omitted ice path 합 | 0.2963788635097451 g/m² |
| omitted/grid native column path 비율 | **0.09051964194974463%** |

이 값은 실제 동시 dry layer mass를 사용한 경로 비율입니다. 셀 면적·map metric을 추가한 domain 총질량, optical-depth 손실률, 플럭스 손실률이 아닙니다. 기주 경로를 더한 집계이며 LW/SW 합계는 서로 같고, 두 phase를 합산하지 않습니다. 단순 QICE 합계의 비율과도 다릅니다.

12셀의 grid ice path는 양수이며 incloud path는 0, omitted path는 grid path와 같습니다. 이 층들의 실제 CLOUD_TAU·PRECIP_TAU·PREPARED_TAU·MASK는 0입니다. host QICE는 보존돼 있습니다. 관측된 zero optics는 현재 omission 정책의 결과이며, omission 없이 계산한 경우의 광학량이나 플럭스 영향은 측정하지 않았습니다.

호스트 반경(m) → adapter 반경(µm) → iceflag 4의 LUT diameter 좌표를 연결했습니다. 관측된 CF0 빙정 반경은 약 5.01–24.12µm, 사용 diameter는 약 10.02–48.25µm입니다. LUT 좌표 bounds는 실제 고정 coefficient NetCDF에서 읽었습니다. 이 산술 연결은 PSD 모멘트·입자 집단의 물리 동등성 승인이 아닙니다.

각 species의 binary32 경로 생성과 분배를 원 연산 순서에 맞춰 재생합니다. `grid = CF*incloud + omitted`는 저장 반올림 잔차를 별도로 검사하며 강제 보정하지 않습니다. 현재 QC/QR의 CF0 omission은 없고, snow/graupel/hail은 관측한 호출에서 0입니다. 다른 시각·구성까지 이를 일반화하지 않습니다.

## 검증 범위와 재생

`archive_runtime.py`는 실제 최종 NetCDF 전체와 captures를 읽어 비교·packet 추출을 수행했습니다. `verify_saved.py`의 CI 재생은 stdlib로 캡처와 packet·저장된 NetCDF 전체 bytes를 재검사합니다. **CI가 NetCDF 변수를 다시 해석하거나 WRF를 실행하는 것은 아닙니다.** source snapshot의 독립 readback은 `saved/source-audit.json.gz`에 보존했고 원래 생산 corpus와 다시 대조합니다. 이후 opt-in 소스 변경은 `historical-source/`의 당시 원본으로 재생하고, 새 후보 실행 근거와 분리합니다.

```sh
python3 -I -S validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py
python3 -I -S validation/rrtmgp37/radiation-occurrence-runtime/test_saved.py
```

기존 acceptance CI의 test entry에 연결했습니다. 일곱 시험은 실제 자료 재생과 history CF 대체, 시각·기주·backend 경로·omitted-layer optics 오류, 잘못된 물리 승격을 검사합니다. 새 workflow나 전체 모델 재빌드 CI를 추가하지 않았습니다.

`run_campaign.py --help`에 재현 인자가 있습니다. 동일 보존 executable/seed/snapshot/library 경로와 새 output directory가 필요합니다. `archive_runtime.py --output`으로 새로운 증거 디렉터리를 만들 수 있습니다. 기존 봉인 자료를 덮어쓰지 않습니다.

## 승인 상태

PR167의 `closure-conditions.json` 일곱 종료 조건을 bytes 그대로 복사했습니다. 새 최상위 gate를 추가하지 않았습니다. PHY-NC·PHY-SIZE·PHY-OCCURRENCE는 OPEN, REF-RFMIP/REF-LBL은 FAIL, FINAL-IDENTITY는 OPEN, FINAL-FORECAST는 NOT_RUN, `production_accepted=false`를 유지합니다. 연구 baseline 감사와 기존 공학적 완료도 그대로 유지합니다.
