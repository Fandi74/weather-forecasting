"""Only measurements available at forecast issue; no future soil is a predictor."""
import bisect
import datetime as dt
import math

from common import WIB
from data import soil_change

BASE=['station_X66','window_hours','gfs_age_hours','gfs_rain_sum','gfs_rain_max','gfs_wet_hours',
      'gfs_temperature_mean','gfs_humidity_mean','gfs_humidity_min','hour_sin','hour_cos']
RAIN=['rain_latest_mm','rain_age_hours','rain_3h_mm','rain_3h_coverage','rain_6h_mm','rain_6h_coverage','last_wet_age_hours']
SOIL=['srm_latest','sm_latest','soil_age_hours','srm_drop_30m_pct','srm_drop_60m_pct','srm_drop_180m_pct','srm_range_180m_pct','sm_change_60m']
FAMILIES=['gfs','local_rain','local_rain_soil','network_rain','network_rain_soil']


def names(family):
    if family not in FAMILIES: raise ValueError(family)
    result=list(BASE)
    if family!='gfs': result += ['own_'+k for k in RAIN]
    if family in ['local_rain_soil','network_rain_soil']: result += ['own_'+k for k in SOIL]
    if family in ['network_rain','network_rain_soil']: result += ['neighbor_'+k for k in RAIN]
    if family=='network_rain_soil': result += ['neighbor_'+k for k in SOIL]
    return result


class History:
    def __init__(self,data):
        self.data=data;self.cache={};self.audit=[]
        self.rain={s:sorted([p for p in d['hours'].values() if p['rain'] is not None],key=lambda p:p['available_at']) for s,d in data.items()}
        self.rain_arrivals={s:[p['available_at'] for p in rows] for s,rows in self.rain.items()}

    def get(self,station,issue):
        key=(station,issue)
        if key in self.cache:return self.cache[key]
        data=self.data[station];used=[]
        rindex=bisect.bisect_right(self.rain_arrivals[station],issue)
        rain=self.rain[station][:rindex]
        latest=rain[-1] if rain else None
        values={k:None for k in RAIN+SOIL}
        age=(issue-latest['observed_at'])/3600 if latest else None
        values['rain_age_hours']=age
        recent=latest is not None and age<=6
        if recent:
            values['rain_latest_mm']=latest['rain'];used.append(latest['available_at'])
        by_time={p['time']:p for p in rain}
        for hours in [3,6]:
            points=[by_time.get(latest['time']-k*3600) for k in range(hours)] if recent else []
            good=[p for p in points if p is not None]
            values[f'rain_{hours}h_coverage']=len(good)/hours
            values[f'rain_{hours}h_mm']=sum(p['rain'] for p in good) if len(good)==hours else None
            used += [p['available_at'] for p in good]
        wet=[p for p in rain if p['rain']>=.28-1e-9 and issue-p['observed_at']<=72*3600]
        if wet:
            values['last_wet_age_hours']=(issue-wet[-1]['observed_at'])/3600;used.append(wet[-1]['available_at'])
        i=bisect.bisect_right(data['times'],issue-3600)-1
        while i>=0 and not data['records'][i]['soil_ok']:i-=1
        soil=data['records'][i] if i>=0 else None
        soil_age=(issue-soil['time'])/3600 if soil else None
        values['soil_age_hours']=soil_age
        if soil is not None and soil_age<=6:
            if soil['time']+3600>issue:raise ValueError('Future/unreceived soil feature')
            values.update(srm_latest=soil['srm'],sm_latest=soil['sm']);used.append(soil['time']+3600)
            for minutes in [30,60,180]:
                change=soil_change(data,soil['time'],minutes)
                if change is not None:
                    values[f'srm_drop_{minutes}m_pct']=change['drop_pct']
                    if minutes==60:values['sm_change_60m']=change['sm_change']
                    if minutes==180:values['srm_range_180m_pct']=change['srm_range_pct']
        if used and max(used)>issue:raise ValueError('Feature receipt after issue')
        self.audit.append({'station':station,'issue':issue,'max_measurement_receipt_used':max(used) if used else None,
            'rain_age_hours':age,'soil_age_hours':soil_age})
        self.cache[key]=values
        return values


def base_features(station,issue,horizon,source_issue,forecasts):
    hour=dt.datetime.fromtimestamp(issue,WIB).hour
    return {'station_X66':int(station=='X66'),'window_hours':horizon,'gfs_age_hours':(issue-source_issue)/3600,
        'gfs_rain_sum':sum(r['forecast_rain'] for r in forecasts),'gfs_rain_max':max(r['forecast_rain'] for r in forecasts),
        'gfs_wet_hours':sum(r['forecast_rain']>=.1 for r in forecasts),
        'gfs_temperature_mean':sum(r['forecast_t'] for r in forecasts)/horizon,
        'gfs_humidity_mean':sum(r['forecast_h'] for r in forecasts)/horizon,'gfs_humidity_min':min(r['forecast_h'] for r in forecasts),
        'hour_sin':math.sin(2*math.pi*hour/24),'hour_cos':math.cos(2*math.pi*hour/24)}


def all_features(station,issue,horizon,source_issue,forecasts,history):
    values=base_features(station,issue,horizon,source_issue,forecasts)
    neighbor='X66' if station=='X50' else 'X50'
    values.update({'own_'+k:v for k,v in history.get(station,issue).items()})
    values.update({'neighbor_'+k:v for k,v in history.get(neighbor,issue).items()})
    return values
