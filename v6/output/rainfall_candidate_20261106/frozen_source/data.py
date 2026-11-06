"""Independent gauge labels and sensor-quality-aware soil histories."""
import bisect
import collections
import csv
import datetime as dt
import math
from pathlib import Path
import re

from common import TIP_MM, WIB, digest, wib

SOURCES = {'X50': Path('C:/Users/isnad/Documents/X50.csv'), 'X66': Path('C:/Users/isnad/Documents/X66.csv')}
DEVICES = {'X50': '905f99c0-9d9f-11ef-a405-d769fcc61350', 'X66': '15955490-112b-11f1-8347-3d92fc978ff9'}
KNOWN_CODES = {'E2','E3','E4','E5','E8','E11','E12','E16'}


def number(value):
    try:
        v=float(value)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError): return None


def normalize(raw):
    codes=set(re.findall(r'\bE\d+\b',raw.get('error','').upper()))
    unknown=codes-KNOWN_CODES
    rf,rfc,srm,sm=[number(raw.get(k)) for k in ['rf','rfc','srm','sm']]
    rain_ok=not unknown and 'E4' not in codes and rf is not None and rfc is not None and min(rf,rfc)>=0
    soil_ok=not unknown and 'E11' not in codes and srm is not None and srm>0
    return {'time':int(raw['timestamp_ms'])/1000,'rf':rf,'rfc':rfc,'srm':srm if soil_ok else None,
        'sm':sm if soil_ok and sm is not None and 0<=sm<=100 else None,
        'rid':number(raw.get('rid')),'rain_ok':rain_ok,'soil_ok':soil_ok,'error':raw.get('error','').strip()}


def rain_hours(records):
    intervals,counts={},collections.Counter()
    for a,b in zip(records,records[1:]):
        na,nb=round(a['time']/600)*600,round(b['time']/600)*600
        reason=None
        if not a['rain_ok'] or not b['rain_ok']: reason='sensor_or_value_invalid'
        elif b['rfc']<a['rfc']: reason='counter_reset'
        elif not 0<b['time']-a['time']<=900: reason='sampling_gap'
        elif abs(b['rf']-(b['rfc']-a['rfc'])*TIP_MM)>.011: reason='rf_counter_mismatch'
        elif abs(a['time']-na)>90 or abs(b['time']-nb)>90 or nb-na!=600: reason='clock_alignment'
        if reason:
            counts[reason]+=1;continue
        if nb in intervals: raise ValueError('Duplicate nominal ten-minute interval')
        intervals[nb]={'amount':b['rf'],'observed_at':b['time'],'available_at':b['time']+3600}
    hours={}
    start=math.ceil(records[0]['time']/3600)*3600
    end=math.floor(records[-1]['time']/3600)*3600
    for target in range(start,end+1,3600):
        pieces=[intervals.get(target-k*600) for k in range(6)]
        good=[p for p in pieces if p is not None]
        hours[target]={'time':target,'rain':sum(p['amount'] for p in good) if len(good)==6 else None,
            'interval_count':len(good),'observed_at':max((p['observed_at'] for p in good),default=None),
            'available_at':max((p['available_at'] for p in good),default=None)}
    counts.update(complete_hours=sum(r['rain'] is not None for r in hours.values()),incomplete_hours=sum(r['rain'] is None for r in hours.values()))
    return hours,intervals,dict(counts)


def read_sources():
    data,quality={},{}
    for station,path in SOURCES.items():
        checksum=digest(path)
        with path.open(encoding='utf-8-sig',newline='') as stream: raw=list(csv.DictReader(stream))
        if {r['device_id'] for r in raw}!={DEVICES[station]}: raise ValueError('Unexpected station identity: '+station)
        records=sorted((normalize(r) for r in raw),key=lambda r:r['time'])
        if len({r['time'] for r in records})!=len(records): raise ValueError('Duplicate source timestamps')
        for r in raw:
            local=dt.datetime.strptime(r['time_WIB'],'%Y-%m-%d %H.%M.%S.%f').replace(tzinfo=WIB).timestamp()
            if abs(local-int(r['timestamp_ms'])/1000)>.01: raise ValueError('WIB/Unix timestamp mismatch')
        hours,intervals,qc=rain_hours(records)
        data[station]={'records':records,'hours':hours,'intervals':intervals,'times':[r['time'] for r in records]}
        quality[station]={'source':str(path),'sha256':checksum,'readings':len(records),'first_wib':wib(records[0]['time']),
            'last_wib':wib(records[-1]['time']),'error_counts':dict(collections.Counter(r['error'] for r in records)),
            'quality_counts':qc,'valid_soil_readings':sum(r['soil_ok'] for r in records),
            'raw_recorded_rain_mm':sum(r['rf'] or 0 for r in records),
            'checked_ten_minute_rain_mm':sum(p['amount'] for p in intervals.values()),
            'complete_hour_rain_mm':sum(r['rain'] for r in hours.values() if r['rain'] is not None),
            'gaps_gt_15_minutes':sum(b['time']-a['time']>900 for a,b in zip(records,records[1:]))}
    return data,quality


def soil_change(data,end,minutes):
    """Observed soil change ending at a chosen reading; no gap/reset interpolation."""
    records,times=data['records'],data['times']
    i=bisect.bisect_right(times,end)-1
    if i<0 or end-times[i]>90 or not records[i]['soil_ok']: return None
    target=records[i]['time']-minutes*60
    j=bisect.bisect_left(times,target-90)
    if j>=i or abs(times[j]-target)>90: return None
    pieces=records[j:i+1]
    if not all(p['soil_ok'] for p in pieces): return None
    if any(b['time']-a['time']>900 or (a['rid'] is not None and b['rid'] is not None and b['rid']<a['rid']) for a,b in zip(pieces,pieces[1:])): return None
    return {'drop_pct':100*(pieces[0]['srm']-pieces[-1]['srm'])/pieces[0]['srm'],
        'sm_change':pieces[-1]['sm']-pieces[0]['sm'] if pieces[0]['sm'] is not None and pieces[-1]['sm'] is not None else None,
        'srm_range_pct':100*(max(p['srm'] for p in pieces)-min(p['srm'] for p in pieces))/pieces[0]['srm']}


def window_label(station_data,issue,hours,cutoff=None):
    points=[station_data['hours'].get(issue+k*3600) for k in range(1,hours+1)]
    if all(p is not None and p['rain'] is not None for p in points):
        available=max(p['available_at'] for p in points)
        if cutoff is not None and available>=cutoff: return None
        return {'amount':sum(p['rain'] for p in points),'available_at':available,'end':issue+hours*3600,'source':'complete_rf_intervals'}
    # A cumulative gauge can recover a whole-window total when both boundaries
    # were measured and missing packets have continuous device record IDs. Never
    # allocate those tips to unknown subintervals or borrow the neighboring gauge.
    records,times=station_data['records'],station_data['times']
    end=issue+hours*3600
    i=bisect.bisect_right(times,issue+90)-1;j=bisect.bisect_right(times,end+90)-1
    if i<0 or j<=i or abs(times[i]-issue)>90 or abs(times[j]-end)>90:return None
    pieces=records[i:j+1]
    if not all(p['rain_ok'] for p in pieces):return None
    for a,b in zip(pieces,pieces[1:]):
        delta=b['rfc']-a['rfc'];elapsed=b['time']-a['time'];steps=round(elapsed/600)
        if delta<0 or elapsed<=0 or abs(elapsed-steps*600)>90:return None
        if a['rid'] is not None and b['rid'] is not None and b['rid']<a['rid']:return None
        if elapsed>900:
            if a['rid'] is None or b['rid'] is None or b['rid']-a['rid']!=steps:return None
            if b['rf']>delta*TIP_MM+.011:return None
        elif abs(b['rf']-delta*TIP_MM)>.011:return None
    available=pieces[-1]['time']+3600
    if cutoff is not None and available>=cutoff:return None
    return {'amount':(pieces[-1]['rfc']-pieces[0]['rfc'])*TIP_MM,'available_at':available,
        'end':end,'source':'counter_endpoints_packet_continuity'}
