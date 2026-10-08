# RFMIP 저장 정밀도 비교의 의미

PR158은 candidate prewrite 21개를 확보했다. 이 자료의 저장 출력 strict 실패는 RSD13·RSU8 그대로다. 기존 출력 키 `candidate_precast_strict_fail=14`는 **candidate binary64 prewrite 대 published reference의 저장 binary32 값**을 비교한 개수다. Publisher의 원래 prewrite와 비교한 실패 개수가 아니다.

| 비교 | 현재 결과 |
|---|---|
| 저장 candidate와 저장 reference | strict FAIL 21개 |
| Candidate prewrite와 저장 reference | 혼합 정밀도 strict 초과 14개 |
| 같은 저장 reference를 고정한 candidate cast 전후 | 임계값을 넘는 7개 |
| Candidate와 publisher의 원래 prewrite | UNKNOWN |

허용기준은 `atol=1e-5 W/m²`, `rtol=0`이다. 이 해석 보강은 허용오차 변경이나 기존 FAIL의 대체 검사가 아니다. [기존 봉인 자료](../remaining-contract-resolution/manifest.json)·source·JSON·binary·검사기를 변경하지 않고 별도 분석으로 연결했다.

## 조건부 반올림 구간 분석

Reference의 저장값을 `r`, 그 이전·다음 binary32를 `r-`, `r+`라 하면, 단일 IEEE 최근접 짝수 반올림의 preimage closed hull은 `[(r-+r)/2, (r+r+)/2]`이다. Odd significand의 정확한 midpoint ties는 실제 preimage에서 제외된다. Closed hull까지의 거리와 양 끝점까지의 최대거리는 보수적인 infimum·supremum 오차 경계다.

보존된 두 candidate capture에서 binary64를 읽어 JSON·binary32 cast와 연결한 뒤, 유리수 산술로 21개를 계산했다. 모두 closed hull 밖이며, 그 구간까지의 거리는 약 `4.94026e-10`∼`1.42484e-7 W/m²`다. 21개 모두 `lower_bound < 1e-5 < upper_bound`이므로 원래 publisher prewrite가 없으면 고정밀 비교의 통과·실패를 결정할 수 없다.

이 구간은 **추가 packing·quantization 없는 단일 최근접 cast를 가정한 계산**이다. Publisher의 실제 저장 규약을 인증했다는 뜻이 아니다. [result.json](result.json)의 두 witness는 각 셀에서 같은 `r`로 반올림되면서 candidate와의 오차가 임계값보다 작거나 큰 가상 binary64다. 실제 publisher 값이 아니며, 모든 witness가 하나의 실현 가능한 publisher 실행에서 함께 생성될 수 있다는 주장도 아니다.

## 실행과 범위

```bash
python3 -I -S validation/rrtmgp37/reference-precision-interpretation/analyze.py --verify
python3 -I -S validation/rrtmgp37/reference-precision-interpretation/test_precision.py
```

첫 명령은 기존 manifest에 기록된 네 입력 파일의 bytes와 21개 산술을 검사한다. 전체 NetCDF·coefficient·원래 publisher 환경은 다시 읽거나 인증하지 않는다. 새 compiler·WRF·UDM·RTE·LBLRTM 실행과 candidate capture는 0회다. 원래 acceptance19/current12 및 `production_accepted=false`를 유지한다.

다음 reference 작업은 정확한 publisher source/build/compiler/coefficients와 prewrite·저장 규약을 확보하는 것이다. 별도 고정밀 기준을 구축한다면 독립 identity와 승인 조건을 갖추고, 기존 published strict FAIL 21개를 보존해야 한다.

## Main과 다음 LBL 대상

[PR158 terminal 기록](pr158-terminal-main.json)은 main `b1da3b9…`와 registration의 실제 checkout `53e439c…`가 tree `4845094…`로 같고, 12개 check가 성공했음을 연결한다. root가 registration 로그를 직접 확인했다. 이전 pending 기록은 원래 시점 상태로 보존한다.

[팀 정밀도 해석 검토](source-precision-interpretation-review-v1.json)는 mixed 비교와 publisher prewrite 미확정을 구분한다. [최소 LBL 대상 계획](lbl-minimal-target-plan-v1.json)은 target1의 `R3(20)`을 물리 주파수로 추적하고 초기화·CNVFNV·XINT·RSYM·PANEL carry/clear와 R4 경로까지 확인하도록 정했다. Source-only 계획이며 동적 계보를 실행하거나 완성한 결과가 아니다. 남은 물리·최종 7개는 그대로 유지한다.

[최종 source·JSON 검토](final-review-v2.json)는 비교 이름, 정확한 유리수 경계, midpoint ties와 가상 witness의 제한을 대조해 `PASS_SCOPED`로 판정했다. 이 검토는 원시 자료 판독이나 모델 실행을 수행하지 않았다.
