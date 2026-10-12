# PR165의 기존 payload에서 native 분광 창 판독

기준 main은 PR165 병합 `3e577a5bacc5d189cd2528675255da1c1b3641b6`, 전체 tree `a63510836516da367aaabda461eacbad6327b047`이다. 이전 격자·약선 기준 대조 실행은 완료로 유지한다. 이번에는 이미 보존된 실제 layer21 OD panel payload에서 **81/161/321개 native 점과161개 공통점**을 읽었다. 새 Fortran 빌드·WRF/LNFL/LBLRTM solver·관측기 삽입은 모두0회이다. 원래45개 OD 전체·TAPE3·원 전체 trace를 새로 인증한 작업도 아니다.

parent package의 모든 봉인 bytes와 선택한 header/payload·INIT grid·공식 source hash를 먼저 확인했다. 기존 parent manifest·result·payload·source는 수정하지 않는다. 출력 CSV는 실제 binary64 payload에서 다시 생성되며, PR165의81개 부분집합과 목표 OD·최대 차이를 비트로 연결한다. 추가 비교용 보간이나 외삽은 없다. 곡선 그림의 선은 표본의 시각적 연결일 뿐 계산용 재표본화가 아니다.

## 전체 native 창

요청 창은 `618.4557162503852–618.7710096127764 cm-1`, 즉 기존 목표618.6133629315808의±40h이다. 실제 panel 좌표의 floating 잔차는 약1.14e-13 cm-1이고 연결 한계1e-7 cm-1 안이다. 원래 IOD2/SAMPLE4/8/16 실행의 격자를 사용하며 과거 IOD0 목표점과 비교하지 않는다.

| 격자 | Native 점 | 음수 점 | 창 안의 최솟값 |
|---|---:|---:|---:|
| h | 81 | 51 | -0.026281922505360846 |
| h/2 | 161 | 102 | -0.02614739548776258 |
| h/4 | 321 | 204 | -0.02614739548776577 |

h/4의 기존81개에 없던240개 중153개가 음수다. 세 격자 모두 창 안에서 하나의 연속된 **음수 표본 run**을 갖는다. h/4의 첫 음수는618.5709953860096이고 바로 앞 비음수는618.5700100942521이다. 이는 부호 전환의 표본 bracket이며 연속함수의 정확한 근을 계산한 것이 아니다.

모든 최솟값은 창의 오른쪽 끝에 있고 음수 run도 그 끝에서 잘린다. 따라서 이 창이 전체 음수 구간을 포함하거나, 보고한 최솟값이 전체 band의 최솟값이라는 뜻은 아니다. 추가240개에서 창의 더 낮은 최솟값은 나오지 않았지만, 이를 창 밖의 수용성으로 확대하지 않는다.

## 161개 공통점과 최대 차이 위치

h/2→h/4의161개 공통점 최대 절대차는 `2.688857634407498e-4`다. 기존81개 최대와 같으며 추가80개 공통점의 최대는 `2.6341043297736094e-4`다. 기존 결과를 덮어쓰거나 같은 계산을 새 solver 실행으로 합산하지 않는다.

최대 차이의 실제 파수는 **618.538480758013 cm-1**이다.

| 해당 표본 | h/2 | h/4 |
|---|---:|---:|
| OD | 0.008297655391754801 | 0.008566541155195551 |
| 실제 payload의1-based index | 155 | 309 |
| R3 격자 정렬 | 아니오 | 아니오 |
| R2 격자 정렬 | 아니오(phase2) | 예(phase0) |
| 가장 가까운 출력 panel 끝까지 | 154개 step | 308개 step |

이 위치의 OD는 두 격자에서 양수다. 따라서 최대 격자 차이의 위치와 최종 음수의 원인을 동일시하지 않는다. 해당 표본은 두 저장 **출력 panel의 내부**에 있다. 이 기하 관계만으로 모든 내부 stencil·carry/panel 처리를 배제한 것은 아니다.

격자 정렬은 실제 trace INIT의 VFT/DVR3와 공식 source의 DVR2=4DV/DVR3=16DV에서 구한다. PANEL source는 정렬점에서는 배열 항을 직접 더하고 사이에서는4점 보간을 사용한다. 그러나 OD payload에는 최종 합만 있으므로 **직접 R1/R2 기여의 크기나 어느 항이 차이를 만들었는지는 이번 자료만으로 확정하지 않는다**.

## 정렬된11개 점의 안정성과 구간 차이는 다르다

161개 공통점을 h/2의 격자 정렬로 분류하면 다음과 같다.

| 그룹 | 점 수 | h/2→h/4 최대 절대차 |
|---|---:|---:|
| R3 node (두 격자 모두 R3 정렬) | 11 | 1.1574075031717257e-14 |
| R2 node 중 R3에 정렬되지 않은 점 | 30 | 2.4855264614729103e-4 |
| h/2의 R2 node 사이 | 120 | 2.688857634407498e-4 |

목표점만의 특이 현상에 그치지 않고11개 공통 R3 정렬점 전체가 매우 안정적이다. 반면 그 사이에는 분명한 격자 의존성이 남는다. 이는 **정렬별 관측 결과**이며, 특정 보간/lookup 또는 직접 R1/R2 물리항의 오류를 인증한 결론은 아니다. 정렬점의 차이비로 전체 수렴 차수를 만들거나, 결과를 본 뒤 승인 허용오차를 정하지 않는다.

[분광 창 그림](native-window.png)과 [PDF](native-window.pdf)는 원시 표본과161개 차이를 보여 준다. 상단은 음수 OD가 유지됨을, 하단은 정렬점 사이의 차이를 보여 준다. `plot_window.py`는 matplotlib를 사용하는 선택 시각화이고 stdlib 저장 CI에서는 그림을 재생성하지 않는다.

`result.json`에는 native 부호 run·표본 국소 extrema와 유한 창의 trapezoid 적분도 포함한다. 단위는 cm-1이며 band 플럭스나 독립 참값 오차가 아니다. 음수 부분 적분은 원 OD를 변경하지 않는 진단이고 clipping한 spectrum을 생성하지 않는다.

## 검증과 완료 범위

```
python3 -I -S validation/rrtmgp37/lbl-native-spectral-window/verify_saved.py
python3 -I -S validation/rrtmgp37/lbl-native-spectral-window/test_saved.py
```

`root-readback.py`는 실제 작업공간에서 사용한 판독 스크립트의 보존 사본이다. 저장소에서 재현할 때는 위 verify_saved.py를 사용한다.

기존 acceptance/test_verify.py의 별도 통합 시험이 위 두 명령을 호출한다. 두 기존 acceptance/identity CI job에서 실제 판독과 네 반례가 실행되며 workflow 파일은 변경하지 않는다. 원래 documentary index 시험의 의미와 production_accepted=false는 유지한다.

저장 CI는 parent 봉인자료·실제 header/payload를 다시 읽어 모든 native CSV와161개 차이 CSV·result를 재생한다. 네 반례는 (1) 기존81개를 그대로 둔 quarter-only 표본 변경, (2) 기존81개에 없던 공통 표본 누락, (3) 잘못된 grid의 nearest-point 대체, (4) 물리 승인으로의 승격을 거부한다. parser를 범용 검증 라이브러리로 확대하는 시험은 추가하지 않는다.

새 native 창 판독·최대 차이 위치·격자 정렬 분석은 완료한 **하위 분석**이다. 기존 대조 실행·선 목록·최초 음수 계보도 완료 범위를 유지한다. 창 전체의 수렴, 직접 성분 원인분해, mixing 근사·partner·독립 reference의 물리 수용성은 아직 미확정이다.

완료15/물리·최종 미완료7, `REF-LBL FAIL`, RFMIP strict21 FAIL 및 `production_accepted=false`를 유지한다. QNN 초기화·단위·population, PSD/LUT, 발생분율은 별도 OPEN이다. 최종 source/실행환경 identity와 확정 정책의 예보·관측 평가는 이 readback으로 대체하지 않는다.
