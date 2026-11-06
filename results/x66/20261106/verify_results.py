"""Verify the published X66 result package using only the Python standard library."""
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def close(a, b):
    return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-12)


def main():
    manifest = read_json(HERE / 'publication.json')
    for path, expected in manifest['files_sha256'].items():
        require(digest(HERE / path) == expected, 'Result hash mismatch: ' + path)
    roots = {
        'V2': (REPO / 'v2/output/engine_v2/benchmark_20261103', 'benchmark_lock.json', 'v2_'),
        'V3': (REPO / 'v3/output/benchmark_20261103_catboost', 'candidate_lock.json', 'selected_'),
        'V4': (REPO / 'v4/output/benchmark_20261103_lightgbm', 'candidate_lock.json', 'selected_')
    }
    forecasts, counts = {}, {}
    original_verification = read_json(HERE / 'verification.json')['locked_file_verification']
    for model, (root, lock_name, prefix) in roots.items():
        expected = original_verification[model]
        require(digest(root / lock_name) == expected['lock_sha256'], model + ' lock differs from evaluated snapshot')
        require(digest(root / 'frozen_predictions.json') == expected['forecast_sha256'], model + ' forecast differs from evaluated snapshot')
        lock = read_json(root / lock_name)
        for relative, checksum in lock['immutable_files'].items():
            require(digest(root / relative.replace('\\', '/')) == checksum, 'Frozen file changed: ' + model + '/' + relative)
        counts[model] = len(lock['immutable_files'])
        forecasts[model] = {r['time']: r for r in read_json(root / 'frozen_predictions.json')['predictions'] if r['station'] == 'X66'}
    aligned = read_csv(HERE / 'hourly_comparison.csv')
    metrics = read_csv(HERE / 'metrics.csv')
    observations = read_csv(HERE / 'prepared_10min_observations.csv')
    reference = [(dt.datetime.fromisoformat(r['time_wib']).timestamp(), r) for r in observations]
    for row in aligned:
        time = int(row['time'])
        observed_at, point = min(reference, key=lambda item: abs(item[0] - time))
        require(abs(observed_at - time) <= 300, 'Reference instant is outside five-minute tolerance')
        require(close(row['actual_temperature_c'], (float(point['t_c']) + float(point['tsht_c'])) / 2), 'Temperature reference mismatch')
        require(close(row['actual_humidity_pct'], point['humidity_hsht_pct']), 'Humidity reference mismatch')
        if row['actual_rain_mm'] != '':
            pieces = [point for stamp, point in reference if time - 3600 < round(stamp / 600) * 600 <= time]
            require(len(pieces) == 6, 'Rain hour lacks six readings')
            require(close(row['actual_rain_mm'], sum(float(point['rf_mm']) for point in pieces)), 'Rain reference mismatch')
        for model, (_, _, prefix) in roots.items():
            original = forecasts[model][time]
            for key, suffix in [('t', 'temperature_c'), ('h', 'humidity_pct'), ('rain', 'rain_mm')]:
                require(close(row[model + '_' + suffix], original[prefix + key]), 'Saved forecast mismatch')
            pkey = 'rain_probability' if model == 'V2' else 'selected_rain_probability'
            require(close(row[model + '_rain_probability'], original[pkey]), 'Saved probability mismatch')
    for score in metrics:
        suffix = {'temperature': 'temperature_c', 'humidity': 'humidity_pct', 'rain': 'rain_mm'}[score['variable']]
        valid = [r for r in aligned if r['actual_' + suffix] != '']
        errors = [float(r[score['model'] + '_' + suffix]) - float(r['actual_' + suffix]) for r in valid]
        require(len(valid) == int(score['n']), 'Metric coverage mismatch')
        actual = {'mae': statistics.mean(abs(x) for x in errors), 'rmse': math.sqrt(statistics.mean(x*x for x in errors)), 'bias': statistics.mean(errors)}
        require(all(close(actual[k], score[k]) for k in actual), 'Metric calculation mismatch')
    for score in read_csv(HERE / 'rain_probability_metrics.csv'):
        valid = [r for r in aligned if r['actual_rain_mm'] != '']
        brier = statistics.mean((float(r[score['model'] + '_rain_probability']) - int(float(r['actual_rain_mm']) >= .28 - 1e-9)) ** 2 for r in valid)
        require(close(brier, score['brier_score']), 'Brier score mismatch')
    print(json.dumps({'verified': True, 'result_files': len(manifest['files_sha256']), 'frozen_files': counts,
        'hourly_temperature_humidity_pairs': len(aligned), 'complete_rain_hours': sum(r['actual_rain_mm'] != '' for r in aligned),
        'accuracy_metrics': len(metrics), 'brier_scores': 3, 'models_refitted': False}, indent=2))


if __name__ == '__main__':
    main()
