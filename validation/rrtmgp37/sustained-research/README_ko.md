# PR180 고정 구성의 지속 실행

검증 기준은 PR180 head `038f53e9f3002f0379a0c54426559424dc278071`, tree
`d143ddd13e045263603aa28e757a627bd1b0e726`이다. PR180은 2026-10-19
01:48:41 UTC에 main `f657fbf30ca46a43b3887d8aa4b82e165501db65`로 병합됐다.
병합된 main과 시험한 head의 전체 tree가 동일함을 확인했다(`merge-binding.json`).
실제 실행의 head·실행파일 identity는 그대로 보존하며, 병합 뒤 새로 실행했다고
재명명하지 않는다. 생산 소스·기본값·계수·초기 물리 배열은 변경하지 않았고
기존 일반 빌드 실행파일을 그대로 사용했다.

`plan.json`의 첫 사본은 1시간 실행 전에 저장했고, 24시간 단계의 checkpoint
시각은 그 단계 전에 기록했다. 최초 계획과 실행별 사본, 출력 timer 후속 변경,
실패한 시작과 모든 실제 프로세스 기록을 `saved/`에 함께 보존한다.

## 결과와 제한

- 동일 양의 구름 입력, number1/population2, dt=10초, radt=30초의 00/11이
  각각 1시간과 24시간을 완료했다. 두 24시간 실행에서 주간 128개·야간 160개
  history 기록을 확인했다. 야간 SWDOWN은 0이고, LW 호출은 0–86370초의
  30초 간격 2880회다. 표본의 수분·number에 음수·비유한값은 없다.
- 11의 21610초(6시간10초) checkpoint 재개는 다음 복사 시각 21630초를 유지했다.
  출력 timer를 명시한 최종 재개에서 공통 216개 시각의 Time 배열 214개가
  연속 실행과 바이트 동일하다. 유지된 LW/SW/total·clear 경향과 STEPRA도 같다.
  첫 재개 복사는 야간이므로 LW capture만 있다. SW capture를 만들어냈다고
  주장하지 않으며 이후 주간 SW history도 전체 배열 비교에 포함한다.
- 최초 재개는 정상 종료했지만 기본 WRF가 다음 history까지 남은 290초를
  반복 간격으로 복원해 300초 출력 주기를 유지하지 못했다. 실제 복사 위상은
  유지됐고, 공통 8개 시각의 214개 배열은 동일했다. 기존
  `override_restart_timers=.true., history_begin_s=290`을 사용한 짧은 출력
  시험 후 같은 checkpoint에서 전체 남은 구간을 실행했다. 생산 수정은 없다.
  관련 기본 코드(`input_wrf.F` output alarm의 `RingInterval=interval`)는
  PR180 이전에도 존재한다. 이 자료를 stock 출력 timer의 정상 판정으로 쓰지 않는다.
- 사전 계획의 1810초 hour checkpoint도 생산했으나 별도 재개하지 않았다.
  더 진화한 21610초 checkpoint 비교로 제한했다. 따라서 사전 계획의 모든
  항목을 무조건 PASS로 표시하지 않는다.

## 아직 닫히지 않은 수지와 광학 범위

건조 층질량과 실제 상태 차이, RAINC+RAINNC, ACLHF/2501000으로 계산한
24시간 `ΔW+P−E`는 00 약 −0.009649, 11 약 −0.012276 kg/m²이다.
이는 history 수분 장부이며, 공통 PBL/PD의 실제 적용 source를 장기간 다시
계측한 결과가 아니다. **host 물수지 보존 PASS로 승인하지 않는다.**

1800초의 LW/SW와 재개 첫 21630초의 LW capture에서 same-call capacity와
native 층의 `C*heating−Q`가 산술 범위에서 일치한다. 실제 양의 cloud의
Gamma8 REL도 검사한다. 그러나 장기 acoustic source 적용 장부는 새로
계측하지 않았으므로 **장기 실제 적용 에너지 폐합은 NOT_ASSESSED**다.

24시간 history에서 질량/number로 진단한 Gamma8 반경은 액체 LUT 범위를
벗어나는 표본도 있다(11에서 770개). 이 값은 각 radiation 호출의 실제
clipping 횟수나 오차율이 아니다. 반경 범위·희박 잔여물의 적용성은 과학적
판정에 남기며, 초기 60초의 비활성 clipping 조건을 장기 실행 전체로 확대하지 않는다.

기존 일곱 종료 조건은 그대로다. `production_accepted=false`이며 독립
reference FAIL은 그대로이며, 전체 물리 에너지·관측 정확도·일반 입력/경계·혼합상은 미승인 상태다.
여기서 확인한 것은 제한 구성의 지속 적분·주야간 경유·조건부 재시작이다.

## 재현과 실행 수

`WRF/test/rrtmgp/run_research_radiation_sustained.py`는 `--stage hour` 이후
`--stage day`를 실행한다. `resume_research_radiation_sustained.py`는 같은
campaign의 선언된 checkpoint를 사용한다. 실행파일·물리 입력 SHA가 다르면
시작 전에 거부한다. 정확한 실제 launch recipe와 stderr/RC는 saved에 보존한다.

새 WRF 모델 실행은 정상 종료 7회다: 네 연속 실행, 기본 timer의 긴 재개,
10분 출력 timer probe, 최종 긴 재개. 최종 지속/재개 비교에는 5회를 사용한다.
별도로 공유 라이브러리 경로 누락으로 모델 진입 전 끝난 프로세스 2회와,
프로세스 생성 전 harness 오류 2회를 보존했다. 새 빌드·독립 UDM/Mie/LBLRTM
캠페인은 없다. RTE는 WRF 복사 호출 안에서 실행됐다. 독립 기상 사례 수가 아니다.

저장 근거 검사(모델을 실행하지 않음):

```sh
python3 -I -S validation/rrtmgp37/sustained-research/verify_saved.py
python3 -I -S validation/rrtmgp37/sustained-research/test_saved.py
```

`T`는 섭동 건조 온위다. 결과의 실제 온도 범위는 `(T+300)*(p/1e5)^(Rd/cpd)`로
별도 환산한다. 00/11의 상태 차이를 순수 엔진 차이나 관측 오차로 해석하지 않는다.
