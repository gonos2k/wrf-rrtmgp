# UDM37 연구 실행 계약과 물리 승인 전 점검

기준 main은 PR166 `d74f8e9b185bbc407156b6a7dd930dd2f1c03929`, tree `41223688a2488c93593a78f631c4c0ab4eba5d4c`이다. 이번에는 새 분광 표본이나 모델 실행을 늘리지 않고, 기존 상수 CCN 경로의 **제안 연구 구성**과 미승인 물리 정의를 하나의 기계 판독 계약으로 묶었다. 생산 WRF/UDM/RTE·Registry·초기화·반경·광학계수는 변경하지 않는다.

[profile.json](profile.json)은 기존 연결 시험의 연구 baseline을 한정한다. 첫 과학 승인 범위의 선택은 별도 결정이며, 현재 `PROPOSED_SCOPE_NOT_PHYSICS_APPROVAL`이다. [정책 결정표](DECISIONS_ko.md)는 확인한 구현·이 연구 profile의 선택·승인에 필요한 정의를 구분한다. 일곱 최상위 종료 조건은 [closure-conditions.json](closure-conditions.json)에 원문 그대로 고정했다.

## 구체적인 연구 범위

UDM27/LW37/SW37, scalar_adv_opt0/RK3/수평5차·수직3차, periodic domain1, overlap2, frozen mode0, 원래ccn_conc raw1e8의 보존된 cold/restart 설정을 참조한다. Frozen mode0와 ice roughness1은 명시 키가 없는 실제 namelist에서 Registry default로 해석된다. 변수를 새로 파싱하는 범용 namelist 도구가 아니라, **정확한 기존 namelist bytes와11개 관련 source 파일**을 연결하는 참조 profile이다. 다른 설정이 틀렸다는 판정이 아니라 이 profile 밖이라는 판정이다. 다른 설정에는 별도 명시적인 profile·근거가 필요하다.

Number encoding은 `UNRESOLVED_NATIVE_RAW`이다. Cold 첫 driver 상수 reset과 확인한 checkpoint 복원을 구분하며, 외부 QNN 공간분포를 활용하는 정책으로 표시하지 않는다. NC/NR/CCN의 내부 체적 단위 근거와 Registry kg-1 표기는 함께 기록하지만, 새ρ/CF 배율이나 이름만 바꾸는 단위 승인은 하지 않는다. CCN 입구clip을 모든 후속 과정의 반환 불변량으로 확대하지 않는다.

Native 반경은 그대로 쓰며 임의 배율은 없다. PSD/LUT 모멘트·입자 집단은 미승인이다. L/I/R/S의 공유CF·CF0 omission은 현재 구현된 **연구 가정**으로 명시한다. Frozen mode0의 양성graupel은 광학 소비가 없고 양성hail은 거부되므로, 이 참조 profile은 확인한 snapshot의qg=qh=0에 한정한다. 현재 mode1 실험 기능을 삭제하거나 WRF 일반 지원을 부정하는 규칙이 아니다.

## 실제 저장 NetCDF 판독

root가 이미 보존된 manufactured connected-host warm-cloud의 input/history/restart **3개 NetCDF**를 NetCDF4로 직접 해제·읽었다. History의 두 시각을 포함해4개 상태에서10개 변수의236셀 binary32 배열을 추출했다. `readback-environment.json`은 사용한Python/NumPy/NetCDF 버전을 기록한다. Compiler/WRF/UDM/RTE/LNFL/LBLRTM 실행은0회다.

초기 input은CF=0에서 양성QCLOUD124셀이나 아직CF 진단 전이다. 이를 실제 복사 누락이나 물리 오류로 판정하지 않는다. 60초 history/checkpoint에는QCLOUD124셀·QICE36셀·QRAIN84셀이 양수이고, CF=0 양성QICE는12셀이다. QGRAUP/QHAIL은0이다. **Warm-cloud 초기 입력이60초 이후에도 액체만 가진 상태라는 가정은 맞지 않는다.**

CF0 양성QICE12개는 저장 snapshot의 실제 조건이다. Radiation caller의 실제 사용 시점·CF/radius tuple·dry layer mass·omitted optical path를 이번에 측정한 것은 아니므로 **실제 입자/질량/플럭스 손실량으로 부르지 않는다**. Audit 출력에도 potential snapshot omission과 direct_radiation_call_state=false를 명시한다. 현재 LW/SW caller의allow_clear_condensate=true라는 소스 정책과 구분한다.

CI는 기존 raw gzip/CDF 전체 bytes의 hash와 root가 추출한binary32 packet·집계·단위 attribute를 검사한다. CI에서 NetCDF 변수를 독립적으로 다시 해석한 것은 아니다. Root의 source 데이터 판독과 stdlib packet 재생을 분리한다. 파일의kg-1 attribute는 기록일 뿐 물리 단위 규약의 승인으로 사용하지 않는다. 체크한4개 snapshot을 모든 RK step/모든 실제 복사 호출의 상태 허용성으로 확대하지 않는다.

## 실행 가능한 점검

```
python3 -I -S validation/rrtmgp37/research-policy-contract/audit_profile.py --purpose research
python3 -I -S validation/rrtmgp37/research-policy-contract/audit_profile.py --case restart-on --purpose research
python3 -I -S validation/rrtmgp37/research-policy-contract/audit_profile.py --purpose physical
```

Research 요청은 해당 source/configuration·저장 상태 참조가 맞으면 `PASS_SCOPED_RETAINED_RESEARCH_PROFILE`, RC0이다. 이것은 새 모델 실행이나 실행파일/library의동시 identity 인증이 아니다. 물리 요청은 `REJECT_PHYSICAL_ACCEPTANCE`, **의도된 RC2**다. 미완료7개와 종료 조건을 함께 출력한다. 단위·population 승인, optical moment 승인, 최종 reference/예보 없이 research용의greenCI를production 승격으로 사용할 수 없다. 체크리스트 label만PASS로 바꿔도 이 연구-only 버전은 물리 사용을 승인하지 않는다.

`--namelist`는 exact reference binding 점검용이며 실행 설정을 편집하지 않는다. `--number-policy preserve_external`은 현재 상수 reset 정책과 충돌하므로 거부한다. 외부 보존 기능을 구현했다는 뜻이 아니다. 고정 profile을 다른 물리 정의로 조용히 재해석하면 거부하며, 실제 정책 변경은 새로운 version과 전체 경계·호환성 검증이 필요하다.

```
python3 -I -S validation/rrtmgp37/research-policy-contract/verify_saved.py
python3 -I -S validation/rrtmgp37/research-policy-contract/test_contract.py
```

다섯 시험은 실제 cold/restart와CF 진단 전/후 구분, 외부 보존·단위 재명명, 다른 수송 설정, 양성G/H, documentary label 변경 후 물리 요청을 검사한다. 새로운 generic parser 예외나새 P2를 만들지 않는다. 기존 acceptance test entry가 두 명령을 호출하며 workflow 파일은 바꾸지 않는다.

## 승인과 다음 결정

기존 수농도 연결·CCN 범위·분광 계보·격자/약선 대조·161/321 판독의 완료 범위는 유지한다. 이 profile·guard 하위 작업도 완료로 기록하지만 **최상위 일곱 항목은 승인하지 않는다**. 원래19/current12 승인 index와 완료15/미완료7, RFMIP strict21 FAIL·REF-LBL FAIL, `production_accepted=false`를 유지한다.

최초 지원 정책을 기존 상수 CCN으로 정하더라도 PHY-NC의 단위/집단이 자동으로 승인되는 것은 아니다. 외부 보존을 선택한다면 첫 reset뿐 아니라 초기·경계·수송·내부 제한·과정·반환·restart의같은정의를 마련해야 한다. 자체η=n/ρ_d 가설은 NOAA 원래 의도 확인과별도로 version을 붙인다. Native optical size와 LUT 모멘트, CF0/입자 가정, independent reference와최종평가는별도승인근거가필요하다.

[공식 UDM 도입 소스](https://github.com/wrf-model/WRF/blob/5fc76c540631be296bd2312e1d96117c07cbf761/phys/module_mp_udm.F), [기존 NOAA 근거](../nc-noaa-primary-contract/README_ko.md), [RRTMGP effective-radius interface](https://earth-system-radiation.github.io/rte-rrtmgp/reference/rrtmgp-fortran-interface/sourcefile/mo_cloud_optics_rrtmgp.f90.html)를 따른다. 이번 공개 검색에서 이 미확정 host 계약을 닫는 새 근거는 확보하지 못했다. Primary source의 존재와 현재 물리 승인을 동일시하지 않는다.

`root-readback.py`는 원래 작업공간용 실제 판독 스크립트의보존사본이며NetCDF4/NumPy가필요하다. 저장소 재생에는stdlib verify_saved.py를 사용한다. 내부manifest/hash는byte연결·일관성근거이며외부독립신뢰서명은아니다.

## 이후 소스 변경과 보존 자료 재생

`--source-scope current`(기본)는 여전히 당시 11개 소스와 현재 tree가 일치해야 합니다. 새 opt-in number 후보가 추가된 tree는 이 legacy profile의 현재 실행 근거로 승인하지 않습니다. `--source-scope retained`는 원래 source pin을 변경하지 않고 `historical-source/`의 611837c6 원본 snapshot으로 과거 결과를 재생합니다. 새 정책의 실행 근거는 `dry-number-grid-v1/`에 따로 둡니다.
