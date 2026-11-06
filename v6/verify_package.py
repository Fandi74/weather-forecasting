"""Verify published V6 artifacts offline using Python's standard library."""
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import statistics

V6 = Path(__file__).resolve().parent
REPO = V6.parent
OUT = V6 / 'output'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(a, b):
    return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-12)


def check_scores(folder, prediction_file, score_file):
    predictions = rows(folder / prediction_file)
    scores = rows(folder / score_file)
    for score in scores:
        sample = [r for r in predictions if r['station'] == score['station'] and r['horizon'] == score['horizon']]
        require(len(sample) == int(score['n']), 'Metric sample count differs')
        actual = [float(r['actual']) for r in sample]
        model = score['model']
        if score['amount_available'] == 'True':
            errors = [float(r[model + '_amount']) - y for r, y in zip(sample, actual)]
            values = {'mae': statistics.mean(abs(e) for e in errors),
                'rmse': math.sqrt(statistics.mean(e*e for e in errors)), 'bias': statistics.mean(errors)}
            require(all(close(v, score[k]) for k, v in values.items()), 'Amount metrics differ')
        if score['probability_available'] == 'True':
            probability = [float(r[model + '_probability']) for r in sample]
            require(all(0 <= p <= 1 for p in probability), 'Probability outside [0,1]')
            brier = statistics.mean((p - (y >= .28 - 1e-9))**2 for p, y in zip(probability, actual))
            require(close(brier, score['brier']), 'Brier score differs')
    return predictions, len(scores)


def main():
    publication = load(V6 / 'publication.json')
    for name, expected in publication['files_sha256'].items():
        require(digest(V6 / name) == expected, 'Publication hash mismatch: ' + name)
    roots = {
        'V2': (REPO / 'v2/output/engine_v2/benchmark_20261103', 'benchmark_lock.json'),
        'V3': (REPO / 'v3/output/benchmark_20261103_catboost', 'candidate_lock.json'),
        'V4': (REPO / 'v4/output/benchmark_20261103_lightgbm', 'candidate_lock.json'),
        'V5': (REPO / 'v5/output/benchmark_20261103_humidity_v5', 'candidate_lock.json'),
        'V6_initial': (OUT / 'rainfall_candidate_20261106', 'candidate_lock.json'),
        'V6_weekly': (OUT / 'rolling_refresh_20261106', 'rolling_lock.json'),
        'V6_E11': (OUT / 'e11_corrected_20261106', 'clarification_lock.json')}
    counts = {}
    for version, (folder, name) in roots.items():
        lock = load(folder / name)
        for path, expected in lock['immutable_files'].items():
            require(digest(folder / path.replace('\\', '/')) == expected, 'Frozen file differs: ' + version + '/' + path)
        counts[version] = len(lock['immutable_files'])
    refs = load(OUT / 'rainfall_candidate_20261106/reference_locks.json')
    for version, ref in refs.items():
        folder, name = roots[version]
        require(digest(folder / name) == ref['lock_sha256'], 'Reference lock differs: ' + version)
        require(digest(folder / 'frozen_predictions.json') == ref['forecast_sha256'], 'Reference forecast differs: ' + version)
    inherited = load(OUT / 'rainfall_candidate_20261106/temperature_humidity_passthrough.json')
    v5 = load(roots['V5'][0] / 'frozen_predictions.json')['predictions']
    require(len(inherited) == len(v5) == 672, 'Temperature/humidity coverage differs')
    for a, b in zip(inherited, v5):
        require(a['station'] == b['station'] and a['time'] == b['time'], 'Passthrough alignment differs')
        for new, old in [('temperature_c', 'selected_t'), ('humidity_pct', 'selected_h')]:
            require(float(a[new]).hex() == float(b[old]).hex(), 'Protected component differs')
    experiments = [
        ('rainfall_candidate_20261106', 'test_predictions.csv', 'test_scores.csv'),
        ('rolling_refresh_20261106', 'predictions.csv', 'scores.csv'),
        ('e11_corrected_20261106/raw_srm_1h', 'predictions.csv', 'scores.csv'),
        ('e11_corrected_20261106/raw_srm_timestamp', 'predictions.csv', 'scores.csv')]
    metric_rows = 0
    cases = None
    for folder, predictions, scores in experiments:
        sample, count = check_scores(OUT / folder, predictions, scores)
        current = {(r['station'], r['issue'], r['horizon']): (float(r['actual']), r['label_available_at']) for r in sample}
        require(len(current) == len(sample) == 2314, 'Case coverage differs')
        if cases is not None:
            require(cases == current, 'Target cases differ between experiments')
        cases = current
        metric_rows += count
    availability = load(OUT / 'e11_corrected_20261106/feature_availability.json')
    for sample in availability.values():
        for r in sample:
            if r['max_assumed_availability_used'] is not None:
                require(r['max_assumed_availability_used'] <= r['issue'] and r['max_csv_timestamp_used'] <= r['issue'], 'Future timestamp used')
    for r in load(OUT / 'e11_corrected_20261106/training_audit.json'):
        require(dt.datetime.fromisoformat(r['max_training_label_available_wib']) < dt.datetime.fromisoformat(r['fit_cutoff_exclusive_wib']), 'Training label crosses cutoff')
    print(json.dumps({'verified': True, 'published_files': len(publication['files_sha256']),
        'locked_files': counts, 'unchanged_temperature_humidity_rows': len(inherited),
        'same_rainfall_cases_per_experiment': len(cases), 'metric_rows_reproduced': metric_rows,
        'models_refitted': False}, indent=2))


if __name__ == '__main__':
    main()
