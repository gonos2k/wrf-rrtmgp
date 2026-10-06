# 관측된 CO2 기여 레코드 801개의 companion census

기존 target R3 contributor 보고서에서 관측된 CO2·flag 1 main 801개를 실제 TAPE3의 지정 block/slot에 연결했습니다. 각각 정확히 하나의 바로 뒤 연속 negative-IFLG companion을 가지며, 누락·중복·identity mismatch·끝이 열린 group은 모두 0입니다. 이는 앞선 3-pair audit를 관측된 801개 main의 **구조적 연관성 범위**로 확장합니다.

실제 saved-record reader는 1회(PID 2169675), actual RC0·reaped·timeout 없음입니다. 새 모델·solver·빌드는 없습니다. 기존 derived report의 6,072 target R3 updates / 837 reason-12 identities 가운데 CO2 flag-1 801개를 사용하며, raw CAND/R3 join을 재실행하지 않았습니다. TAPE3 header와 block 484–496의 13개 panel에서 총 509,192 bytes를 읽었습니다. 이전 whole-file SHA는 역사적 provenance이며 **이번 reader가 새로 full-file hash를 계산한 것은 아닙니다**. 선택 범위별 SHA 및 전후 stat 동일성은 실행 결과에 보존했습니다.

각 main에서 다음 nonnegative slot까지의 연속 negative 슬롯을 세었으며 panel 경계를 포함합니다. 이 결과는 모든 후보·rejection 집합의 완전성, 명명된 물리 coupling group, companion coefficient/YI/GI/SPPSP 또는 R3 값의 정확성을 증명하지 않습니다. 기존 negative-OD 물리 FAIL과 약 +0.68063847 W/m²의 남은 common-angle residual의 원인 미분해 상태는 그대로입니다. WRF/NOAA 정확성 또는 정상 물리 판정이 아닙니다.

`evidence/plan.json`, preparation README 및 root preflight의 prepared/pending 문구는 원본 작성 시점의 상태를 그대로 보존한 것입니다. 실제 완료 상태는 `run/execution.json`, `run/result.json`, `reviews/independent-terminal.json`에 있습니다. 모든 원본 copy는 byte-exact이며 `origins.json`으로 묶었습니다. PR121의 기존 패키지는 수정하지 않습니다. 이 패키지는 raw TAPE3·AER 원문·계수 벡터·OD binary·실행파일·실행 authority·signed URL을 배포하지 않습니다.

어느 cwd에서든 다음 stdlib 명령으로 저장된 패키지의 closed roster, SHA, 실행/소스 binding, 801개 저장된 identity/cardinality 및 요약 일관성을 검사할 수 있습니다.

```sh
python3 -I -S /path/to/repository/validation/rrtmgp37/stock-lblrtm-co2-companion-census/verify.py
```

이 verifier는 raw TAPE3를 열거나 audit를 재실행하지 않습니다. 보관된 `evidence/audit.py`는 당시 private path와 external 입력을 사용하는 실제 실행 소스이며 packaged path에서 직접 재실행 가능한 프로그램이 아닙니다. 재실행에는 external 자료와 경로의 별도 검토가 필요합니다. integrity 검증 성공과 물리 검증 완료를 구분합니다. 이 새 PR의 CI 결과는 여기서 주장하지 않습니다.
