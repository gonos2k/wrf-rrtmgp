# 정책1 경계 보호와 기존 빙정 융해 순서 수정

PR170 main `e26ab7ba04ccf54b02f22d3e87f7f886122a824a` 이후의 좁은 두 수정이다.

- 정책1의 실제 입력 검사에서 specified/nested, max_dom≠1, domain ID≠1, x/y 비주기 구성을 거부한다. 지정 경계 QNN 체적 상수 대입을 η로 바꾸는 새 producer는 구현하지 않았다. 정책0 경계 코드는 변경하지 않았다.
- 순간 빙정 융해의 qi=0 대입을 기존 Ni 진단 뒤로 옮겼다. 원래 질량 의존식·한계값을 유지하고, 질량과 잠열 대입 순서를 유지했다. 이 문제는 PR170 bridge 이전부터 존재했다. 정책0과 정책1 모두 적용된다.

## 직접 수행한 검증

전체 실제 UDM을 O0/O2로 컴파일했다. CF=1, 두 건조 밀도, 두 양의 qi, 정책0/1에 대해 수정 production 소스·관측 소스·이전 소거 순서 대조군을 실행했다. 총 48개 UDM 호출이다. 이전 순서 Ni는 1,000, 수정 후 약 7,322–57,787이다. 질량 이동과 잠열 갱신의 블록 결과는 이전 순서와 비트 동일하고, 관측기 ON/OFF 반환과 두 정책의 native 융해 값도 일치한다. 최종 NC는 후속 과정에서 변할 수 있으므로 단계 값과 별도로 보존했다.

별도 GNU serial REAL32 SCM WRF/ideal을 새로 빌드했다. 정책1/정책0 periodic은 각각 60초 정상 종료했고 history의 주요 상태는 유한하다. 정책1로 명시된 실제 입력 + specified 구성은 새 fatal에서 거부됐으며 history가 없었다. GNU fatal의 반환코드가 0일 수 있어 로그·성공 문구·출력 유무를 함께 확인했다. nested/max_dom/domain ID/nonperiodic 거부는 입력 검사 블록을 원문 그대로 컴파일한 O0/O2 16회 probe로 확인했다. 전체 nested WRF/MPI 캠페인은 수행하지 않았다.

기존 CTest 경로에 두 시험을 추가했고 둘 다 통과했다. 초기 configure 두 시도는 nc-config/nf-config 변수 이름이 맞지 않아 실패했다. 세 번째 configure와 실제 build가 정상 완료됐으며 이전 실패 로그도 보존했다. 이는 새로운 생산 물리 결함이 아니다.

## 이전 증거와 현재 소스

PR170의 source·결과 해시와 바이너리 자료를 유지한다. 당시 변경된 mp/input/CMake bytes와 registration receipt를 `historical-source/snapshot-e26ab7ba*`에 보존했다. 기존 bridge 검사는 당시 소스를 재생하며 이번 수정을 인증하지 않는다. 이번 자료의 identity와 새 CTest가 현재 수정 소스에 대응한다. 과거 과학 결과 해시를 현재 값으로 덮어쓰지 않았다.

`verify_saved.py`는 실제 UDM 관측 로그를 파싱해 Ni, NC, 물질·잠열과 대조군을 재계산하고 실제 WRF/probe 종료 로그를 검사한다. CI의 저장 재생은 새 모델 실행이 아니다. 저장된 NetCDF는 무결성 봉인만 수행하며 CI에서 독립 변수 해석을 하지 않는다. 로컬 readback은 `runtime_readback.json`에 구분했다. 실제 새 WRF 바이너리는 로컬 격리 build에 보존하고 해시·CMake 설정·실제 library 식별을 기록했다.

## 남은 물리 판단

`POPULATION_DECISIONS_KO.md`의 부분 CF 정의표를 다음 PHY-NC/PHY-SIZE 작업으로 사용한다. 이번 CF=1의 순서 수정은 Ni fit의 관측 정확성이나 부분 CF population을 승인하지 않는다. PSD/LUT·발생분율·RFMIP/LBLRTM·최종 identity/예보의 기존 일곱 조건을 유지한다. `production_accepted=false`다. 새로운 장시간 예보나 같은 누락 빙정 민감도 캠페인은 수행하지 않았다.
