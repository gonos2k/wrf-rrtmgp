# QNN/QNC host 경계: 실제 스칼라 수송 절차의 제한 검증

기준 main `a152b2798ef465c57822db6a45e983a4b1d4ef34`, 전체 tree
`92c73cece68279af1d04ab3e15643ae3cad94eae`. PR154는 병합됐고 11개 check가
terminal SUCCESS다. 과거 PR154 제출 시점의 pending 기록은 수정하지 않는다.

현재 소스의 `advect_scalar`, `rk_update_scalar`, `rk_update_scalar_pd`,
`flow_dep_bdy_qnn` 전체 절차 본문을 그대로 추출해 최소 config/type/shape
adapter와 컴파일했다. **전체 모듈 빌드·WRF host 실행·QNN/QNC routing은 아니다.**
두 일반 scalar slot의 manufactured 값과 소스상의 QNN/QNC 호출 관계를 구분한다.

## 확인한 동작

- O0/O2 각 8가지 입력 구성: 두 건조 column mass, uniform/patterned scalar,
  flat 또는 hybrid/공간적으로 변하는 map factor. 밀도/EOS를 맞춘 대기 사례가 아니다.
- Order-2 수평 flux와 RK stage1/3를 각각 호출한다. y/vertical flux는 0이며
  주기 halo는 fixture에서 채운다. 단계별 같은 입력을 사용하므로 전체 RK 궤적이 아니다.
- 셀별 독립 FV flux/update, uniform scalar 보존, 원래 time-t buffer와 선택한
  horizontal diagnostic을 검사한다. 서로 다른 scalar는 별도 tendency/update 호출이다.
- 면적 `A=1/(msftx*msfty)`, 층 질량 `M=-DNW*(C1*MU+C2)/g`를 사용한
  `sum(A*M*scalar)`는 닫힌 주기 flux에서 보존된다. maximum relative residual
  약 `3.99e-8`. Patterned arm의 raw sum은 변하므로 raw 합계와 질량 가중 보존을 구분한다.
- PD update는 **같은 old/new mass에서 prescribed mass-coupled source 추가와
  tendency 초기화**만 검사한다. PD advection limiter나 changing-mass PD는 검사하지 않는다.
- QNN boundary는 velocity -1/0/+1과 periodic-x OFF/ON의 6개 경우에서
  유입 `ccn_conc` 직접 대입·유출 내부 복사·0속도의 유입 처리·halo/top 보존을 검사한다.

각 최적화에서 transport cell 768개, boundary 전체 저장 cell 720개를 기록했다.
실제 call은 advection32 + normalRK32 + sourceRK32 + boundary6이다.
두 최적화를 합해 204회 절차 호출이며 독립 기상 사례 수가 아니다.
최종 실행은 compile/link2 + fixture2 + version query1; 전체 WRF/UDM/RTE 실행0.
6개 변조 입력은 최적화별로 거부된다. 독립 FV 계산은 tolerance bounded이며
REAL32 모든 연산의 bitwise source-order 재현을 주장하지 않는다.

## 입력·수송·소비의 남은 연결

Registry는 QNN/QNC에 `# kg(-1)`, `ccn_conc`에 `# m-3`를 표기한다.
`start_em`과 37번 driver startup은 특정 조건에서 `ccn_conc`를 QNN에 그대로
대입한다. generic scalar update는 질량으로 coupling/decoupling하고, UDM call의
`NN=qnn_curr, NC=qnc_curr`는 raw 배열을 전달한다. 이 접점은 소스 근거와
선택한 실제 boundary/transport 동작으로 좁혔지만, **의도된 host denominator와
population·producer/restart 입력의 단위는 승인되지 않았다.**

초기화 블록과 실제 전체 UDM 입구를 이번 fixture에서 실행한 것은 아니다.
기존 startup·부분 activation·액체 반경 근거를 같은 host 실행으로 합산하지 않는다.
수송의 보존형만으로 단위 의도를 결정하거나 NC/NN에 밀도·CF 배율을 추가하지 않는다.
PSD/LUT 모멘트, CF0 occurrence, RFMIP strict21FAIL, LBLRTM negativeOD 및 최종
identity/forecast gate는 유지된다. 체크리스트 완료15/잔여7, `production_accepted=false`.

## 재현과 원본 보존

```sh
python3 -I -S validation/rrtmgp37/host-number-transport/verify_saved.py
python3 WRF/test/rrtmgp/test_udm_host_number_transport.py WRF --workdir /fresh/path
```

Saved verifier는 고정 archive의 source slice·adapter·실제 RC·셀별 ledger를 다시
계산한다. Fresh 시험은 working source를 다시 추출·컴파일하며 별도 receipt를 만든다.
원본 source와 최종 runner/fixture, stdout/stderr 및 receipt를 보존했다.
큰 실행파일은 hash만 보존하며 이 package에 포함하지 않는다. Manifest 자체의
외부 trusted hash가 없다면 무결성 검사는 내부 연결의 확인이지 독립 진위 인증이 아니다.

첫 v1은 checker가 binary64 기대 입력과 REAL32 제조 입력을 정확히 같다고
요구하여 실패했다. 실제 입력 rounding을 고려해 수정했으며 과거 실패는 보존했다.
v2는 source-update/transport만, v3는 boundary 추가, v4는 static host source pin을
추가한 최종 실행이다. 앞선 receipt/log는 historical/superseded이며 최종 PASS와
혼합하지 않는다. 앞선 fixture/checker snapshot을 별도 보존하지 않은 시도는
최종 sealed source 재현 근거로 사용하지 않는다. 네 시도의 총 process는
별도 development-attempts.json에서 실제 journal로 집계한다.

팀 검토는 소스·작은 JSON metadata만 읽었다. 컴파일·fixture·raw scientific
record 판독은 root가 수행했으며 팀 검토를 추가 실행 횟수로 세지 않는다.
