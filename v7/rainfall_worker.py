"""Run the unchanged V6 inference primitives in an isolated Python process."""
import argparse
import csv
import json
from pathlib import Path
import sys

V7 = Path(__file__).resolve().parent
ROOT = V7.parent
sys.path.insert(0, str(ROOT/'v6'))
from common import FREEZE, HORIZONS, locate, read_json, save_json
from clarification_review import TimingHistory, keep_raw_adc
from data import SOURCES, read_sources
from features import all_features
from experiment import apply_selection, predict_all


def core_module():
    sys.path.insert(0, str(locate()['V2'][0].parents[2]/'engine_v2'))
    import core
    return core


def snapshot():
    strict, quality = read_sources()
    raw = {}
    for station, path in SOURCES.items():
        with path.open(encoding='utf-8-sig', newline='') as stream:
            raw[station] = {int(r['timestamp_ms'])/1000: r for r in csv.DictReader(stream)}
    corrected = keep_raw_adc(strict, raw)
    history = TimingHistory(corrected, 3600)
    gfs = read_json(locate()['V2'][0]/'frozen_predictions.json')
    index = {(r['station'], r['time']): r for r in gfs['predictions']}
    rows = []
    for station in ['X50','X66']:
        for horizon in HORIZONS:
            forecasts = [index[station, FREEZE+k*3600] for k in range(1, horizon+1)]
            rows.append({'station': station, 'issue': FREEZE, 'horizon': horizon,
                'end': FREEZE+horizon*3600, 'actual': None, 'label_available_at': None,
                'label_source': 'not_used_for_composition', 'stage': 'merged_retrospective_snapshot',
                # Preserve V6's archived forecast-snapshot issue convention.
                'gfs_source_issue': FREEZE, 'hourly_forecasts': forecasts,
                'features': all_features(station, FREEZE, horizon, FREEZE, forecasts, history)})
    if any(r['max_assumed_availability_used'] is not None and r['max_assumed_availability_used'] > r['issue'] for r in history.audit):
        raise ValueError('Future station context')
    return {'rows': rows, 'feature_availability': history.audit,
        'source_quality': quality, 'assumed_receipt_delay_seconds': 3600,
        'gfs_snapshot_issue': FREEZE, 'gfs_run_initialized_utc': gfs['gfs_run_initialized_utc'],
        'source_note': 'Snapshot-issue feature convention is unchanged from V6; model-run initialization is recorded separately.'}


def predict(snapshot_data):
    model_root = V7/'models/rainfall'
    descriptors = {p.parent.name: read_json(p) for p in model_root.glob('*/descriptor.json')}
    baseline = read_json(model_root/'baselines.json')
    result = predict_all(snapshot_data['rows'], descriptors, model_root, baseline, core_module())
    selection = read_json(V7/'models/rainfall_selection.json')
    apply_selection(result, selection)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['snapshot','predict'])
    parser.add_argument('output', type=Path)
    parser.add_argument('--input', type=Path)
    args = parser.parse_args()
    value = snapshot() if args.command == 'snapshot' else predict(read_json(args.input))
    save_json(args.output, value)
