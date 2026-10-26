"""Render a report only after actual results exist; no predicted model scores."""
from pathlib import Path
import json
P=Path(__file__).resolve().parent

def main():
 r=json.loads((P/'result.json').read_text());assert r['status']=='ACTUAL_INTERIOR_DOMAIN_COLD24H_OBSERVATION_EVALUATION_COMPLETE';new=r['statistics']['primary'];old=r['original_statistics_preserved']['primary'];surf=r['surface_16_17UTC'];m=surf['means'];obs=surf['observed_components_reused'];neg=sum(v['negative_elements'] for row in r['history_validity']['hourly_validity'] for v in row['water_number'].values());contrast=r['input_contrast'];hgt=next(x for x in contrast['variables'] if x['variable']=='HGT');land=next(x for x in contrast['variables'] if x['variable']=='LANDMASK');peak=r['maximum_absolute_error_hour']
 text=f'''# Sterling 내부영역의 실제 하루 예보와 관측 평가

**#201의 준비 입력으로 2016-10-06 00:00–2016-10-07 00:00 UTC를 실제 적분하고 관측을 채점했다.** 기존 public 실행파일과 고정 물리를 사용했다. 새 구성의 전체시간 RMSE는 **{new['all']['RMSE_W_m2']:.6f} W/m²**, 주간 편차는 **{new['daylight']['bias_W_m2']:+.6f} W/m²**다. 아래 결과는 영역·WPS·지리자료가 함께 바뀐 별도 연구 구성의 성능이다. 순수 경계 거리 효과나 광학 코드 개선율이 아니다.

기준 main `eef6e4a593e886162af1e0ff786928dc18b5bbda`, tree `448c3229895270f9969b15ba1d34cd62311b50f5`. 생산 WRF·UDM·RTE, 기본값·광학계수·기존 일곱 종료 조건은 변경하지 않았다. 완료된 경계·음수·재시작·SW 반환·조건부 광학 계산·#201 입력 준비는 완료로 유지한다.

## 실제 실행과 위치

| 항목 | 실제 결과 |
|---|---|
| 모델 step / hourly history | {r['actual_run']['steps']} / {r['history_validity']['records']} |
| LW 양의 native 물경로 로그 | {len(r['actual_run']['LW_source_seconds'])}시각, 600–85,800초 |
| 물리 질량격자 | 143×90, native44층 |
| 같은 관측소의 최근접 격자 | **1-based (37,119)**, zero-based [118,36] |
| 위경도 / 관측소 거리 | {r['site']['model_lat_lon']}, {r['site']['distance_m']/1000:.6f} km |
| 북쪽 물리 경계 거리 | **24셀**, 직접 완화띠 밖 |
| hourly 수분7종·number3종 음수 표본 | **{neg}** |
| hourly 전체 숫자 비유한 표본 | **{r['history_validity']['numeric_nonfinite_elements']}** |
| 실제 실행 자산의 전후 hash | 동일 |

LW 물경로 로그는 native 물경로가 양수일 때만 출력된다. 초기 청천0초가 이 로그에 없다는 것을 호출 누락으로 해석하지 않는다. 전체 LW 호출 횟수의 직접 counter는 관측하지 않았으며 예정된144회를 실제 counter로 바꾸어 집계하지 않는다. 첫 후처리의144개 로그 assertion 실패와 수정은 development에 보존한다.

이는 모든 내부 RK 상태의 양수성을 뜻하지 않는다. 아래 진단 복구 재개는 cold와1,350개 배열이 동일해야 사용하며, 이 한정된 재개 구간의 근거를 모든 재시작 구성으로 확대하지 않는다. 원시 history와 보조 NetCDF를 로컬에서 직접 읽었고 파일 hash·입력·실행파일·계수를 실제 process receipt와 연결했다.

물리 구성은 단일 영역·직렬 one tile, UDM27/LW37/SW37, number1/population0, scalar_adv0, capacity0/liquid-size0, dt60초·복사600초, 기존 experimental frozen1이다. **60초 preflight namelist가 아니라 보존된24시간 forecast namelist**를 사용했다. WPS/REAL/입력 생산은 반복하지 않았다.

## 관측 점수

| 지표, W/m² | 원래 경계 구성24h | 새 내부 구성24h | 원래 주간 | 새 주간 |
|---|---:|---:|---:|---:|
| Bias | {old['all']['bias_W_m2']:+.6f} | {new['all']['bias_W_m2']:+.6f} | {old['daylight']['bias_W_m2']:+.6f} | {new['daylight']['bias_W_m2']:+.6f} |
| MAE | {old['all']['MAE_W_m2']:.6f} | {new['all']['MAE_W_m2']:.6f} | {old['daylight']['MAE_W_m2']:.6f} | {new['daylight']['MAE_W_m2']:.6f} |
| RMSE | {old['all']['RMSE_W_m2']:.6f} | {new['all']['RMSE_W_m2']:.6f} | {old['daylight']['RMSE_W_m2']:.6f} | {new['daylight']['RMSE_W_m2']:.6f} |

하루 적산은 새 모델 **{new['all']['model_energy_MJ_m2']:.6f} MJ/m²**, 같은 관측 주 참조 **{new['all']['reference_energy_MJ_m2']:.6f} MJ/m²**다. 새 최대 절대오차 시간은 **{peak['start_utc']}–{peak['end_utc']}**, signed 오차는 **{peak['primary_error_W_m2']:+.6f} W/m²**다. 보조 PSP 결과는 result.json에 별도로 보존한다.

모델은25개 `ACSWDNB` 끝값의 차/3600으로 계산했다. 관측은 동일 Sterling·UTC·QC0·(시작,종료]의60분, 분별 `DNI×max(cos(SZA),0)+DHI`를 먼저 계산한 평균이다. 원 `observations()`, `hour()`, `statistics()`, `ulp32()`를 그대로 호출한다. 야간 음수·주 참조·보조 PSP·daylight30분 기준도 유지한다. 순간 `SWDOWN`을 점수에 사용하지 않는다. 원래24시간 점수와 원 비교기의99×90/(37,97) guard는 그대로다.

![동일 관측과 두 구성의 시간별 결과](sterling-interior-day-sw.png)

## 사전에 고정한16–17 UTC 복사 상태

| 같은 한 시간 지원, W/m² | 관측 | 새 모델 native held 평균 |
|---|---:|---:|
| 전천 하향 | {obs['primary_W_m2']:.6f} | {m['SWDNB']:.6f} |
| 청천 하향 | 독립 청천 기준 없음 | {m['SWDNBC']:.6f} |
| 수평 직달 | {obs['horizontal_direct_W_m2']:.6f} | {m['SWDDIR']:.6g} |
| 산란 | {obs['DHI_W_m2']:.6f} | {m['SWDDIF']:.6f} |
| 직달법선량 | {obs['DNI_W_m2']:.6f} | {m['SWDDNI']:.6g} |

새 모델 전천−청천은 **{m['all_minus_clear_W_m2']:+.6f} W/m²**다. 분별 성분 관측은 이전 검증에서 보존한 같은60분의 분해를 재사용하고, 현재 채점 함수의 해당 시간 주 참조와 같음을 검사한다. 관측 전천을 청천 참값으로 사용하지 않는다. 모델의 성분·구름효과는 모델 진단이며 독립적인 광학 오차가 아니다.

처음 IO 설정에 제가 넣은 빈 줄 때문에 native parser가 뒤쪽 aux 변수 목록을 읽지 않았다. Cold 하루 적분과 기본 history는 유지했고, 빈 줄만 제거한 설정으로 이 cold의11:58checkpoint에서17:00까지 **추가 진단 재개1회**를 수행했다. 12–17 UTC의225배열×6시각=**1,350쌍이 모두 동일**해야 아래 성분을 사용한다. 원 실행 script/IO와 수정 경위를 development로 보존했으며, 향후 cold runner에도 빈 줄 제거·거부를 반영했다. 생산 소스의 결함 수정이 아니다.

Native 출력 기능만 사용했다. auxhist7은16:00–17:00의61개 끝시각에 표면 성분을 기록한다. **16:01–17:00의60개 period-end flux**가 실제 각60초 누계 갱신을 재현하며, 전천·청천 **120개 REAL32 갱신**과 시간별 끝값이 같다. Flux의 held 평균과 누계 점수의 차이 **{surf['held_minus_accumulator_W_m2']:+.9f} W/m²**는 별도 남긴다. SWDDIR은 unscaled 수평 직달, SWDDNI는 native 호출의 법선 환산값이다. 평균 DNI에 평균 cosine을 곱하지 않는다.

Auxhist8의7개600초 상태는 같은 셀의 CLDFRA·수분6종·QC_CU/QI_CU를 제공한다. **end-of-step q와 이전 호출에서 유지될 수 있는 CLDFRA를, 정확한 어댑터 소비 입력으로 재명명하지 않는다.** UDM_CLDFRA는 별도 진단이고 이 경로의 소비 CF를 대신하지 않는다. Native/CU population의 의미도 합치지 않는다.

시간별 수분 경로는 같은 history의 dry hybrid mass `−DNW×(C1H×(MU+MUB)+C2H)/g`로 재구성했다. Pa 결합 계수를 kg/m² 자체로 표시하지 않으며, 이 history 값이 이전 radiation call의 MUT와 마지막 비트까지 같다고 주장하지 않는다. QCU/QICU가 없는 일반 history 시간은 CU 경로를 **null(미측정)**로 남긴다.16/17시만 실제 aux 상태로 연결한다. 물경로·CF0 부분은 이 상태의 진단이며 실제 solver mask/incloud 경로를 모두 계측한 결과가 아니다.

## 판정과 후속 작업 하나

- 전체시간 RMSE가 원 구성보다 낮음: **{r['new_all_hour_RMSE_lower']}**
- 고정 시간의 양의 CF·수분이 같은 층에 있는 상태 관측: **{r['at_preselected_hour_positive_cloud_state']}**
- 같은 시간 전천 감쇠와 원 구성보다 약한 직달: **{r['at_preselected_hour_cloud_attenuation_and_weaker_direct']}**
- 다음 작업: **{r['decision']}**

목적별 물리 허용량·기준 불확실도·대표성 불확실도는 아직 정하지 않았다. 결과를 본 뒤 통과 기준을 맞추지 않는다. 이 하루 비교가 완료됐다는 것과 일반 예보 정확도·wet hail·전체 물/에너지·RFMIP/LBLRTM이 승인됐다는 것은 다르다.

## 남은 최대 오차를 기존 자료로 좁혔다

새 최대 오차18–19 UTC는 모델 전천663.834722, 청천663.836111 W/m²로 거의 같다. 같은60분 관측은 수평 직달12.168087, 산란290.465000, 합302.633087 W/m²이며 **95.9793%가 산란**이다. 모델18/19시의 max CLDFRA는0이고 액체/비 물경로는0이다. 미량 snow/graupel subnormal 상태는 삭제하지 않고 원 값으로 보존했다.

이는 새 점수로 고른 **후속 해석 구간**이며 원24시간 점수의 기간·셀·QC를 바꾸지 않는다. 새 최대 구간의 모델 직달/산란 시간평균은 직접 계측하지 않았으므로16–17 UTC 값을 옮겨 채우지 않는다. 총/청천 누계와 상태가 지지하는 다음 경계는 **17시 이후의 구름 소실·지속성 시점**이다. source 원인이나 실제 관측 구름의 수직 구조를 확정한 것은 아니다. 순수 영역 효과를 주장하지 않으므로 전처리 일치 대조를 이 판정의 선행조건으로 추가하지 않는다.

## 입력·전처리 차이의 실제 확인

관측소 대응 셀 좌표는 같지만, 공통 구간 전체 좌표는 bitwise 동일하지 않다. 최근접 행·열 대응으로 old j0:99↔new j22:121을 확인했다. 최대 위도 차이는1.52587890625×10⁻⁵도, 경도 차이는3.814697265625×10⁻⁶도다. 첫 분석의 전체 좌표 동일 assertion 실패는 development에 보존했다.

공통 구간 지형 RMS 차이는 **{hgt['difference_RMS']:.6f} m**, 육해 마스크 차이는 **{land['different_elements']}셀**이다. 관측소 지형은 **{hgt['site_old']:.6f}→{hgt['site_new']:.6f} m**다. 토지이용·토양·지표/토양 상태·초기 P/T/QV의 원/새 차이를 별도 input-contrast에 보존한다. 저장 초기 T는 theta 표현으로 대조하며 실제 기온으로 오독하지 않는다.

영역 확장과 WPS4.3→4.6·lowres 지리자료가 함께 변했다. 이번 차이만으로 순수 영역 효과를 구할 수 없다. [공식 저해상도 지리자료 안내](https://www2.mmm.ucar.edu/wrf/users/download/get_sources_wps_geog.html)의 시험·교육용 한계와 응결물 미제공 기본0 가정은 유지한다. 24셀 안쪽이라는 사실도 간접 경계 영향을 배제하지 않는다. 순수 영역 인과성이 필요할 때만 같은 WPS·지리자료의 작은 영역 대조를 수행한다.

## 수행·재생 범위

실제 WRF 실행은 **cold24h1회와 IO 복구용11:58–17:00 진단 재개1회**, 총2회다. 새 build·WPS·REAL·Mie·standalone RTE는0회다. 하루를 처음부터 반복하지 않았으며, 두 실행을 독립 기상 사례2개로 집계하지 않는다. 추가 native IO는16–17 UTC에 한정하며 생산 소스를 계측용으로 재컴파일하지 않았다. 실행 source/table/input/namelist의 전후 동일성을 보존한다. 실행시간은 receipt의 실제 측정값이며13/9 격자 수 비율을 시간·정확도 배율로 쓰지 않는다.

```sh
python3 -I -S validation/rrtmgp37/sterling-interior-day-evaluation/verify_saved.py
python3 -I -S validation/rrtmgp37/sterling-interior-day-evaluation/test_saved.py
```

저장 검증은 실제 추출·입력/실행/계수 연결·새 격자·같은 관측 함수·성분의 실제 누계 갱신을 재생한다. 원 NetCDF는 로컬에서 직접 판독했고 큰 파일은 hash와 로컬 경로로 보존한다. CI는 큰 NetCDF를 다시 열거나 모델을 실행하지 않으며 `new_model_runs_in_saved_replay=0`이다.7개 의미 시험은 옛 인덱스, 옛 guard 완화, 순간값의 점수 혼용, UTC 이동, 잘못된 실제 flux, QC 채움, 사후 허용량 변경을 검사한다. 기존 일곱 최상위 종료 조건은 늘리지 않았다.
'''
 (P/'README.md').write_text(text)
if __name__=='__main__':main()
