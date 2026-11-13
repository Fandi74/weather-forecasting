"""Version 0.1 inference using anonymous site keys and portable model paths."""
import functools
import json
import math
from pathlib import Path

import numpy as np
from _numeric import offset_predict, rain_predict, probability_predict

VERSION='0.1'
ROOT=Path(__file__).resolve().parent
HORIZONS=(1,6,12,24)

def load(relative):
    return json.loads((ROOT/relative).read_text(encoding='utf-8'))

@functools.lru_cache(maxsize=16)
def _lightgbm(relative):
    import lightgbm as lgb
    return lgb.Booster(model_file=str(ROOT/relative))

@functools.lru_cache(maxsize=1)
def _catboost():
    from catboost import CatBoostRegressor
    model=CatBoostRegressor()
    model.load_model(str(ROOT/'models/humidity/catboost.json'),format='json')
    return model

def _row(r):
    return {'forecast_t':r['gfs_temperature_c'],'forecast_h':r['gfs_humidity_pct'],
        'forecast_rain':r['gfs_rain_mm'],'hour':r['local_hour'],
        'day':r['forecast_day'],'raw':r['gfs_rain_mm']}

def predict_points(inputs):
    params=load('models/point_parameters.json')['sites']
    names=load('models/humidity/features.json')
    output=[]
    for r in inputs:
        if r['site'] not in params or not 1<=r['forecast_day']<=7 or not 0<=r['local_hour']<24:
            raise ValueError('Unsupported site or forecast day/hour')
        p=params[r['site']];row=_row(r)
        t=offset_predict({**row,'raw':r['gfs_temperature_c']},p['temperature'][str(r['forecast_day'])],'temperature')
        h=offset_predict({**row,'raw':r['gfs_humidity_pct']},p['humidity'][str(r['forecast_day'])],'humidity')
        output.append({'site':r['site'],'lead_hours':r['lead_hours'],'temperature_c':t,
            'humidity_pct':h,'baseline_humidity_pct':h,
            'baseline_rain_mm':rain_predict([row],p['rain'])[0],
            'baseline_rain_probability':probability_predict([row],p['rain_probability'])[0] if p['rain_probability'] else None})
    eligible=[i for i,r in enumerate(inputs) if r['site']=='Site A']
    if eligible:
        vectors=[]
        for i in eligible:
            r=inputs[i]
            values={'gfs_temperature_c':r['gfs_temperature_c'],'gfs_humidity_pct':r['gfs_humidity_pct'],
                'gfs_rain_mm':r['gfs_rain_mm'],'hour_sin':math.sin(2*math.pi*r['local_hour']/24),
                'hour_cos':math.cos(2*math.pi*r['local_hour']/24),'forecast_day':r['forecast_day']}
            values.update({k:v for k,v in r.get('humidity_history',{}).items() if k in names[6:]})
            vectors.append([np.nan if values.get(k) is None else values[k] for k in names])
        matrix=np.array(vectors,dtype=float)
        cb=_catboost().predict(matrix)
        lg=_lightgbm('models/humidity/lightgbm.txt').predict(matrix,num_threads=4)
        blend=load('models/humidity/selection.json')
        for j,i in enumerate(eligible):
            raw=inputs[i]['gfs_humidity_pct']
            components=[output[i]['baseline_humidity_pct'],min(100.,max(0.,raw+float(cb[j]))),
                min(100.,max(0.,raw+float(lg[j])))]
            output[i]['humidity_pct']=min(100.,max(0.,sum(w*v for w,v in zip(blend['weights'],components))+blend['bias_pp']))
    return output

def predict_rain_windows(inputs):
    baseline=load('models/rainfall/baselines.json')
    routing=load('models/rainfall/selection.json')
    base_names=load('models/rainfall/base_features.json')
    families={}
    for p in (ROOT/'models/rainfall').glob('*/descriptor.json'):
        d=json.loads(p.read_text(encoding='utf-8'));families[p.parent.name]=d
    output=[]
    for r in inputs:
        if r['site'] not in ['Site A','Site B'] or r['horizon'] not in HORIZONS:
            raise ValueError('Unsupported rainfall site or window')
        age=r.get('max_context_available_offset_hours')
        if age is not None and age>0:
            raise ValueError('Future station context is not permitted')
        row=[_row(x) for x in r['hourly_forecasts']]
        if len(row)!=r['horizon']:
            raise ValueError('Rain-window coverage mismatch')
        controls=baseline['sites'][r['site']]
        values={'baseline_amount':sum(rain_predict(row,controls['amount']))}
        model=baseline['window_probability']
        x=np.array([r['features'][k] for k in base_names],dtype=float)
        z=np.concatenate(([1.],(x-np.array(model['mean']))/np.array(model['std'])))
        # Preserve the reference window-logistic transform and clipping.
        logits=float(z@np.array(model['coefficients']))
        values['weather_logistic_probability']=float(1/(1+np.exp(-np.clip(logits,-35,35))))
        values['training_climatology_probability']=model['climatology'][r['site']+'_'+str(r['horizon'])]
        for family,d in families.items():
            vector=np.array([[np.nan if r['features'].get(k) is None else r['features'][k] for k in d['feature_names']]],dtype=float)
            p=(_lightgbm('models/rainfall/'+family+'/'+d['occurrence']).predict(vector,num_threads=4)[0] if 'occurrence' in d else d['constant_probability'])
            a=(_lightgbm('models/rainfall/'+family+'/'+d['positive_amount']).predict(vector,num_threads=4)[0] if 'positive_amount' in d else d['constant_positive_amount'])
            p=float(np.clip(p,0,1));a=float(max(.28,a))
            values[family+'_amount']=p*a;values[family+'_probability']=p
        selected=routing[r['site']][str(r['horizon'])]
        output.append({'site':r['site'],'horizon':r['horizon'],
            'rainfall_mm':values[selected['amount_method']+'_amount'],
            'rain_probability':values[selected['probability_method']+'_probability']})
    return output

def compose(points,rain):
    idx={(r['site'],r['lead_hours']):r for r in points}
    if len(idx)!=len(points):
        raise ValueError('Duplicate point forecasts')
    window={(r['site'],r['horizon']):r for r in rain}
    if len(window)!=len(rain):
        raise ValueError('Duplicate rainfall windows')
    result=[]
    for site in sorted({r['site'] for r in points}):
        for h in HORIZONS:
            if any((site,k) not in idx for k in range(1,h+1)):
                raise ValueError('Missing hourly coverage')
            point=idx[site,h]
            if site in ['Site A','Site B']:
                if (site,h) not in window:raise ValueError('Missing direct rainfall window')
                selected=window[site,h]
                amount=selected['rainfall_mm'];prob=selected['rain_probability']
            else:
                amount=sum(idx[site,k]['baseline_rain_mm'] for k in range(1,h+1))
                prob=point['baseline_rain_probability'] if h==1 else None
            if amount<0 or prob is not None and not 0<=prob<=1:
                raise ValueError('Invalid rain prediction')
            result.append({'site':site,'horizon':h,'temperature_c':point['temperature_c'],
                'humidity_pct':point['humidity_pct'],'rainfall_mm':amount,'rain_probability':prob})
    return result
