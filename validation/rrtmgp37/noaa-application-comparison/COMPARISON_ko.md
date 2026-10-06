# NOAA/NWS 적용 사례와 UDM27–RRTMGP37 비교

확인일: **2026-10-06**. 평가 대상은 **UDM27만**이다. NOAA의 공개 구현은 비교 기준으로 사용하며, 다른 미세물리로 WRF 지원 범위를 확대하지 않는다.

**가장 직접적인 공식 근거는 HAFS v2.2의 RRTMG→RRTMGP 전환 공고다. 다만 시행일은 2026-10-13으로, 확인일에는 운영 전환 예정이다. 공개 HAFS suite는 Thompson을 사용하므로 UDM27 결합의 동등성이나 정확성을 입증하지 않는다.**

## 1. 적용 상태

| 대상 | 공식 자료에서 확인한 내용 | 이번 평가에서의 해석 |
|---|---|---|
| HAFS v2.2 | 2026-09-09 NWS 공고에 RRTMG→RRTMGP 전환과 2026-10-13 시행 명시 | 구체적인 운영 전환 예정 사례. 10월 6일에 이미 시행됐다고 표시하지 않음 |
| GFS v17 | 2026-04-15 제안 공고에는 Thompson–Eidhammer 및 **RRTMG 개선** 명시 | 이 공고나 개발용 RRTMGP suite 이름으로 운영 RRTMGP 전환을 주장할 수 없음 |
| NOAA UFS 연구·전환 사업 | FY25 JTTI에 RRTMGP 정확도·효율 개선 및 운영 전환 과제 명시 | NOAA의 연구·전환 활동 근거. 특정 모델의 운영 시행을 입증하는 자료와 구분 |

공식 출처: [HAFS NWS SCN26-76](https://www.weather.gov/media/notification/pdf_2026/scn26-76_HAFSv2.2.pdf), [GFS NWS PNS26-29](https://www.weather.gov/media/notification/pdf_2026/pns26-29_Science_for_GFSv17.pdf), [NOAA WPO FY25 JTTI](https://wpo.noaa.gov/jtti-program-fy25-awards/).

HAFS 공고의 예보 성능 향상은 복사·경계층·지면·해양·자료동화 등이 함께 변경된 **전체 시스템** 비교다. RRTMGP 단독의 개선율로 인용하지 않는다.

## 2. 비교한 코드의 신원

공개 HAFS `production/hafs.v2.2`의 고정 소스 연결은 다음과 같다.

`HAFS 6ac5af9 → UFS 9ad9fab → UFSATM 8f3a2ec → CCPP 9c64d49 → RTE-RRTMGP 763cc15`.

이는 공개 branch와 submodule 연결의 확인이며, NOAA가 배포한 실행파일의 동일성 검증은 아니다. 전체 SHA·파일 해시는 [공개 소스 보고서](noaa-public-source-report.json)에 보존돼 있다.

WRF 비교 대상은 **아직 병합되지 않은 PR112 후보 `79a58e27cddb8d737d81c925c299a868a86596d6`**이다. 원격 main은 별도로 **`3b4b2d8aa949cb342615f72bbd2ec0feed14a50a`**, PR8 병합본으로 재확인했다. 후보에 추가된 기체·건조질량·상수 처리를 main의 기능으로 표시하지 않는다. [main 확인 기록](main-readback-v2.json)

## 3. 구현 비교

| 항목 | 고정 공개 HAFS/CCPP 소스 | UDM27 WRF 후보 | 판정 |
|---|---|---|---|
| 미세물리 | HAFS suite는 Thompson | UDM27 전용, UDM native 반경 | host의 물리 구성이 다름. NOAA UDM과 같다는 결론은 불가 |
| 구름·강수 분류 | 미세물리별 mapper. GFDL/unified 분기는 snow+graupel, Thompson 분기는 liquid/ice/rain/snow | UDM 종별 질량·반경 계약으로 준비 | GFDL의 `qs+qg`를 NOAA 전체의 공통 정책으로 일반화하면 안 됨 |
| 구름·강수 분율 | 미세물리별 구름분율; `precip_frac=cld_frac` 대입 | WRF/UDM 분율 차이와 강수 발생영역을 별도로 평가 | NOAA 구현에도 분율 가정이 존재. 복사 정확도의 자동 보증이 아님 |
| 기체 입력 | 검사한 LW/SW wrapper가 명시적으로 설정하는 VMR은 6기체 | SW 6기체, LW 11종: N2와 4개 CFC류 포함 | wrapper에 없는 기체가 실제로 0이라고 추론하지 않음. active gas 설정까지 맞춰야 함 |
| 건조 기체량 | 압력·온도·VMR 전달, wrapper에 native dry mass/`col_dry` 인수 없음 | WRF native 건조질량으로 모델 내부층 기체량을 명시, 상부 확장은 압력/VMR 경로 | WRF의 건조질량 좌표 계약을 유지하며 비교해야 함 |
| 물리상수 | 검사한 wrapper만으로 linked engine의 상수 초기화는 확정 불가 | WRF의 g, cp, 건조공기 분자량을 전달 | NOAA와 상수값이 같거나 다르다고 단정하지 않음 |
| 장파 각도 적분 | 청천 optimal-angle/Gaussian 분기와 전천 Gaussian 인수 명시 | 각도 keyword를 생략해 linked RTE 기본값 사용 | 동일 입력에서 각도 정책을 통제할 비교 항목 |
| 단파 delta scaling | 검사한 SW wrapper의 cloud `delta_scale()` 호출은 주석 처리 | cloud를 한 번 scale; 강수 광학은 이미 scale된 별도 경로 | 확인된 알고리즘 차이. 곧바로 포팅 오류나 차이의 원인이라고 판정하지 않음 |
| 빙정 크기·거칠기 | mapper의 크기 직접 전달. 검사한 파일만으로 HAFS roughness의 실제 선택값은 미확정 | UDM native 크기 전달과 코드상 변환, 명시 roughness. LUT 크기 정의와의 물리적 동등성은 미검증 | 반경/직경 이름만 보고 2배 오류를 판정하거나 NOAA roughness 값을 추정하지 않음 |

소스 근거: [HAFS suite](https://github.com/NOAA-EMC/ufsatm/blob/8f3a2ecd5b0b6ecaf6331356fb6fa3aed917b229/ccpp/suites/suite_FV3_HAFS_v2.xml), [CCPP cloud mapper](https://github.com/ufs-community/ccpp-physics/blob/9c64d49ba93e06ba2e7e0e6f63d8edd707ac1c51/physics/Interstitials/UFS_SCM_NEPTUNE/GFS_rrtmgp_cloud_mp.F90), [CCPP LW](https://github.com/ufs-community/ccpp-physics/blob/9c64d49ba93e06ba2e7e0e6f63d8edd707ac1c51/physics/Radiation/RRTMGP/rrtmgp_lw_main.F90), [CCPP SW](https://github.com/ufs-community/ccpp-physics/blob/9c64d49ba93e06ba2e7e0e6f63d8edd707ac1c51/physics/Radiation/RRTMGP/rrtmgp_sw_main.F90). 자세한 소스 위치와 후보 측 대조는 [비교 기록](source-contract-comparison.json)에 보존돼 있다.

## 4. 정상적인 차이로 볼 수 있는가

**NOAA도 RRTMGP를 선택했다는 사실만으로 현재 4↔37 차이를 정상으로 인정할 수는 없다.** 같은 엔진이어도 host의 물리 상태·광학 구성·난수 표본이 다르기 때문이다. 이번 조사는 소스 비교이며 새로운 수치 정확도 시험은 아니다.

UDM27의 동일 저장 상태에서 다음 순서로 비교 조건을 맞춘다.

1. 기체 계수자료, 모든 active gas의 VMR, native 건조질량과 상부 확장, 물리상수.
2. UDM의 종별 수분경로와 크기 정의, 구름·강수 분율, LUT와 roughness.
3. LW 각도 적분, SW cloud/precipitation의 scaling·합성 순서.
4. 같은 McICA mask, 또는 각 엔진의 다중 seed 평균과 표본분산.
5. 플럭스에서 WRF 가열률·온위 경향·진단값으로의 변환.

조건을 맞추면서 사라지는 차이는 해당 입력·설정·표본의 기여로 추적할 수 있다. 남는 차이는 독립 기준 계산으로 평가한다. 결합 적분의 차이만으로 계수 차이·표본오차·피드백·포팅 결함을 구분하지 않는다.

현재 결론은 **NOAA의 공개 적용·전환 근거와 구현 비교 항목을 확인했지만, UDM27의 잔차를 정상으로 인정할 근거는 별도로 필요하다**는 것이다. 이번 조사에서는 새로운 모델 실행·RTE 계산·관측 정확도 판정을 수행하지 않았다.
