# 실제 UDM fractional-CF 임시 population 관측

이 패키지는 **물리 방정식을 바꾸지 않은 private 관측 소스**의 실제 2분 OFF/ON 실행과 저장 자료를 보존합니다. 두 모델이 모두 RC0로 종료·reap됐고, root의 사후 process-group 검사에서도 잔여 구성원이 없었습니다. history 231변수 및 restart 668변수는 전체 파일 바이트, 배열, schema, attrs가 OFF/ON에서 정확히 같았습니다. 이것은 같은 관측 소스의 passivity이며 원래 uninstrumented executable 또는 물리 진실과의 동일성 주장이 아닙니다.

새 input은 PR143에서 이미 실행한 supersaturation 입력4be를 복사한 뒤 QCLOUD[Time0,k6,j1,i22] 한 원소만 REAL32(1e-4)로 바꿨습니다. 전체 197변수의 메타데이터, 나머지196배열 및 QCLOUD 다른 모든 원소가 보존된 검토를 함께 둡니다. 이는 4be에 대해 QC 하나의 개입이며 원래849f 입력에 대해서는 승계된 QV 변경까지 포함한 두 개의 개입입니다.

관측은 native UDM에서 CF를 계산한 뒤 여섯 질량을 CF로 나누기 전/후, 중간 녹음·동결 과정 뒤 곱하기 전/후의 네 checkpoint입니다. NN/NC/NR은 단위 승인 없는 원문 raw 값으로 기록했습니다. 새 `.cfpop` 8개/352층, NUMBER 20개/880층, QNN 24개/1056층은 모두 이 새 실행의 자료입니다. 이전 all-zero QNC 또는 activation packet을 새 양성 증거로 조인하지 않습니다.

| 실제 i23/j2/k7 | step1 | step2 |
|---|---:|---:|
| predivision CF | 0.6835536957 | 0.9798682928 |
| predivision QC | 0.0001212107163 | 0.0001853906724 |
| raw NC before division | 99186352 | 196143984 |
| helper QC | 0.0001881706703 | 0.00002366141416 |
| helper raw NC | 199167296 | 196090928 |
| returned cloud radius (m) | 6.220532669e-6 | 3.135956149e-6 |

두 step 모두 실제 predivision QC/NC>0, 0<CF<1과 양의 helper 입력을 관측했습니다. 즉시 나누기/곱하기 쌍의 여섯 질량 원문 REAL32 연산 1056개와 NN/NC/NR 불변 검사 528개가 exact입니다. phase2→3에는 실제 미세물리 과정이 있으므로 질량·수농도의 불변 또는 전체 역변환을 요구하지 않습니다. NUMBER23↔predivision 88층 및 return40↔helper50↔helper51 176층 상태 조인이 exact입니다. helper/history 여섯 profile 및 CF profile·epoch·top은 원본 NetCDF를 독립적으로 읽은 616개 field 확인으로 보존합니다. CF는 앞선 진단 시점이며 helper 시점에 다시 계산한 값이 아닙니다. source top 위 CF=1은 작업배열 초기값으로 구분하며 진단된 구름덮개라고 주장하지 않습니다.

준비 certificate의 CF≈0.580050826은 QC=1e-4/QI=0을 그대로 source 식에 넣은 **조건부 계산**입니다. 실제 transport/미세물리 후의 predivision QC가 달라져 위의 실제 CF를 관측했습니다. 원문은 dxmeter=10000을 사용하며 이는 실제 WRF 격자 간격도, 50/100km 식의 외삽을 물리적으로 승인한 근거도 아닙니다.

원본 model/source/input/receipt는 exact copy, 두 큰 JSON과 source patch는 timestamp0의 lossless gzip으로 보존합니다. `origins.json`은 원문 및 저장 바이트의 SHA/size를 각각 연결합니다. parent PR143 패키지의 고정 manifest와 필요한 source를 재사용하며, 부모 UDM+patch를 재구성한 SHA 및 다섯 observer marker 제거 후의 부모 전체 바이트 일치를 검사합니다. 새 full UDM 사본은 중복 배포하지 않습니다.

private build commit11623344/tree8e9d6aea의 실제 configure/build/install 세 RC0와 새 wrf executable b340f016...fc59를 바인딩합니다. `build/public-build-identity.json`은 source/tree, 명시적 flags, 실제 configure 로그의 compiler 표시, toolchain/library 핀만 선별한 **파생 공개 메타데이터**입니다. full controlled_env, 내부 IP/네트워크 구조, session metadata, authorization 내용 및 원문 private build plan은 공개하지 않습니다. 원본 private plan SHA는 보존하지만 CI에서는 그 private 파일이나 compiler를 재실행·재구성한 것으로 표현하지 않습니다. 정확한 compiler binary identity까지 입증하는 증거가 아니라는 원래 source review 한계도 유지합니다.

저장 증거 검증은 표준 라이브러리만 사용합니다. 다른 cwd에서도 아래 absolute 경로 호출이 가능합니다.

```bash
python3 -I -S /path/to/repo/validation/rrtmgp37/fractional-cf-population/verify_saved.py --output /tmp/cf-verification.json
```

`--output`은 새 파일이어야 합니다. verifier는 닫힌88 payload 목록, 저장/압축 원문 SHA, parent source/manifest, 즉시 binary32 연산, packet identity와 QNN 원문 분기/밀도식 및 실제 receipt 관계를 확인합니다. 큰 NetCDF와 executable/library/input 파일은 패키지에 없으므로 whole-file/NetCDF 비교는 원본 실제 실행 및 독립 검토 receipt를 검증하는 범위입니다. 새 모델·compiler·RTE, libm table 또는 native radius 식의 독립 재실행을 하지 않습니다. workflow가 먼저 외부의 고정 manifest SHA를 확인한 뒤 이 saved-only verifier를 실행합니다. CI PASS는 새로운 forecast 또는 물리 PASS가 아닙니다.

복사된 계획/준비 파일의 PREPARED·UNRUN 등은 **그 파일을 쓴 당시**의 원문 메타데이터입니다. `scope.json`의 state_at_package_creation도 생성 시점 값입니다. `scripts/run_once.py`, staging script 및 독립 NetCDF audit는 실제 실행했던 역사적 원문이며 private absolute 경로·선행 자료를 사용합니다. 패키지 위치에서 곧바로 모델을 재현하는 CLI가 아니고, 재현하려면 별도로 검토한 경로·출력 조정과 원래 자료가 필요합니다. 이동 없이 직접 재사용되는 saved parser는 `scripts/validate_cf_population.py`, CI entry는 `verify_saved.py`입니다. 과거 private authoring/pin 오타 실패는 별도로 보존됐고 새로운 과학 실행으로 계산하지 않습니다.

**Nc/CCN 단위 권위, PSD/LUT population, CF 외삽 물리 타당성, RFMIP strict FAIL, LBL negative-OD FAIL 및 forecast/flux 진실은 여전히 미완료입니다.** 이 패키지에는 density correction, population correction, optical/PSD 정책 변경 또는 scientific acceptance가 없습니다. 큰 model 파일·raw 외부 linebank/TAPE3/계수 벡터·executable/library·authorization JSON·signed URL은 포함하지 않습니다.
