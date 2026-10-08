# UDM27 RRTMGP37 미완료 항목 해소 체크리스트

기준 main은 `0f6dd96c4ad588f974c2f89600c1b9aecbde7ccd`, tree는 `720e462503a36a1b1c79ec55bc04c6aab2f92b26`이다. 기존 15개 제한적 완료는 유지한다. 아래 7개 물리·최종 승인 항목은 이번 하위 작업의 성공과 구분한다. `production_accepted=false`, 원래 19개 및 current 12개 승인 항목은 변경하지 않았다.

## 남은 항목과 완료 조건

| 항목 | 상태 | 이번에 해소한 하위 작업 | 다음 종료 조건 |
|---|---|---|---|
| PHY-NC 수농도와 초기화 정책 | OPEN | PR156–157의 실제 host 연결·세 number 입력 보존 검사는 완료 상태다. | 변수별 질량분모/population을 확정하고 기존 상수 초기화의 지원범위를 결정한다. 외부 입력 보존은 별도 계약이다. 가정한 밀도/CF 보정은 적용하지 않는다. |
| PHY-SIZE PSD와 LUT 유효크기 | OPEN | UDM 과정별 Gamma 정규화·slope·최종 helper와 LUT consumer의 정의표를 작성했다. | AER revision 2174의 정확한 생성 recipe·계수/PSD와 현재 pinned 파일의 연결을 확보한다. 평균체적 반경과 광학 유효반경을 임의 1.06 배율로 맞추지 않는다. |
| REF-RFMIP RFMIP published strict 기준 | FAIL | 누락된 8개 실패 셀의 candidate binary64 prewrite를 새로운 1회 SW standalone 실행으로 확보했다. 전체 flux float32 bytes와 기존 결과가 동일하다. | 정확한 publisher 생성 환경과 pre-cast reference를 확보한다. Candidate prewrite 분류는 strict 실패의 해결이나 publisher 재현이 아니다. |
| REF-LBL LBLRTM 음의 광학두께 | FAIL | 기존 v14 semantic review가 이미 완료됐음을 대장에 연결했다. 35개의 선택 direct XINT write는 음수 목적지의 최초 발생원을 설명하지 않는다. | 35개 attribution/29개 distinct cell의 소스 표를 작성했다. 남은 runtime target hit·MAX/valid extent·owner panel·predecessor를 인증한다. endpoint 일치는 완전한 source roster의 증명이 아니다. |
| PHY-OCCURRENCE 강수 발생분율과 frozen 재료 | OPEN | 6종 native/CU·mode0/1·CF0/positive CF의 물경로와 마스크 소스 표를 작성했다. | 종별 발생분율과 재료/습성 가정을 정한 독립 optics 및 관측 대조를 수행한다. source 표의 완성은 물리 정책의 승인이 아니다. |
| FINAL-IDENTITY 최종 실행 identity | OPEN | 보존된 connected-host 실행의 binary/input/namelist/log/history와 현재 생산 source bytes를 연결했다. 5915개 WRF 파일 일치, 차이는 시험 runner 2개다. | 최종 정책이 승인된 뒤 새 실행의 실제 환경과 library closure를 기록한다. 이번 ldd는 현재 audit 환경이며 원래 실행환경 인증이 아니다. |
| FINAL-FORECAST 최종 장시간 예보와 관측 | NOT_RUN | 기존 13h/48h 및 관측 자료의 source/policy 범위를 유지한다. 새 최종 정책 실행으로 전용하지 않는다. | 최종 정책·수송 옵션·입력·관측 지표를 고정한 뒤 해당 구성의 장시간 쌍과 관측을 실행한다. 정책 미확정 상태에서 종료 성공만으로 정확도를 승인하지 않는다. |

항목별 종료 조건과 근거는 [checklist.json](checklist.json)에 있다. 완료율 백분율로 해석하지 않는다. PHY-NC의 실제 host 연결은 PR156–157의 시험 구성에서 완료됐으며, 다시 누락된 것으로 취급하지 않는다.

## 이번 실제 실행과 실패 보존

- **Native CCN 범위:** 실제 UDM 전체 모듈을 변경 없이 컴파일하고, 두 밀도 및 하한·상한 바로 안팎의 20개 제조 조건을 시험했다. v2 O0/O2는 compile/link 16회, fixture process 6회, outer UDM 호출 120회다. 세 활성층의 clip 입력/작업배열/반환과 native/OFF/ON 비트가 일치했다. `flgzero=true`의 건조 경로에 한정하며 두 subcycle을 실행했다. 구름 증발의 uncapped number 반환 등 모든 과정에 일반화하지 않는다.
- **초기 검사 실패:** 첫 O0 시도는 compile/link 8회, fixture process 3회, outer UDM 호출 60회였으며 모두 프로세스 RC0였다. 검사기가 세 활성층과 네 번째 storage level을 혼동해 실패했다. 원래 receipt와 로그를 보존했고 기대 roster를 수정한 별도 O0/O2 실행이 통과했다. v1 실패와 v2 성공을 보존한 뒤 팀 검토로 입력군 oracle을 강화한 v3를 새로 실행했다. v3 compile/link 16회, fixture 6회, outer 호출 120회도 통과했다. 전체 세 시도의 compile/link 40회, fixture 15회, outer 호출 300회는 독립 기상 사례 수가 아니다. 세 compiler-version query는 compile/link 총계에서 제외했다.
- **RFMIP:** 기존 인증 historical diagnostic executable을 재사용한 SW standalone 1회, 새 compile 0회다. 누락된 8개 실패 셀의 prewrite를 캡처했고 candidate 전체 109800개 값/변수의 float32 비트가 보존됐다. 저장 strict 실패는 RSD13/RSU8 그대로다. 기존 13개와 합쳐 candidate prewrite 21개를 확보했지만 publisher 원본 prewrite는 아니다.
- **실행 identity:** 보존된 실제 connected-host 실행의 파일/프로세스와 현재 생산 bytes를 연결한 audit다. 새 WRF 예보 0회다. 최초 default `ldd` audit은 간접 NetCDF library를 찾지 못했고 명시적 audit LD_LIBRARY_PATH로 해결했다. 현재 library 조회를 과거 실행환경 인증으로 전용하지 않는다.

이 패키지에는 작은 receipt·stdout/stderr·prewrite binary와 소스 검토를 포함한다. 실행파일, 전체 NetCDF 결과, coefficient 원본, LBL raw stream은 외부 경로와 hash로 참조한다. 저장 verifier는 포함된 bytes와 21개 prewrite 산술을 검사하며, 외부 대형 파일을 다시 인증한 것으로 표시하지 않는다. 내부 hash manifest는 독립 trusted provenance 서명이 아니다.

## 회귀 보호와 물리 승인

[새 직접 UDM 시험](../../../WRF/test/rrtmgp/test_udm_native_ccn_bounds.py)은 CI에서 현재 소스를 새로 컴파일·실행한다. Historical RFMIP 자료는 현재 source hash로 덮어쓰지 않는다. 생산 미세물리·복사식, Registry 단위, 상수 cold-start 정책과 UDM27 전용 gate를 변경하지 않았다.

[모멘트·발생분율 표](evidence/size-occurrence-contract-matrix-v1.json)는 공식 데이터 계보를 [AER SVN revision 2174를 인용하는 첫 cloud data 커밋](https://github.com/earth-system-radiation/rte-rrtmgp/commit/39fb66b80fc69c70a15f6f15fb9b2c68d14f24b3)까지 좁힌다. 해당 계보만으로 정확한 pinned LUT PSD 생성식을 승인하지 않는다.

[LBL 후속 경계 정정](evidence/reference-next-step-review-v2.json)은 이미 끝난 v14 semantic review를 다시 제안한 오류를 바로잡는다. RFMIP의 8개 capture 제안은 이 패키지에서 실제 완료됐다. LBL source roster·initialized extent·완전한 음수 기원 및 물리 reference 승인은 계속 미완료다.

[최종 v3 범위 실행](evidence/native-bounds-v3/receipt.json)은 정확한 입력군·density·INPUT15/RETURN73/ENTRY5/EXIT6/TAGS2 폭과 dry 입력을 검사한다. [네 반례](evidence/native-bounds-oracle-negative-controls-v1.json)는 반복된 interior 입력군·잘못된 density·양의 condensate·짧은 반환을 거부한다. v2의 실제 입력은 올바른 범위를 포함했으며 이 보강은 향후 입력군 누락을 방지한다.

[LBL target별 소스 표](evidence/lbl-r1-r2-r3-source-census-v1.json)는 35개 attribution과 29개 고유 셀의 가능한 writer와 수명주기를 연결한다. 기존 v14의 35개 route10 XINT write는 별개의 event 집합이다. Runtime target hit·extent·panel ownership과 complete writer roster는 UNKNOWN이며, source 표로 물리 기준을 승인하지 않는다.

[팀 최종 소스 검토](evidence/remaining-contracts-source-ci-review-v2.json)는 v3·문서·CI 범위와 원래 acceptance19/current12 보존을 확인했다. 원시 stdout/binary는 팀이 재판독하지 않았으며 root의 저장 verifier와 구분한다. 보고서의 assembly manifest는 보고서 포함 전 검토 시점 값이고, 최종 포함 파일 roster는 이 폴더 manifest로 별도 봉인한다.

`evidence/audit-tools`는 실제 사용한 one-shot 도구의 byte 보존 사본이다. RFMIP/identity 도구는 원래 준비 폴더의 외부 경로를 요구하므로 이 사본의 위치에서 새 실행을 시작하는 launcher가 아니다. 현재 소스 재실행용 인터페이스는 `WRF/test/rrtmgp/test_udm_native_ccn_bounds.py WRF --workdir 새경로`이다.
