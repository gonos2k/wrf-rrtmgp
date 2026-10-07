# NOAA 개발자 원자료와 UDM 수농도 계약

[NOAA UIFCW 2023 발표](https://epic.noaa.gov/wp-content/uploads/2023/08/UIFCW-2023-Tue-19.-Songyou-Hong-mp_new-202307-UIFCW-template.pdf)의 원본 PDF를 내려받아 확인했다. 표지 포함 5·6·17·20쪽은 과정의 평균 기준, 이중모멘트 개발 과제, 체적 CCN 초기값, 예측 수농도 변수를 뒷받침한다. 이 자료는 2023년 개발 실험이다. 현재 WRF의 host 저장·호출 규약이나 NOAA 운영 채택의 증명은 아니다.

[공식 WRF 도입 소스](https://github.com/wrf-model/WRF/blob/5fc76c540631be296bd2312e1d96117c07cbf761/phys/module_mp_udm.F)는 PR #2147의 병합 commit `5fc76c5`로 고정했다. 내부 Nc/Nr/CCN 상수의 m⁻³ 주석과 선택된 cloud-slope 식은 내부 체적 수농도 의도를 지원한다. 현재 main `a91d0d855da3e24094c2e6c7ba1088b56bc8c461`의 소스도 비교했다. 도입 당시와 현재의 Nc/Nr 상한은 각각 2×10⁹→3×10¹⁰, 2×10⁶→3×10⁸ m⁻³로 다르다. 후속 시험에는 현재 소스의 상한을 사용해야 한다. 이 기록은 상한 변경의 물리 승인이나 변경 제안이 아니다.

| 체크리스트 부분 | 판정 |
|---|---|
| 발표 실험의 CCN 초기 입력 체적 단위 | 직접 확인 |
| 내부 수농도 상수와 선택된 slope의 체적 기준 근거 | 직접 확인 |
| 미세물리와 침강·역학의 평균 기준 구분 의도 | 직접 확인 |
| QNN/QNC의 host 저장 단위·질량 분모 | OPEN |
| 격자평균/구름내 population과 변환 위치·시점 | OPEN |
| 모든 과정의 단위 폐합·PSD/LUT 유효크기 의미 | OPEN |

Registry는 QNN/QNC를 kg⁻¹, `ccn_conc`를 m⁻³로 표기한다. 초기·지정경계에서 QNN에 직접 대입하고, generic scalar는 건조질량 좌표로 가중해 수송한다. UDM에도 수농도 인자를 직접 전달하며, 해당 CF divide/restore 경계에서는 응결물 질량만 변환한다. 이는 충돌 경로를 특정하지만, 메타데이터가 오래됐는지 변환이 누락됐는지 의도한 host 표현이 다른지는 결정하지 못한다. **PHY-NC 전체는 OPEN**이며 기존 10/17의 범위 내 완료 개수와 생산 승인은 바뀌지 않는다.

같은 입자 집단에서 질량당 수농도 η의 분모가 건조공기이면 체적 수농도는 `n=ρ_dη`이다. 구름방울이 맑은 부분에는 없을 때만 `n̄_c=f_c n_c^in`을 쓸 수 있다. CCN은 `n̄=f_c n_cloud+(1−f_c)n_clear`이므로 QNN을 자동으로 분율로 나눌 수 없다. 이는 정의에 따른 조건부 관계이며 미확정 UDM 규약을 대신하는 처방이 아니다. 생산 코드의 밀도·CF 배율이나 Registry 단위 표기를 바꾸지 않았다.

[contract.json](contract.json)에 확인된 부분과 미확정 부분을 분리하고, [PHY-NC 항목](checklist-item.json)과 [개발자 질문 초안](developer-questions_ko.md)을 연결했다. 질문은 발송하지 않았다. 팀 검토는 선택된 소스와 생성 경로를 확인한다. 새 WRF·컴파일·RTE·물리 수치실험은 0회이다.

`primary-fetch.json`은 원자료 URL과 hash를 기록한다. 첫 download batch는 원본 4개를 확보한 뒤 GitHub 비인증 API rate-limit으로 멈췄다. PR/comment는 별도의 읽기 전용 API로 확보했다. 웹 PDF screenshot은 403으로 실패했지만 원본 PDF를 로컬에서 렌더링하고 텍스트와 대조했다. PDF·공식 전체 소스·원본 PR 본문은 저장소에 복제하지 않는다. 작은 source/hash/판정 기록만 보존하며, 원자료 파일은 원래 local preparation 경로에 있다.

이 package는 main 기반의 별도 검토 변경이다. [PR #146](https://github.com/gonos2k/wrf-rrtmgp/pull/146)의 runtime 통합과 [PR #147](https://github.com/gonos2k/wrf-rrtmgp/pull/147)의 보존 증거를 자동으로 main에 넣지 않는다. 기존 acceptance 19/current 12, 과거 source pin, RFMIP strict·LBLRTM FAIL과 `production_accepted=false`는 유지한다.
