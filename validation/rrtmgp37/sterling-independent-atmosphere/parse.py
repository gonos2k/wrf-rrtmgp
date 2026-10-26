"""Raw archive parsing with explicit time, missing and observation conventions."""
import csv,io,datetime as dt,re,math
UTC=dt.timezone.utc
MISSING={-8888,-9999}
def require(ok,message):
 if not ok:raise ValueError(message)
def elapsed_seconds(value):
 if value in MISSING:return None
 require(value>=0 and value%100<60,'IGRA elapsed MMMSS')
 return value//100*60+value%100

def sounding(raw):
 lines=raw.decode('ascii').splitlines();h=lines[0]
 require(h.startswith('#USM00072403') and len(lines)-1==int(h[32:36]),'IGRA station/NUMLEV')
 nominal=dt.datetime(*map(int,[h[13:17],h[18:20],h[21:23],h[24:26]]),tzinfo=UTC)
 rel=h[27:31];release=None
 if rel!='9999' and rel[-2:]!='99':
  base=nominal.replace(hour=int(rel[:2]),minute=int(rel[2:]));release=min([base+dt.timedelta(days=n) for n in [-1,0,1]],key=lambda d:abs((d-nominal).total_seconds()))
 fields={'elapsed':(3,8),'p_Pa':(9,15),'z_msl_m':(16,21),'T_tenth_C':(22,27),'RH_tenth_percent':(28,33),'DPDP_tenth_C':(34,39),'wind_from_deg':(40,45),'wind_tenth_m_s':(46,51)}
 levels=[]
 for idx,line in enumerate(lines[1:],1):
  r={'record':idx,'level_type':[int(line[0]),int(line[1])],'PFLAG':line[15],'ZFLAG':line[21],'TFLAG':line[27]}
  vals={k:int(line[a:b]) for k,(a,b) in fields.items()}
  r['original_integer_fields']=vals
  for k,v in vals.items():r[k]=None if v in MISSING else v
  r['elapsed_s']=elapsed_seconds(vals['elapsed']);r['actual_UTC']=(release+dt.timedelta(seconds=r['elapsed_s'])).isoformat() if release and r['elapsed_s'] is not None else None
  r['T_K']=None if r['T_tenth_C'] is None else r['T_tenth_C']/10+273.15
  r['Td_K']=None if r['T_K'] is None or r['DPDP_tenth_C'] is None else r['T_K']-r['DPDP_tenth_C']/10
  r['reported_RH_ratio']=None if r['RH_tenth_percent'] is None else r['RH_tenth_percent']/1000
  r['wind_speed_m_s']=None if r['wind_tenth_m_s'] is None else r['wind_tenth_m_s']/10
  if r['wind_from_deg'] is not None and r['wind_speed_m_s'] is not None:
   a=math.radians(r['wind_from_deg']);r['wind_u_east_m_s']=-r['wind_speed_m_s']*math.sin(a);r['wind_v_north_m_s']=-r['wind_speed_m_s']*math.cos(a)
  else:r['wind_u_east_m_s']=r['wind_v_north_m_s']=None
  levels.append(r)
 surface=next((r['z_msl_m'] for r in levels if r['level_type'][1]==1 and r['z_msl_m'] is not None),None)
 for r in levels:r['z_agl_m']=None if surface is None or r['z_msl_m'] is None else r['z_msl_m']-surface
 return {'station':h[1:12],'nominal_UTC':nominal.isoformat(),'release_HHMM':rel,'release_UTC':release.isoformat() if release else None,'release_date_rule':'nearest candidate date to nominal hour; no missing release/time fill','archive_coordinate_lat_lon':[int(h[55:62])/10000,int(h[63:71])/10000],'coordinate_scope':'IGRA fixed-station header coordinates are not sounding-by-sounding historical location or balloon drift','surface_geopotential_msl_m':surface,'levels':levels}

def metars(raw):
 rows=[];seen=set()
 for r in csv.DictReader(io.StringIO(raw.decode())):
  require(r['station'] in ['IAD','DCA','BWI'],'unexpected ASOS station');key=(r['station'],r['valid'],r['metar']);require(key not in seen,'duplicate METAR');seen.add(key)
  body=r['metar'].split(' RMK')[0];layers=[{'amount':a,'base_agl_m':None if b=='///' else int(b)*100*.3048,'original_hundreds_ft':b} for a,b in re.findall(r'\b(FEW|SCT|BKN|OVC)(\d{3}|///)\b',body)]
  ceiling=[l['base_agl_m'] for l in layers if l['amount'] in ['BKN','OVC'] and l['base_agl_m'] is not None]
  group=re.search(r'\bT([01])(\d{3})([01])(\d{3})\b',r['metar']);temp=dew=None;kind='missing'
  if group:
   a,b,c,d=group.groups();temp=(-1 if a=='1' else 1)*int(b)/10;dew=(-1 if c=='1' else 1)*int(d)/10;kind='raw METAR T-group, tenthC'
  else:
   g=re.search(r'\b(M?\d{2})/(M?\d{2})\b',body)
   if g:temp,dew=[-int(x[1:]) if x.startswith('M') else int(x) for x in g.groups()];kind='raw METAR body, wholeC'
  wind=re.search(r'\b(VRB|\d{3})(\d{2,3})(?:G(\d{2,3}))?KT\b',body)
  direction=None if not wind or wind[1]=='VRB' else int(wind[1]);speed=None if not wind else int(wind[2])*.5144444444444445
  rows.append({'station':r['station'],'time_UTC':r['valid'].replace(' ','T')+':00+00:00','metadata_lat_lon':[float(r['lat']),float(r['lon'])],'metadata_elevation_m':float(r['elevation']),'raw_METAR':r['metar'],'layers':layers,'ceiling_agl_m':min(ceiling) if ceiling else None,'low_level_clear_reported':bool(re.search(r'\b(CLR|SKC)\b',body)),'T_C':temp,'Td_C':dew,'temperature_source':kind,'wind_from_deg':direction,'wind_speed_m_s':speed,'wind_variable':bool(wind and wind[1]=='VRB'),'decoded_archive_row':r})
 return rows

def interpolate(profile,p,field):
 """Log-pressure interpolate valid values only, retaining original bracket records."""
 valid=[x for x in profile if x.get('p_Pa') is not None and x.get(field) is not None and x['p_Pa']>0]
 valid=sorted(valid,key=lambda x:-x['p_Pa'])
 for x in valid:
  if p==x['p_Pa']:return {'value':x[field],'bracket_records':[x.get('record'),x.get('record')],'bracket_pressures_Pa':[p,p]}
 for a,b in zip(valid,valid[1:]):
  if a['p_Pa']>p>b['p_Pa']:
   f=(math.log(p)-math.log(a['p_Pa']))/(math.log(b['p_Pa'])-math.log(a['p_Pa']));return {'value':a[field]+f*(b[field]-a[field]),'bracket_records':[a.get('record'),b.get('record')],'bracket_pressures_Pa':[a['p_Pa'],b['p_Pa']]}
 return None

def distance(a,b):
 p,q=map(math.radians,[a[0],b[0]]);x=math.sin((p-q)/2)**2+math.cos(p)*math.cos(q)*math.sin(math.radians(a[1]-b[1])/2)**2
 return 2*6371000*math.asin(math.sqrt(x))
