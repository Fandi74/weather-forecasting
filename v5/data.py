"""Separate hsht labels; never modify V2 observation caches or load November actuals."""
import csv
import datetime as dt
import math
from pathlib import Path
import re
import sys

from common import BASE_TRAIN_END, FREEZE, WIB, digest, locate, read_json, wib

DEVICE = '15955490-112b-11f1-8347-3d92fc978ff9'
KNOWN_CODES = {'E2', 'E3', 'E4', 'E5', 'E8', 'E11', 'E12', 'E16'}


def sht_value(row):
    # E2 flags the BME stream; hsht is the separate SHT humidity sensor.
    codes = set(re.findall(r'\bE\d+\b', row.get('error', '').upper()))
    try:
        value = float(row.get('hsht', ''))
    except (ValueError, TypeError):
        return None
    return value if not (codes - KNOWN_CODES) and math.isfinite(value) and 0 <= value <= 100 else None


def prepare_sht(rows):
    hours = {}
    for row in rows:
        stamp = int(row['timestamp_ms']) / 1000
        if stamp >= FREEZE:
            raise ValueError('Historical training source contains November benchmark actuals')
        value = sht_value(row)
        target = int(round(stamp / 3600)) * 3600
        offset = abs(stamp - target)
        if value is None or offset > 300:
            continue
        if target not in hours or offset < abs(hours[target]['observed_at'] - target):
            hours[target] = {'time': target, 'value': value, 'observed_at': stamp, 'available_at': stamp + 3600}
    return hours


def eligible(rows, observations, cutoff):
    result = []
    for row in rows:
        point = observations.get(row['time'])
        if row['station'] != 'X66' or point is None or row['issue'] is None or row['issue'] >= cutoff:
            continue
        if max(point['time'], point['observed_at'], point['available_at']) >= cutoff:
            continue
        if not all(isinstance(row.get('forecast_' + key), (int, float)) and math.isfinite(row['forecast_' + key]) for key in ('t', 'h', 'rain')):
            continue
        result.append({**row, 'observed': point['value'], 'observed_at': point['observed_at'], 'available_at': point['available_at']})
    return sorted(result, key=lambda r: (r['time'], r['issue']))


def load_inputs():
    roots = locate()
    baseline = roots['V2'][0].parents[2]
    checksums = read_json(roots['V2'][0] / 'input_checksums.json')
    for path, expected in checksums['forecast_files'].items():
        if digest(baseline / path.replace('\\', '/')) != expected:
            raise ValueError('GFS input checksum mismatch: ' + path)
    source, source_hash = next((Path(p), checksum) for p, checksum in checksums['station_files'].items() if '/X66/' in p.replace('\\', '/'))
    if digest(source) != source_hash:
        raise ValueError('Historical X66 source hash differs from original V2 audit')
    with source.open(encoding='utf-8-sig', newline='') as stream:
        raw = list(csv.DictReader(stream))
    if {r['device_id'] for r in raw} != {DEVICE}:
        raise ValueError('Historical X66 identity mismatch')
    observations = prepare_sht(raw)
    sys.path.insert(0, str(baseline / 'engine_v2'))
    import core
    manifest, annual, exact, frozen = core.load_gfs()
    del annual
    # These are out-of-time October predictions from the original pre-October
    # base fits. Their method recipes were selected in the earlier October work;
    # hence this remains development validation, not an untouched historical test.
    validation = {}
    with (roots['V3'][0] / 'validation_predictions.csv').open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            if row['station'] == 'X66' and row['variable'] == 'humidity' and row['model'] == 'engine_v2':
                key = (dt.datetime.fromisoformat(row['issue_wib']).timestamp(), dt.datetime.fromisoformat(row['target_end_wib']).timestamp())
                validation[key] = float(row['prediction'])
    train = eligible(exact, observations, BASE_TRAIN_END)
    final = eligible(exact, observations, FREEZE)
    val = [r for r in final if r['issue'] >= BASE_TRAIN_END and (r['issue'], r['time']) in validation]
    for r in val:
        r['v2_h'] = validation[r['issue'], r['time']]
    if min(len(train), len(val)) < 168:
        raise ValueError('Insufficient independent hsht training/validation support')
    support = {'X66': {'status': 'hsht_training_supported', 'source': str(source), 'source_sha256': source_hash,
        'readings': len(raw), 'hourly_hsht': len(observations), 'first_wib': wib(min(observations)), 'last_wib': wib(max(observations)),
        'pre_october_training_rows': len(train), 'october_calibration_rows': len(val), 'final_training_rows': len(final)},
        'X50': {'status': 'retain_v2', 'reason': 'Historical export has no hsht column'},
        'X51': {'status': 'retain_v2', 'reason': 'Historical export has no hsht column and lacks October support'},
        'X67': {'status': 'retain_v2', 'reason': 'No accepted independent pre-cutoff hsht history'}}
    return {'observations': observations, 'exact': [r for r in exact if r['station'] == 'X66'],
            'frozen': [r for r in frozen if r['station'] == 'X66'], 'train': train, 'final': final, 'validation': val,
            'support': support, 'source': source, 'source_hash': source_hash, 'forecast_input_hashes': checksums['forecast_files']}
