from pathlib import Path
import gzip,json,struct
B=Path(__file__).resolve().parent.parent/'udm37-grid-threshold-pr-work/validation/rrtmgp37/lbl-grid-threshold-comparison'
m=json.loads((B/'samples.json').read_text());arms={};coords={}
for a,rs in m.items():
    x=[]
    for r in rs:
        lo,hi,h,n,pad=struct.unpack('<dddii',gzip.decompress((B/f"OD/{a}.{r['panel']}.header.gz").read_bytes()))
        j=round((r['nu']-lo)/h);x.append(lo+j*h)
    coords[a]=x;arms[a]={'target_actual_coordinate':x[40],'max_abs_planned_coordinate_residual':max(abs(t-r['nu']) for t,r in zip(x,rs))}
result={'computed_from_actual_saved_panel_headers':True,'arms':arms,
 'target_coordinate_bit_identical_across_arms':len({struct.pack('<d',v[40]) for v in coords.values()})==1,
 'maximum_cross_arm_coordinate_mismatch':max(abs(v[j]-coords['h'][j]) for v in coords.values() for j in range(81))}
(B/'coordinate-diagnostic.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
