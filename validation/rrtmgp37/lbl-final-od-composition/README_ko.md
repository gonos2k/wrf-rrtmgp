# 같은 실행의 선택 R3→R2→R1→최종 OD 연결

선택한 layer 21, 파수 **618.6144711111115 cm⁻¹**에서 continuum 이후 R3와 PANEL의 두 단계 합성, 실제 RADFNI 배율, 저장 OD를 연결했다. 최종 OD는 **−0.009028119955355695**이다. 이 자료는 그 음수를 고치거나 물리적으로 승인한 결과가 아니다. **REF-LBL FAIL과 production_accepted=false는 유지한다.**

기준 main은 PR161의 `4c97d835ef5169f5f55262d1b34cb096c182318c`, tree `fb15a10670f77406c8489fa85c9548ebe07724cc`이다. PR160의 최초 음수 경로와 PR161의 TAPE3 내부 line·sidecar 및 계수 산술은 완료된 하위 근거로 유지한다. 새 관측 블록을 제거하면 PR161 관측 source의 원래 bytes를 정확히 복원한다. 생산 WRF/UDM/RTE, Registry, CCN 정책, 광학계수, tolerance, UDM27 전용 조건은 변경하지 않는다.

## 이번에 실제로 수행한 작업

GNU Fortran 13.3 double 구성에서 LBLRTM make 2회, solver 4회가 RC0으로 종료·회수됐다. Version1은 합성 snapshot의 예비 실행, version2 OFF/ON 두 실행은 continuum 입력 stencil까지 포함한 최종 증거다. 첫 실행기 준비 때 donor plan 파일명을 잘못 바꾼 실패는 자식 실행 전에 발생했다. Version2 make 성공 뒤에는 기존 version1 기록명과 충돌해 기록을 거부한 실패가 있었으며, 성공 빌드를 유지하고 object 검증과 solver 실행부터 재개했다. 실패 기록과 원래 실행기를 별도로 보존한다. 추가 make를 한 것으로 집계하지 않는다.

성공 빌드에서 `oprop.o`만 달라졌으며 stock의 다른 20개 object는 동일했다. 같은 실행파일의 관측 OFF/ON, 같은 입력·설정의 PR161 출력 45개를 root가 직접 열어 Fortran record marker와 과학 record **53,279개**를 대조했다. FILHDR 이후 record는 모두 동일했다. 전체 파일 bytes의 FAIL은 날짜·시각 16바이트 차이로 보존한다. PR161의 MIN_R3와 LINE_COEFF trace도 전체 bytes가 동일했다. 이는 pristine 생산 실행파일과의 비교나 새 WRF 예보가 아니다.

## 선택 파수의 실제 값

| 단계 | 실제 값 |
|---|---:|
| R3(20), continuum 전 | −2.5643980319365688e−5 |
| 해당 continuum 증가량 | +8.775708875840199e−6 |
| R3(20), continuum 후 | −1.686827144352549e−5 |
| R2(77), R3 합성 전 | +1.1890094049754419e−6 |
| R2(77), R3 합성 후 | −1.567926203855005e−5 |
| R1(305), R2 합성 전 | +4.810988582819415e−7 |
| R1(305), R2 합성 후 | −1.5198163180268107e−5 |
| 실제 복사장 배율 | +594.0270444705432 |
| 출력 OD, panel14 sample273 | **−0.009028119955355695** |

세 격자의 좌표 `VFT+304*DV`, `VFT+76*DVR2`, `VFT+19*DVR3`는 같은 binary64 파수다. OD header의 sample273 좌표도 대조한다. R3, R2, R1은 합성 전의 내부 성분이므로 최종 dimensionless OD와 동일한 양으로 부르지 않는다.

관측 범위는 R1 289–324, R2 72–84, R3 17–24이다. 실제 54개 기록을 고정한 순서·폭·층·panel로 검사한다. 8개 continuum 목적지의 실제 4점 입력 stencil, 정의된 NPTABS 범위, 보간 계수와 더하기를 재생한다. R3→R2 13개와 R2→R1 36개는 direct 및 세 polynomial residue를 포함한다. 이어 실제 곱셈과 OD payload 값 36개를 대조한다. **총 361개 산술·값 연결 검사**이며 기상 사례 수가 아니다. 선택한 36개 중 31개가 음수다.

R4는 비활성, JRAD=0, DVOUT=0으로 관측됐다. XSECTM은 활성화됐지만 이번에 관측한 배열 구간은 호출 전후 비트가 같았다. 이는 다른 파수나 층에서 cross-section이 0임을 보장하지 않는다. Continuum 외 추가 기여를 0으로 가정하지 않고 실제 호출 전후를 확인했다.

## 포함 자료와 재생 범위

`trace.txt.gz`는 실제 관측 trace다. `excerpts/`는 실제 ODdeflt_021의 물리 순차 record 1(FILHDR), 28(panel14 header), 29(2,400개 OD)을 그대로 압축한 자료다. 합성으로 만든 NetCDF나 JSON 값에서 다시 만든 OD가 아니다. `OD-readback.json`은 전체 파일 hash와 발췌 위치를 기록한다. source·patch·실행기·환경·object 비교·로그·초기 실패를 함께 보존한다. 실행파일, 전체 TAPE3, 전체 45개 OD는 이 작은 package에 포함하지 않는다.

```sh
python3 -I -S validation/rrtmgp37/lbl-final-od-composition/verify_saved.py
python3 -I -S validation/rrtmgp37/lbl-final-od-composition/test_saved.py
```

저장 검사와 CI는 포함된 실제 trace·OD panel을 재생하고 parent package와 source 복원을 검사한다. 전체 45개 OD 재판독, solver·WRF 재실행은 하지 않는다. 파일 전체 비교 metadata의 검사는 원시 전체 readback을 대신하지 않는다. 여섯 반례는 연산 누락, continuum stencil, 좌표, R2 합성, 실제 radiation 배율, 실제 OD 한 ULP 변조를 거부한다.

## 종료한 하위 경계와 남은 경계

**종료:** 같은 입력·같은 실행에서 선택 R3 음수 성분이 continuum, 주변 stencil과 기존 R2·R1 성분, radiation 곱셈을 거쳐 최종 OD 파일까지 연결되는 수치 경계. 이 선택점에서는 필수 합성을 적용한 뒤에도 음수가 남는다.

**남음:** 원 Y/G 분광계수의 upstream 근거와 선택·절단 범위, 주변 개별 선 및 모든 성분의 독립적 물리 생성 검증, 전체 spectrum/reference 수용성, 분광 적분·복사 플럭스 영향. 기록된 continuum 입력과 RADFNI 배율을 사용하는 것은 그 생성의 독립 검증이 아니다. 모든 주변 line의 항을 각각 추적한 자료도 아니다. Signed coupling을 제거하거나 clipping하지 않으며 미승인 LBLRTM에 맞춰 UDM 반경이나 RRTMGP 계수를 보정하지 않는다.

이 하위 PASS로 기존 15개 제한적 완료/7개 물리·최종 미완료를 바꾸지 않는다. QNN 초기화·단위·population, PSD/LUT, 발생분율, RFMIP strict21, 최종 실행 identity 및 장시간·관측 평가도 별도로 남는다.
