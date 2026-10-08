# 선택 CO₂ coupling의 AER ASCII 원자료 연결

선택 TAPE3 record521/block260/slot124와 sidecar125를 실제 사용한 AER v3.8.1 ASCII 자료의 인접 두 기록에 연결했다. Combined `line_file/aer_v_3.8.1`과 `lncpl_lines`에서 선택 line/sidecar는 원래 bytes가 동일했다. Source scalar→TAPE3의 **16개 연결**이 일치한다. 원 Y/G 생성 코드·충돌모델의 독립 재현과 물리 reference 승인은 포함하지 않는다.

## 확인한 실제 자료

Root가 combined ASCII 908,403,720바이트와 `lncpl_lines` 74,234,394바이트를 순차 판독해 파일 hash, 유일한 선택 line, 바로 다음 sidecar, publisher CO₂ header를 기록했다. 판독기의 길이 guard를 명시적인 두 비교로 보강한 뒤 같은 자료를 재판독했으며 두 판독의 값·hash receipt는 정확히 같았다. 제조 입력·solver·compiler 실행은 이번 추가 작업에서 0회다.

| 파일 | 선택 line의 물리 줄 | byte offset0 | sidecar의 물리 줄 |
|---|---:|---:|---:|
| Combined AER v3.8.1 | 2,651,493 | 267,925,552 | 2,651,494 |
| lncpl_lines | 49,207 | 4,969,806 | 49,208 |

각 원 record는 100문자와 newline 1바이트다. Normal record hash는 `c33da0b0eb2a3565cd69b4bb3e895fddd1920f92bbd6017e63e1bb34b4aa6a22`, sidecar는 `aed61e73537de2f48676febc0a759fc18fb1c43cbec4b26d630c0a80f1135f62`다. 실제 원자료의 파일·offset 식별이며 HITRAN의 전역 고유 line ID라는 뜻은 아니다.

Publisher `lncpl_lines` header는 CO₂ 자료를 **Lamouroux et al., 2015** line-mixing database로 설명한다. 배포 archive를 직접 다시 hash한 MD5 `12e29cc828b36f78145f6ee874af552b`는 [공식 Zenodo v3.8.1](https://zenodo.org/records/4019178)에 공시된 값과 같다. 버전 DOI는 `10.5281/zenodo.4019178`이다. 이는 배포 파일의 동일성과 publisher의 계보 표기를 연결하며, 원 mixing 생성 계산을 독립 인증하지 않는다.

[2015 원 논문](https://www.sciencedirect.com/science/article/abs/pii/S0022407314003896)은 CO₂-air line mixing database/software와 2.1/4.3 μm 시험에 관한 자료다. 그 논문의 검증을 이번 618 cm⁻¹ 선택 셀의 직접적인 물리 승인으로 전용하지 않는다. 명시된 header와 논문 사이의 관계도 publisher attribution으로 표시하며 해당 선택 계수가 논문 산술에서 직접 재생됐다고 주장하지 않는다.

## 원 ASCII→TAPE3의 연결

Actual LNFL v3.2 F100 RDFIL1 source에서 다음 규약을 확인했다.

- Molecule2/isotopologue1을 `2+100×1=102`로 encode한다.
- Normal record의 −1 flag는 main line의 +1과 뒤따르는 foreign-coupling sidecar를 의미한다.
- VNU는 double, 선폭·에너지·pressure shift와 Y/G는 single 표현으로 전달한다. `TMPALF=1−TDEP`도 single 연산이다.
- Sidecar Y200/G200/Y250/G250/Y296/G296/Y340/G340을 VNU/SP/ALFA/EPP/AMOL/HWHM/TMPAL/PSHIFT에 대응시킨다. AMOL의 계수 비트를 일반 분자번호로 해석하지 않는다.

검사한 16개는 normal record의 VNU, encoded molecule, flag, 두 선폭, energy, shift, `1−TDEP`의 8개와 네 온도별 Y/G의 8개다. Strength normalization은 이번에 재생하지 않았다. IVUP=3/IVLO=2, CLO의 `Q  2f`는 원 F100 표기를 그대로 기록하며 현대 HITRAN quantum assignment의 인증으로 확대하지 않는다.

## 실제 선택 설정

성공한 historical LNFL run-v6의 TAPE5를 직접 확인했다. `VMIN=475`, `VMAX=2275 cm⁻¹`, 선택 molecule은 1,2,3,4,6,7,22이며 HOLIND는 blank다. **F100 경로이고 F160/NOCPL이 아니다.** Combined 파일의 header는 더 긴 형식이지만 실제 transition/sidecar는 F100이다. 이전 실패 시도의 F160 plan을 최종 실행 설정으로 사용하지 않는다. Physical output union 500–2250의 양끝 여유는 각각25 cm⁻¹다.

이는 실제 요청 범위를 확인한 결과다. 모든 필요 partner line의 completeness, 내부 strength rejection·line-shape cutoff의 적합성이나 first-order mixing 모델의 물리 수용성을 증명하지 않는다. 선택 line이 수용돼 output에 존재한다는 사실만으로 전체 band 제약을 닫지 않는다. [LNFL 공식 변경 기록](https://github.com/AER-RC/LNFL/wiki/What's-New)도 coupling은 explicit input으로 공급하고 NOCPL은 이를 억제하는 설정으로 설명한다.

## 재생과 제한

```sh
python3 -I -S validation/rrtmgp37/lbl-coupling-ascii-origin/verify_saved.py
python3 -I -S validation/rrtmgp37/lbl-coupling-ascii-origin/test_saved.py
```

공개 package는 위치·hash receipt, 판독한 scalar facts, 검사 코드와 LNFL source 부분을 제공한다. 전체 publisher ASCII, 원문 record와 archive는 로컬 원자료로 유지한다. **Saved CI는 decoded-source facts와 PR161에 포함된 실제 TAPE3 block의 대응을 검사하며 원 ASCII 전체를 다시 읽지 않는다.** 여섯 반례는 계수, 온도지수, 잘못된 sidecar 위치, F160 오인, archive checksum, 물리 승인으로의 승격을 거부한다.

선택 계수의 **배포 ASCII→TAPE3 파일 경계는 완료**다. 원 Lamouroux mixing generator·충돌/분광 모델·정확한 version 변환의 독립 검증, 필요한 주변 line과 cutoff의 물리 적합성 및 전체 spectrum/flux 수용성은 남는다. 같은 실행의 선택 최종 OD 연결은 별도 [합성 package](../lbl-final-od-composition/README_ko.md)에 있으며 최종 OD 음수는 그대로다. 생산 WRF·UDM·RTE, Registry, 수농도 정책, 계수, tolerance, UDM27 조건은 변경하지 않았고 REF-LBL FAIL, 완료15/잔여7, production_accepted=false를 유지한다.
