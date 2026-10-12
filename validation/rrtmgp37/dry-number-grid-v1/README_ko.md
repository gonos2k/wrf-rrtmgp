# dry-number-grid-v1 후보 구현과 검증

`udm_number_policy=1`을 선택하면 host QNN/QNC/QNR는 건조공기 질량당 number(kg⁻¹), UDM 작업배열은 체적 number(m⁻³)로 연결됩니다. 기본값 0은 이전 raw 동작입니다. 자체 선택한 연구 정책이며 NOAA 원래 규약 인증이나 물리적 생산 승인이 아닙니다.

한 호출의 dry density를 저장하여 `n=rho_call*eta`로 입장하고, 기존 native 제한·미세물리·반경/반사도 계산을 마친 다음 `eta=n_final/rho_call`로 반환합니다. 다음 호출에는 그때의 밀도를 새로 사용합니다. host에 체적 number를 임시로 써 넣지 않으며, 새로운 최종 clipping이나 CF 배율을 넣지 않습니다. Cold start의 물리적 CCN 배경은 `ccn_conc/rho_d`로 저장합니다. 밀도가 정의되지 않은 비소비 halo/top 메모리는 0으로 두며, 물리 호출 영역의 invalid density는 거부합니다.

입력·경계·restart 파일은 `UDM_NUMBER_POLICY`를 선언해야 합니다. 누락은 legacy 0으로만 해석하며, 파일과 namelist의 표현이 다르면 양방향으로 거부합니다. History/checkpoint에는 표현을 기록합니다. **기존 raw checkpoint의 자동 migration은 없습니다.** 새 number를 생산하지 않는 real/ideal 및 boundary writer는 policy1 표기를 붙이지 못하도록 명시적으로 거부합니다. 시험의 제조 cold input은 알려진 체적 number를 별도 Python producer로 eta로 바꾸고 그 파일에만 표기를 붙였습니다. 일반 legacy raw의 단위 추론이나 외부 QNN 보존 기능이 아닙니다.

## 실제 수행한 최종 적격 검증

- GNU O0/O2, 두 dry density, partial CF와 partial activation, 해당 cap/floor 비활성 조건: 전체 UDM의 32개 제조 paired case, 64회 호출. 동일한 rounded 체적 입력을 받은 control과 native 과정/반경이 동일하고 host 반환은 native 결과/rho와 비트 일치합니다.
- 무과정 반환, 같은 물리적 cold CCN 배경, 기존 체적 입구 제한을 별도 비교했습니다.
- 새 GNU serial REAL32 SCM 빌드, 한 periodic 2×2×59 제조 상태: 120초 control와 60초 checkpoint 재개에서 최종 history 변수 211개 비트 일치.
- 실제 정책 표기가 없는 cold/restart, eta 파일을 legacy로 읽는 세 요청과 잘못된 타입의 정책 표기를 거부했습니다. 이 serial 빌드의 fatal도 RC0이므로 RC만으로 판정하지 않고 fatal/성공 문구와 산출물을 확인합니다.
- 실제 ideal producer의 잘못된 policy1 표기 거부를 확인했습니다.
- 12개 실제 미세물리 호출의 number encoding/density/radius tuple을 읽었습니다. Cold 59층은 `1e8/rho`와 비트 일치하고, 재구성된 체적 number로 액체 radius를 대조한 372층의 최대 상대차는 약 4.52e−7입니다. `NATIVE_NC_RECONSTRUCTED`는 반환 eta에서 재구성한 값이며 private helper 피연산자의 직접 관측이 아닙니다.
- Capture OFF/ON history 전체 bytes가 같습니다. 기본 legacy 경로도 이전 GNU 실행파일과 새 실행파일의 211개 history 변수, 13개 시각에서 비트 일치합니다.

이는 한 제조 SCM과 직접 UDM 시험입니다. 비주기 경계·nested/MPI·새 수송 옵션, 실제 대기 PSD/발생분율·독립 정확도·장시간 예보를 승인하지 않습니다. 새 WRF 계산과 기존 #169 얼음 민감도 계산은 합산하지 않습니다. 최종 후보는 WRF 8회(네 정상 실행과 네 의도적 거부), 별도 ideal 1회 거부입니다. 이전 실행파일의 legacy control 1회는 별도 비교이며 `saved/process-accounting.json`에는 분석기/빌드 수정 전 시도도 따로 보존합니다.

## 과거 증거와 새 소스

과거의 source pin은 변경하지 않았습니다. 당시 소스 bytes를 `../historical-source/`에 보존하여 이전 연구 계약과 #168/#169 replay를 실행합니다. 현재 tree는 이전 profile의 현재 실행 근거로 승인되지 않습니다. 새 정책의 현재 7개 변경 소스, executable, 설정·입력·결과는 이 package의 별도 identity에 연결합니다. 변경되지 않은 5,894개 기존 corpus 파일은 이전 corpus와 비교합니다. 추가 9개 standalone fixture에는 새 fatal 함수의 테스트용 출력/종료 dependency를 연결했습니다. 이는 후보 실행의 제한된 identity이며 FINAL-IDENTITY 종료가 아닙니다.

```sh
python3 WRF/test/rrtmgp/test_udm_dry_number_bridge.py WRF --workdir /new/scratch/module-test
python3 WRF/test/rrtmgp/test_udm_dry_number_scm.py WRF --exe /new/build/main/wrf --seed /known/manufactured/seed --workdir /new/scratch/scm
python3 -I -S validation/rrtmgp37/dry-number-grid-v1/verify_saved.py
python3 -I -S validation/rrtmgp37/dry-number-grid-v1/test_saved.py
```

CI는 저장 자료 재생이며 새 Fortran/WRF solver 실행이 아닙니다.

## 기존 종료 조건

`closure-conditions.json`의 일곱 조건을 유지합니다. PHY-NC의 선택한 bridge 후보 구현과 기계적 검증은 완료했습니다. Native 부분구름 과정의 population/가정, 입력 authority, 첫 과학 지원 범위의 승인은 별도입니다. PHY-SIZE/PHY-OCCURRENCE, RFMIP/LBL FAIL, FINAL-IDENTITY, FINAL-FORECAST를 유지하며 `production_accepted=false`입니다.
