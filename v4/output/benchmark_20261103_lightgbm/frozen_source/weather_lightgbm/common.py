import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

VERSION = 'engine_v4_lightgbm.1'
VERSION_DIR = Path(__file__).resolve().parents[1]
WORKSPACE = VERSION_DIR.parents[1]
WIB = dt.timezone(dt.timedelta(hours=7))
UTC = dt.timezone.utc
FREEZE = dt.datetime(2026, 11, 3, tzinfo=WIB).timestamp()
VALIDATION_START = dt.datetime(2026, 10, 1, tzinfo=WIB).timestamp()
HISTORY_START = dt.datetime(2025, 11, 3, tzinfo=WIB).timestamp()
EVENT_MM = 0.28
VARIANTS = ('lightgbm_base_full', 'lightgbm_base_exact', 'lightgbm_history_exact')
VARIABLES = {'temperature': 't', 'humidity': 'h', 'rain': 'rain'}
DEFAULT_OUTPUT = VERSION_DIR / 'output/benchmark_20261103_lightgbm'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def wib(timestamp):
    return dt.datetime.fromtimestamp(timestamp, WIB).isoformat()


def now():
    return dt.datetime.now(UTC).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def verify_files(root, files):
    for name, expected in files.items():
        path = Path(root) / Path(name.replace('\\', '/'))
        if digest(path) != expected:
            raise ValueError('Immutable file mismatch: ' + str(path))


def check_unlocked(output):
    if (Path(output) / 'candidate_lock.json').exists():
        raise ValueError('Candidate is locked; use score or a new output/version.')


def row_signature(rows):
    keys = sorted((r['station'], r['time'], r['issue'] if r['issue'] is not None else -1, r['day']) for r in rows)
    return hashlib.sha256(json.dumps(keys, separators=(',', ':')).encode()).hexdigest()
