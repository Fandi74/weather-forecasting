"""Chronological window forecasts against independent, complete gauge labels."""
import bisect
import collections
import math
import sys

from common import FREEZE,HORIZONS,TRAIN_END,VALIDATION_END,digest,locate,read_json
from data import window_label
from features import History,all_features


def load_gfs():
    baseline=locate()['V2'][0].parents[2]
    checks=read_json(locate()['V2'][0]/'input_checksums.json')
    for path,expected in checks['forecast_files'].items():
        if digest(baseline/path.replace('\\','/'))!=expected:raise ValueError('Archived GFS changed: '+path)
    sys.path.insert(0,str(baseline/'engine_v2'))
    import core
    manifest,annual,exact,frozen=core.load_gfs();del annual
    runs=collections.defaultdict(lambda:collections.defaultdict(dict))
    for r in exact+frozen:
        if r['station'] in ['X50','X66']:runs[r['issue']][r['station']][r['time']]=r
    return core,runs,checks['forecast_files']


def partition(issue,available):
    if issue<TRAIN_END and available<TRAIN_END:return 'train'
    if TRAIN_END<=issue<VALIDATION_END and available<VALIDATION_END:return 'validation'
    if VALIDATION_END<=issue<FREEZE and available<FREEZE:return 'test'
    if issue>=FREEZE:return 'november_diagnostic'
    return 'purged_boundary'


def build_samples(data):
    core,runs,hashes=load_gfs()
    run_times=sorted(runs);history=History(data)
    start=math.ceil(min(d['records'][0]['time'] for d in data.values())/3600)*3600
    end=math.floor(max(d['records'][-1]['time'] for d in data.values())/3600)*3600
    samples=[];hourly={};coverage=collections.Counter()
    for issue in range(start,end,3600):
        j=bisect.bisect_right(run_times,issue)-1
        if j<0:continue
        source_issue=run_times[j]
        for station,d in data.items():
            lookup=runs[source_issue][station]
            for horizon in HORIZONS:
                forecasts=[lookup.get(issue+k*3600) for k in range(1,horizon+1)]
                if not all(r and all(isinstance(r.get('forecast_'+key),(int,float)) and math.isfinite(r['forecast_'+key]) for key in ['t','h','rain']) for r in forecasts):
                    coverage['missing_gfs_window']+=1;continue
                label=window_label(d,issue,horizon)
                if label is None:
                    coverage[station+'_missing_rain_window']+=1;continue
                features=all_features(station,issue,horizon,source_issue,forecasts,history)
                row={'station':station,'issue':issue,'horizon':horizon,'end':label['end'],'label_available_at':label['available_at'],
                    'actual':label['amount'],'label_source':label['source'],'gfs_source_issue':source_issue,'stage':partition(issue,label['available_at']),
                    'features':features,'hourly_forecasts':forecasts}
                samples.append(row)
                for forecast in forecasts:
                    point=window_label(d,forecast['time']-3600,1)
                    if point is None:continue
                    key=(station,issue,forecast['time'])
                    hourly[key]={**forecast,'issue':issue,'raw':forecast['forecast_rain'],'observed':point['amount'],
                        'label_available_at':point['available_at']}
    return {'samples':samples,'hourly':list(hourly.values()),'history':history,'core':core,'gfs_checksums':hashes,'coverage':dict(coverage)}
