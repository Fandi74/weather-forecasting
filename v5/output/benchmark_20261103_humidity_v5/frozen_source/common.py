"""V5 humidity experiment constants and immutable-reference checks."""
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import statistics

VERSION_DIR = Path(__file__).resolve().parent
WORKSPACE = VERSION_DIR.parent
WIB = dt.timezone(dt.timedelta(hours=7))
FREEZE = dt.datetime(2026, 11, 3, tzinfo=WIB).timestamp()
BASE_TRAIN_END = dt.datetime(2026, 10, 1, tzinfo=WIB).timestamp()
DEFAULT_OUTPUT = VERSION_DIR / 'output/benchmark_20261103_humidity_v5'


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wib(time):
    return dt.datetime.fromtimestamp(time, WIB).isoformat()


def locate():
    baseline = WORKSPACE if (WORKSPACE / 'engine_v2/core.py').exists() else WORKSPACE / 'v2'
    v3 = next(p for p in [WORKSPACE / 'v3', WORKSPACE / 'versions/v2_catboost'] if (p / 'output/benchmark_20261103_catboost/candidate_lock.json').exists())
    v4 = next(p for p in [WORKSPACE / 'v4', WORKSPACE / 'version/v4'] if (p / 'output/benchmark_20261103_lightgbm/candidate_lock.json').exists())
    return {'V2': (baseline / 'output/engine_v2/benchmark_20261103', 'benchmark_lock.json'),
            'V3': (v3 / 'output/benchmark_20261103_catboost', 'candidate_lock.json'),
            'V4': (v4 / 'output/benchmark_20261103_lightgbm', 'candidate_lock.json')}


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


def metrics(actual, predicted):
    if not actual:
        return {'n': 0, 'mae': None, 'rmse': None, 'bias': None, 'correlation': None}
    errors = [p - y for y, p in zip(actual, predicted)]
    return {'n': len(actual), 'mae': statistics.mean(abs(v) for v in errors),
            'rmse': math.sqrt(statistics.mean(v*v for v in errors)), 'bias': statistics.mean(errors),
            'correlation': statistics.correlation(actual, predicted) if len(actual) > 1 and statistics.pstdev(actual) and statistics.pstdev(predicted) else None}


def no_overwrite(output):
    output = Path(output)
    if (output / 'candidate_lock.json').exists() or (output.exists() and any(output.iterdir())):
        raise ValueError('Use a new empty output folder; frozen experiments cannot be overwritten.')
