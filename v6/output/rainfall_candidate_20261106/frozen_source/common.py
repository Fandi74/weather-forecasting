"""V6 rainfall research constants; all earlier versions remain read-only."""
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import statistics

VERSION_DIR = Path(__file__).resolve().parent
ROOT = VERSION_DIR.parent
WIB = dt.timezone(dt.timedelta(hours=7))
TRAIN_END = dt.datetime(2026, 10, 1, tzinfo=WIB).timestamp()
VALIDATION_END = dt.datetime(2026, 10, 20, tzinfo=WIB).timestamp()
FREEZE = dt.datetime(2026, 11, 3, tzinfo=WIB).timestamp()
HORIZONS = (1, 6, 12, 24)
TIP_MM = .28
DEFAULT_OUTPUT = VERSION_DIR / 'output/rainfall_candidate_20261106'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def write_csv(path, rows):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader(); writer.writerows(rows)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wib(time):
    return dt.datetime.fromtimestamp(time, WIB).isoformat()


def locate():
    baseline = ROOT if (ROOT / 'engine_v2/core.py').exists() else ROOT / 'v2'
    v3 = next(p for p in [ROOT / 'v3', ROOT / 'versions/v2_catboost'] if (p / 'output/benchmark_20261103_catboost/candidate_lock.json').exists())
    v4 = next(p for p in [ROOT / 'v4', ROOT / 'version/v4'] if (p / 'output/benchmark_20261103_lightgbm/candidate_lock.json').exists())
    return {'V2': (baseline / 'output/engine_v2/benchmark_20261103', 'benchmark_lock.json'),
        'V3': (v3 / 'output/benchmark_20261103_catboost', 'candidate_lock.json'),
        'V4': (v4 / 'output/benchmark_20261103_lightgbm', 'candidate_lock.json'),
        'V5': (ROOT / 'v5/output/benchmark_20261103_humidity_v5', 'candidate_lock.json')}


def verify_references():
    checks = {}
    for version, (root, name) in locate().items():
        lock = read_json(root / name)
        for relative, expected in lock['immutable_files'].items():
            if digest(root / relative.replace('\\', '/')) != expected:
                raise ValueError('Frozen reference changed: ' + version + '/' + relative)
        checks[version] = {'files': len(lock['immutable_files']), 'lock_sha256': digest(root / name),
            'forecast_sha256': digest(root / 'frozen_predictions.json')}
    return checks


def metrics(actual, predicted, probabilities=None):
    if not actual:
        return {'n': 0, 'mae': None, 'rmse': None, 'bias': None, 'brier': None}
    error = [p-y for y,p in zip(actual,predicted)]
    wet = [y >= TIP_MM-1e-9 for y in actual]
    decisions = [p >= TIP_MM-1e-9 for p in predicted]
    hits = sum(a and b for a,b in zip(wet,decisions))
    misses = sum(a and not b for a,b in zip(wet,decisions))
    false = sum(not a and b for a,b in zip(wet,decisions))
    return {'n': len(actual), 'wet_cases': sum(wet), 'mae': statistics.mean(abs(e) for e in error),
        'rmse': math.sqrt(statistics.mean(e*e for e in error)), 'bias': statistics.mean(error),
        'wet_mae': statistics.mean(abs(e) for e,w in zip(error,wet) if w) if any(wet) else None,
        'brier': statistics.mean((p-y)**2 for p,y in zip(probabilities,wet)) if probabilities is not None else None,
        'hits_amount_threshold': hits, 'misses_amount_threshold': misses, 'false_alarms_amount_threshold': false,
        'precision_amount_threshold': hits/(hits+false) if hits+false else None,
        'recall_amount_threshold': hits/(hits+misses) if hits+misses else None}


def no_overwrite(output):
    output=Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new empty experiment directory; never overwrite a sealed candidate.')
