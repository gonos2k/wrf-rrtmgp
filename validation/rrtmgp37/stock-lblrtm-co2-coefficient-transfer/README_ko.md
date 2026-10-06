# 관측된 CO2 801개 line의 조건부 계수 전달 검토

앞선 census의 관측된 CO2 flag-1 identity 801개에 대해, 저장된 TAPE3 main/companion과 실행 메타데이터 사이의 interpolation·pressure·center 전달을 확인했습니다. Target의 5,930 writes에서 8개 필드를 비교한 47,440 반복 field checks는 bit difference 0 / max ULP 0입니다. Unique identity-field 조합은 801×8=6,408개입니다. 47,440은 독립 line 또는 관측 개수와 다릅니다.

확인 필드는 YI, GI, PAVP0, PAVP2, observed corrected SUI로부터의 SP 및 SPPSP, shifted VNU, term metadata VNU입니다. **Corrected SUI는 저장된 실제 입력으로 사용했습니다.** 모든 801개에 대한 WK/WKI/SCOR·thermal-strength 생성이나 원본 ASCII→TAPE3 진실성을 독립 증명한 결과가 아닙니다. R3 write 자체의 값·물리 cancellation·모든 candidate/rejection의 완전성 또한 검증하지 않습니다. Negative-OD 물리 FAIL과 +0.6806384666588787 W/m²의 남은 residual 원인 미분해 상태는 그대로입니다.

실제 saved-only reader는 1회(PID 2254879), actual RC0·reaped·timeout 없음입니다. 새 solver·model·build는 없습니다. 기존 ancestry 72개와 layer-21 panel header의 동일 P/T context, 기존 R3 term 기록 및 census의 선택 TAPE3 범위 SHA를 사용합니다. TAPE3 header/13 panels의 509,192 bytes만 재확인했으며 historical whole-file SHA를 새로 계산하지 않았습니다.

801개 모두 additional pressure-shift branch의 첫 positive-sum predicate가 false입니다. 795개의 zero vector와 6개의 `(-654321,0,…,0)` vector가 있습니다. 최초 peer review의 당시 미확인 의미를 원문 그대로 보존하고, 별도 source-only clarification도 함께 보존했습니다. Pinned LNFL의 equivalence/초기화 코드에 따르면 `-654321`은 storage-length marker이며 물리 broadening coefficient가 아닙니다. 이 설명은 기존 결과를 변경하거나 물리 판정 범위를 늘리지 않습니다.

13개 원본 파일은 byte-exact copy입니다. 기존 census 16개 파일과 ancestry 55개 파일은 수정하지 않습니다. Public result는 identity와 check 요약만 담으며 raw coefficient vectors/ancestry/R3/PANEL/CAND/TAPE3/AER/OD binary/executable/실행 authority를 배포하지 않습니다. 원본 plan의 prepared 상태와 historical path는 당시 작성 상태를 보존한 것입니다. 실제 완료 상태는 `run/execution.json` 및 root/peer terminal review에 있습니다.

어느 cwd에서든 stdlib로 저장된 archive integrity, 실행/소스 binding, census membership 및 field-check 요약 일관성을 검사합니다.

```sh
python3 -I -S /path/to/repository/validation/rrtmgp37/stock-lblrtm-co2-coefficient-transfer/verify.py
```

Verifier는 raw 입력을 열거나 계수 계산/reader를 재실행하지 않습니다. Archived `evidence/audit.py`는 실제 실행된 소스이나 private original path와 미배포 raw inputs를 필요로 하므로 이 packaged 경로에서 직접 재실행 가능한 프로그램이 아닙니다. 재실행에는 relocation과 external input 검토가 필요합니다. 이 source-mechanics evidence는 WRF/RRTMGP 정확성·normality 또는 전체 reference physics의 승인과 다릅니다. 새 PR CI 성공은 주장하지 않습니다.
