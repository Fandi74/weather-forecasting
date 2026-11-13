"""Replay the public v0.1 demonstration without private archives or raw data."""
import argparse
import csv
import json
from pathlib import Path
import math
from engine import load,predict_points,predict_rain_windows,compose

ROOT=Path(__file__).resolve().parent

def verify_replay():
    points=predict_points(load('data/point_inputs.json'))
    rain=predict_rain_windows(load('data/rain_inputs.json'))
    windows=compose(points,rain)
    with (ROOT/'data/point_forecasts.csv').open(encoding='utf-8',newline='') as f:
        expected=list(csv.DictReader(f))
    with (ROOT/'data/window_forecasts.csv').open(encoding='utf-8',newline='') as f:
        expected_windows=list(csv.DictReader(f))
    idx={(r['site'],int(r['lead_hours'])):r for r in expected}
    for r in points:
        old=idx[r['site'],r['lead_hours']]
        for key in ['temperature_c','humidity_pct','baseline_rain_mm','baseline_rain_probability']:
            value=old[key]
            if value=='':
                if r[key] is not None:raise ValueError('Unsupported probability changed')
            elif not math.isclose(float(value),r[key],rel_tol=1e-11,abs_tol=1e-11):
                raise ValueError('Reference point forecast differs: '+key)
    idx={(r['site'],int(r['horizon'])):r for r in expected_windows}
    for r in windows:
        old=idx[r['site'],r['horizon']]
        for key in ['temperature_c','humidity_pct','rainfall_mm','rain_probability']:
            if old[key]=='':
                if r[key] is not None:raise ValueError('Fallback probability changed')
            elif not math.isclose(float(old[key]),r[key],rel_tol=1e-11,abs_tol=1e-11):
                raise ValueError('Reference window forecast differs: '+key)
    return {'version':'0.1','point_forecasts_reproduced':len(points),
        'rain_windows_reproduced':len(rain),'combined_windows_reproduced':len(windows)}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['replay','verify'])
    args=parser.parse_args()
    if args.command=='verify':
        from verify_package import verify
        print(json.dumps(verify(),indent=2))
    else:
        print(json.dumps(verify_replay(),indent=2))
