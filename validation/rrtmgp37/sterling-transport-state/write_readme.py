"""Render a concise science decision from the actual retained native face result."""
from pathlib import Path
import json
P=Path(__file__).resolve().parent

def main():
 r=json.loads((P/'result.json').read_text());hs={h['start_hour_UTC']:h['layers'][1] for h in r['hourly']};total=r['five_hour_layers'][1];h15=hs[15];rows=[];flows=[]
 for hour,x in hs.items():
  s=x['sums'];m=x['means'];rows.append(f"| {hour}–{hour+1} | {s['dry_theta_paired_horizontal_K']:+.6f} | {s['dry_theta_paired_vertical_K']:+.6f} | {s['qv_horizontal_g_kg']:+.6f} | {s['qv_vertical_g_kg']:+.6f} | {s['qv_center_relative_face_g_kg']:+.6f} | {s['qv_center_mass_convergence_g_kg']:+.6f} |")
  flows.append(f"| {hour}–{hour+1} | {m['qv_eta_mass_flux_lower_native_Pa_s']:+.6f} | {m['qv_eta_mass_flux_upper_native_Pa_s']:+.6f} | {m['qv_pred_above_minus_center_g_kg']:+.6f} | {m['dry_theta_pred_above_minus_center_K']:+.6f} | {m['geometric_W_lower_m_s']:+.6f} | {m['geometric_W_upper_m_s']:+.6f} |")
 g=r['prior_state_evidence']['hourly_central_states'];state=[]
 for h in g:
  a,b=[next(x for x in h['profiles'] if x['record']==k) for k in [7,8]];state.append(f"| {h['hour_UTC']} | {b['dry_theta_K']-a['dry_theta_K']:+.6f} | {1000*(b['qv_kg_kg']-a['qv_kg_kg']):+.6f} | {b['z_msl_m']-a['z_msl_m']:.3f} |")
 context=[]
 for x in r['source_hour_horizontal_context']:
  if x['k']==8:context.append(f"| {x['source_hour_UTC']} | {x['dry_theta_east_minus_west_two_native_cells_K']:+.6f} | {x['dry_theta_north_minus_south_two_native_cells_K']:+.6f} | {x['qv_east_minus_west_two_native_cells_g_kg']:+.6f} | {x['qv_north_minus_south_two_native_cells_g_kg']:+.6f} | {x['grid_U_masspoint_mean_of_two_staggered_faces_m_s']:+.6f} | {x['grid_V_masspoint_mean_of_two_staggered_faces_m_s']:+.6f} |")
 old=json.loads((P.parent/'sterling-thermodynamic-tendencies/result.json').read_text());totals=[]
 for x in r['five_hour_layers']:
  k=x['k'];v=x['sums'];layer_state=next(z for z in old['five_hour_layers'] if z['k']==k);totals.append(f"| {k} | {layer_state['dry_theta_change_K']:+.6f} | {v['dry_theta_paired_horizontal_K']:+.6f} | {v['dry_theta_paired_vertical_K']:+.6f} | {layer_state['qv_change_g_kg']:+.6f} | {v['qv_horizontal_g_kg']:+.6f} | {v['qv_vertical_g_kg']:+.6f} |")
 s=h15['sums'];m=h15['means'];count=h15['qv_mass_flux_both_positive_steps'];qneg=h15['qv_pred_above_drier_steps'];wneg=h15['geometric_W_both_negative_steps']
 text=f'''# Sterling native7–8 transport, consumed state and coordinate decision

PR #206의 실제 12–17 UTC 경향 귀속을 완료로 유지하고, 부족했던 **실제 수직 face·η 질량 flux·소비 stencil**만 연결했다. 공개 생산 WRF·UDM·RTE, 광학계수·기본 정책은 변경하지 않았다. 기준은 `85af9c7f8e1fec2dd9dbefb8591e4df06197d16a`이며, 고정 기주 `(i,j)=(37,119)`, native7–8층, 2016-10-06 UTC이다.

**판정:** 수송의 시간별 부호를 실제 면 교환과 좌표 정의로 설명하는 이번 단계는 완료다. 보존형 수직수송의 습윤화가 곧 위층의 습윤화나 상승류를 뜻하지는 않는다. 현재 자료에서 새 생산 결함·PBL 계수 오류·광학 보정 근거는 확정하지 않았다. 고정 직렬 연구 기준선과 오후 예보 적용 제한을 유지한다.

## 기존 자료를 먼저 재사용했다

[PR206 경향 결과](../sterling-thermodynamic-tendencies/README.md)의 step·시간별 항과 12–16시의 7×7,k4–13 주변 상태 2,450개를 먼저 읽었다. 같은 qualified cold의 기존 history를 실제로 다시 읽어 12–17시의 압력·건조 온위·수증기·geopotential 높이·η·기하학적 `W`를 연결했다. 중심 6개 profile과 고정 7×7의 294개 profile을 보존했다. native 층은 고정 압력면이나 공기덩이가 아니다.

| UTC | history θd8−θd7, K | qv8−qv7, g/kg dry | 질량점 높이8−7, m |
|---|---:|---:|---:|
{chr(10).join(state)}

이 표는 8−7층 대비이고, 아래 소비 기울기 표의 8층 항은 9−8층 대비다.

7→8층의 건조 온위 대비와 수증기 대비가 강화되지만, 이 시간별 자료 자체를 60초 과정 경향으로 쓰지 않는다. history의 `T+300`은 저장된 dry 온위이고, PR206 주변 기록 및 새 theta face의 field는 moist 온위 섭동이다.

기존 history에는 `W/U/V`가 있고 **WW·WWM·OMEGA는 없었다**. 기존 acoustic `wdtn`은 섭동 항이므로 총 η mass flux로 대체할 수 없다. 이 부족한 경계에 한해 같은 11:58 checkpoint에서 17:00까지 private read-only 관측 실행 1회를 했다. 새 cold24h나 전체 물리 경향 재계측은 하지 않았다.

### 기존 주변 자료의 수평 상태도 보존한다

8층에서 중심의 동−서, 북−남 이웃 두 native cell 차이와 두 staggered 면을 평균한 grid U/V이다. 지리 동서/남북으로 회전한 관측 바람이나 실제 face flux가 아니다. 7층 및 고정7×7 min/max는 결과 JSON에 함께 있다.

| UTC | θ E−W, K | θ N−S, K | qv E−W, g/kg | qv N−S, g/kg | grid U, m/s | grid V, m/s |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(context)}

이 중앙 차분과 바람의 곱을 native 고차·보존형 수평 경향으로 대체하지 않는다. 시간별 실제 H/V 항과 주변 상태가 함께 남으므로 공기 유입의 해석에서 방향·시각·질량 정규화를 추가로 확인할 수 있다. 주변의 잘 맞는 격자로 관측 점수를 교체하지 않는다.

## 5시간 합계와 시간별 반전을 함께 보존한다

12–17시 합계는 다음과 같다. 순변화에는 표에 생략한 물리·확산·정규화·산술 항도 포함되므로 H+V만을 순변화와 같다고 요구하지 않는다.

| native 층 | 실제 Δθd, K | θ H, K | θ V, K | 실제 Δqv, g/kg | qv H, g/kg | qv V, g/kg |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(totals)}

아래 θ는 PR206의 **slow+acoustic+수증기 변환을 포함한 paired dry 온위 기여**이다. qv H/V는 실제 final-RK 보존형 연산 기여다. 기존 상태 오차·물리항·정규화 항과 원래 일사 점수는 모두 유지한다.

| UTC | θ H, K | θ V, K | qv H, g/kg | qv V, g/kg | qv 중심 상대 face항 | qv 중심×질량flux차 항 |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

8층의 5시간 qv 수직 기여는 **{total['sums']['qv_vertical_g_kg']:+.6f} g/kg**이나, 15–16시에는 **{s['qv_vertical_g_kg']:+.6f} g/kg**으로 습윤화한다. 같은 시간 수평 기여는 **{s['qv_horizontal_g_kg']:+.6f} g/kg**으로 더 크게 건조화한다. 12–15시의 초기 구조 발달과 15–17시의 아래층 물리 냉각을 하나의 지속적인 수직 건조화로 묶지 않는다.

### 실제 소비 mass flux와 기울기

다음은 각 시간의 60개 actual final-RK 호출 평균이다. qv는 acoustic 시간평균 mass flux를 사용한 PD 경로, W는 theta predictor 시점의 별도 기하학적 interface 속도다. 서로 다른 단위·시간 지원을 의도적으로 구분한다. 기울기는 실제 소비한 predictor에서 해당 층 위 질량점−중심점이다.

| UTC | PD η flux 하단, native Pa/s | 상단, native Pa/s | qv 위−중심, g/kg | θd 위−중심, K | geometric W 하단, m/s | 상단, m/s |
|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(flows)}

15–16시에는 위층이 더 건조한 step이 **{qneg}/60**, 두 PD η flux가 양수인 step이 **{count}/60**, 두 기하학적 W가 음수인 predictor step이 **{wneg}/60**이다. 이 조건과 qv 수직 습윤화가 공존한다. 따라서 qv 수직 항의 양수만 보고 상승류나 위층의 습윤 공급을 추론하면 안 된다.

### 두 면의 실제 flux를 연결한 항등식

native η는 k가 증가할수록 감소한다. 실제 갱신은 `−rdnw*(Ftop−Fbottom)`이며, PD의 F는 **제한된 antidiffusive flux와 low-order flux를 함께** 포함한다. 중심의 실제 transported field를 q₀, 각 면 mass flux를 M으로 놓으면

```text
Ftop − Fbottom
= [(Ftop − q₀ Mtop) − (Fbottom − q₀ Mbottom)]
  + q₀ (Mtop − Mbottom).
```

이 선언된 중심 기준 분해에서 15–16시 8층 qv의 상대 face항은 **{s['qv_center_relative_face_g_kg']:+.6f} g/kg**, 중심×질량flux차 항은 **{s['qv_center_mass_convergence_g_kg']:+.6f} g/kg**이다. 그 합과 별도 보고한 native 반올림 차이가 실제 qv V를 재구성한다. 위쪽의 건조한 기울기가 있어도 두 면의 mass flux 차이까지 포함한 보존형 항의 부호는 달라질 수 있다.

**두 항의 배분은 중심 기준값에 의존한다.** 질량수렴 항을 독립 수증기 생성량으로 부르거나, 정규화·수평 연속식을 떼어 전체 물수지로 승인하지 않는다. 전체/시간별 원 경향은 바꾸지 않으며 진단 잔차를 특정 물리항에 맞추지 않는다. F/M을 정의할 수 없는 0 mass-flux 면은 유효 혼합비를 만들지 않고 null로 보존한다.

θ 수송에서 실제 field는 **moist 온위의 섭동**이다. face 분해에 dry θ 또는 `+300`을 임의로 대입하지 않는다. slow θ 면항, acoustic θ 항, paired qv 변환항을 별도로 보존하므로 slow face항 하나를 기존 θ V 총량으로 부르지 않는다.

## 좌표·시각·관측이 허용하는 주장

- `rom`은 실제 호출에 전달된 map-coupled η vertical mass flux다. 양수는 증가하는 η 방향이다. geometric W나 pressure omega가 아니다. `rdnw`, η, C1/C2, MU/MUB/MUT, map factor와 geopotential 인터페이스를 함께 보존했다.
- theta `rk_tendency`는 순간 predictor `wwE`, PD qv는 acoustic 시간평균 `ww_m`에서 `WW_SPLIT`을 거친 값을 소비한다. 실제 q predictor와 source-updated `field_old`도 각각 기록한다. 같은 상태·시간이라고 가정하지 않는다.
- 관측 profile과 모델의 7→8층 온습도 구조 차이는 [PR204 관측](../sterling-independent-atmosphere/README.md)과 [PR205 입력 계보](../sterling-low-level-evolution/README.md)에 보존돼 있다. 실제 상승시각·풍선 이동·약9 km 위치차·27 km 격자 대표성의 제한도 유지한다. 그 관측은 **모델의 η flux 또는 수직운동 정확도**를 직접 검증하지 않는다.
- 관측의 지표 직달 억제·저층운과 모델 오후 청천화의 차이는 그대로 남는다. forcing의 내부 분석 기주를 강제 source나 독립 수직운동 참값으로 사용하지 않는다.

**다음 조치:** 생산 정책과 계수는 유지하고, 오후 구름·일사의 정량적 적용은 보류한다. 물리적 원인 판단을 계속할 경우 온난·건조한7–8층 공기의 **시간별 수평 face 수송·질량 정규화와 주변 기울기·관측/구동장 바람·온습도**를 연결하는 한 경계로 좁힌다. 현재 관측이 제약하지 못하는 수직운동을 오류로 확정하거나, 이미 완료한5시간 경향 귀속과 구름 최종 증발 추적을 반복하지 않는다.

## 실제 실행·재생·무영향 근거

- 공개 생산 코드·계수·정책 변경: **0**. private observer 빌드 **6개 명령**(4 compile+archive+link), 한정 WRF 재개 **1회**, 기존 NetCDF 재판독. 새 cold24h·WPS·REAL·독립 RTE/Mie·포화함수 실행: **0**.
- 기존 cold의 225개 배열×12–17시 6시각 = **1,350쌍 바이트 동일**. 이 무영향 확인을 새 일반 재시작 캠페인이나 독립 기상 사례로 세지 않는다.
- 실제 source 300 step,7–8층의 θ 수직발산 **600건**, PD qv 수직발산 **600건**, θ 3차 face **1,200건**을 native REAL32 순서로 재생. #206의 해당 수직 갱신 **600건**과 일치한다.
- `step-faces.csv` 600행과 `result.json`의5시간·시간별 통계 및 기존 관측 점수를 원 저장 피연산자로 재생한다. `verify_saved.py`는 표준 라이브러리만 사용하며 CI에서 새 모델·NetCDF 실행을 하지 않는다. archive·실제 빌드·실행 receipt·compiled source·동일 입력 및 기존 자료의 해시/크기를 연결한다.
- 원래 일곱 종료 조건, frozen1의 실험성·물성/밀도 계약, RFMIP/LBLRTM, 전체 물·에너지 미승인은 유지한다. 이번 수치 재생을 물리 정확도 승인으로 바꾸지 않는다.

![같은 시간별 수송·면 분해](transport-state.png)

```sh
python -I -S validation/rrtmgp37/sterling-transport-state/verify_saved.py
python -I -S validation/rrtmgp37/sterling-transport-state/test_saved.py
```
'''
 (P/'README.md').write_text(text)
if __name__=='__main__':main()
