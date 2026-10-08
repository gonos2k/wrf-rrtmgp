# 실제 격자·약선 기준 대조: 음의 OD 유지

PR164 main `8eb96d2b7676eff152bf3563dc030bb924c3a4a9`, tree `14b2c6ca35e7f75071aed2d71a2c51690fee92cd` 이후의 검증이다. 기존 선택 line/폭/모든 R3 write 연결을 다시 미완료로 돌리지 않는다. 생산 WRF/UDM/RTE·Registry·초기화·광학계수·허용오차는 변경하지 않는다.

root가 GNU13.3 double LBLRTM v12.17을 make1회 빌드하고, 같은 실행파일로 OFF1/ON5의 solver6회를 실제 실행했다. 그 전에 이전 PR164 실행파일의 OFF probe1회를 수행했다. 일곱 solver 모두 RC0/REAPED이다. LNFL/WRF 실행은 없으며 독립 기상 사례 일곱 개라는 뜻이 아니다. runner는 timeout600초, trace32MiB, case3GiB 상한과 예외 시 process-group 종료/회수를 적용한다. 실행 종료 후에만 원시 출력을 읽었다.

## 정확한 비교 설정

모든 비교 실행은 공식 `IOD=2`, `IMRG=1`의 exact layer DV 경로를 사용한다. 기본 `IOD=0`에서는 interlayer DV 반올림 때문에 SAMPLE만4/8/16으로 바꿔도 실제 DV가 정확히 h/h2/h4가 되지 않는다. 이번에는 IOD2를 모든 대조에서 고정하고, SAMPLE4/8/16으로 실제 layer21 DV를 `0.003941167029890377`, `0.0019705835149451886`, `0.0009852917574725943`으로 만들었다. ALFMAX는 세 격자에서 `0.06305867247824604`로 같다.

기존 역사적 파수 `618.6144711111115 cm-1`가 새 exact grid에 놓이지 않으므로, probe의 실제 panel 시작점/DV에서 공통 R3 격자점 `618.6133629315808 cm-1`을 선택했다. 이동은 `-0.001108179530660891 cm-1`이다. 이것은 과거 선택점을 대체하거나 과거 OD를 재평가한 결과가 아니다. 과거 IOD0의 OD `-0.009028119955355695`와 REF-LBL FAIL은 보존한다.

원래45층 TAPE5에서 IOD/SAMPLE/DPTMIN의 명시적인 세 필드만 바꿨다. 대기상태와 다른 설정·37개 부속 입력·TAPE3는 같다. `DPTMIN=-1`은 공식 기본값 `0.0002`, `2e-5`는10배 낮춘 값, `0`은 실제0이다. 이 실행의 JRAD0/RADFN 고파수 분기에서 DPTMN은 각각 `8.88888888888889e-8`, `8.88888888888889e-9`, `0`이다. 명목0을 기본값으로 해석하지 않는다. Coupling/continuum은 원래 구성대로 함께 유지했다.

## 실제 결과

| ON 실행 | DV | LNC 통과/거부 | R3 write가 있는 선 / 비영 곱 항이 있는 선 | 선택 OD |
|---|---:|---:|---:|---:|
| h | 0.003941167029890377 | 2779 / 2092 | 1011 / 987 | -0.008768587504714919 |
| h/2 | 0.0019705835149451886 | 2779 / 2092 | 1001 / 987 | -0.008768587417547139 |
| h/4 | 0.0009852917574725943 | 2779 / 2092 | 994 / 987 | -0.00876858741755266 |
| h, 약선 기준/10 | 위 h와 동일 | 2932 / 1939 | 1069 / 1045 | -0.008762561700804932 |
| h, 약선 기준0 | 위 h와 동일 | 4871 / 0 | 1837 / 1802 | -0.008760491872701745 |

관측은 layer21에서 목표 ±5 cm-1 안의 LNC 진입4871개/실행과 실제 목표 R3의 모든 CN_WRITE를 연결한다. Panel 번호는 격자에 따라 달라져 고정하지 않는다. 새 observer는 물리 파수만 선택하고, 이전 panel14 전용 FINAL_OD stencil은 사용하지 않는다. 초기 탈락에서 정의되지 않은 값을 읽지 않도록 거부 OUTCOME은 native SPPSP=0 뒤에 기록한다. 네 observer 편집을 역적용하면 PR164 소스 bytes가 복원된다. native 대입 순서를 바꾸지 않았다.

세 격자의 R3 write 목록에서 추가/탈락한 항은 모두 곱이0인 lookup 끝점 항이다. 비영 곱 항을 가진987개 선의 집합은 같고 공통 선의 폭도 같다. 따라서 write 개수 차이를 비영 흡수 성분의 누락으로 설명하지 않는다. 기존 약선 기준에서 실제 R3 기여 선의 폭 제한은 세 격자 모두0이다. 약선 기준0에서는 새로 포함된 선 중 하한 제한1개가 있다. 이전의 unclamped 결과를 새 입력군에 일반화하지 않는다.

선택점의 h/2→h/4 OD 차이는 약 `-5.52e-15`이나, 목표±40h의81개 공통 OD 표본에서 최대 차이는 `2.68886e-4`다(h→h/2는 `7.81376e-4`). 81개 중51개가 모든 대조에서 음수다. 따라서 선택점의 안정성을 전체 구간 수렴이나 물리 승인으로 승격하지 않는다. 수렴 허용기준도 사후에 만들지 않는다.

약선 기준/10과0은 R3 write 선을58개/826개 늘리지만 선택 OD 증가량은 약 `6.03e-6`/`8.10e-6`이고 여전히 음수다. R3 공통 선의 곱 항은 변하지 않았다. 최종 OD 변화 전체를 R3 변화만으로 설명하지 않는다. 직접 R1/R2·continuum 등도 계산에 들어간다.

## 원시 판독과 저장 CI의 범위

root는 probe/새 OFF/새 ON의45개 OD 전체를 실제 다시 읽어 FILHDR 이후57007개 record가 모두 같음을 확인했다. FILHDR 차이는 해당 레이아웃의 날짜·시각16바이트 안이고 전체 파일 FAIL은 유지한다. 이전 실행파일 probe와 새 observer OFF가 같다는 검사도 포함한다.

root는 다섯 ON 실행의 실제 layer21 OD를 읽고 공통81개 물리 파수의 원시 panel header/payload를 발췌했다. 격자점의 floating coordinate 잔차1e-7 cm-1 이내에서 같은 파수 표본을 연결하며 비교용 추가 보간은 하지 않는다. 실제 좌표의 요청점 잔차 및 격자 간 최대 차이는1.13687e-13 cm-1이고 선택점의 실제 좌표는 모든 실행에서 비트 동일하다(`coordinate-diagnostic.json`). 전체 layer21 파일을 읽었지만 아래 판정량은81개 표본으로 한정한다. 다섯 ON 모두의 전45층 과학 정확도를 새로 승인한 것은 아니다.

TAPE3의 필요한 data/header 기록은 실제 marker와 함께 판독하고 line-use 원래 centre/strength/species/flag를 record/slot에 연결한다. 전체 파일 SHA도 확인하지만 PR163 공급 roster census를 반복한 것은 아니다.

저장 CI는 포함된 trace·실제 TAPE3 발췌·OD panel payload·입력·영수증을 재생한다. 새 solver/원시45개 OD 전체/TAPE3 전체를 CI에서 실행·재판독하지 않는다. 날짜·시각 passivity 요약은 원시 readback 당시 root의 결과이며 CI는 그 범위·집계·hash 연결을 검사한다. 여섯 반례는 DV, 물리 파수, 명목0 threshold, 대상 write 누락, 실제 OD payload 변경, 물리 승인으로의 승격을 거부한다.

```
python3 -I -S validation/rrtmgp37/lbl-grid-threshold-comparison/verify_saved.py
python3 -I -S validation/rrtmgp37/lbl-grid-threshold-comparison/test_saved.py
```

`root-execution/`은 실제 사용한 runner/preparation/readback 스크립트이다. 새로운 경로에서 실행하려면 명시된 historical input·stage·NetCDF 환경을 준비해야 한다. 이 저장 package만으로 전체 solver를 재빌드할 수 있다고 주장하지 않는다.

## 체크리스트 판정

선택 exact-DV 구성의 격자·약선 기준 대조 **실행 하위 과제는 완료**다. 선택점 음수는 grid refinement와 실제 SPEAK threshold0에서도 남는다. 전체 window의 수렴, 원 mixing 근사의 수용성·물리 partner 완전성·독립 reference·band/flux 검증은 완료가 아니다. 이후에는 해당 모델/성분의 물리적 적용성과 window 오차를 겨냥한다. 같은 대조를 새로운 미완료 항목으로 다시 만들지 않는다.

완료15/물리·최종 미완료7, REF-LBL FAIL, RFMIP published strict21 FAIL, `production_accepted=false`를 유지한다. QNN 초기화·단위·population와 PSD/LUT 정책은 별도 OPEN이다. 생산 정책을 미승인 LBLRTM에 맞춰 보정하지 않는다.
