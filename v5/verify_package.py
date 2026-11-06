"""Verify the published V5 models, frozen references and reported results offline."""
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

V5 = Path(__file__).resolve().parent
REPO = V5.parent
BENCHMARK = V5 / 'output/benchmark_20261103_humidity_v5'
EVALUATION = V5 / 'output/evaluation_20261106'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def csv_rows(path):
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
    publication = read_json(V5 / 'publication.json')
    for path, expected in publication['files_sha256'].items():
        require(digest(V5 / path) == expected, 'Published file hash mismatch: ' + path)
    refs = read_json(BENCHMARK / 'reference_locks.json')
    roots = {
        'V2': (REPO / 'v2/output/engine_v2/benchmark_20261103', 'benchmark_lock.json'),
        'V3': (REPO / 'v3/output/benchmark_20261103_catboost', 'candidate_lock.json'),
        'V4': (REPO / 'v4/output/benchmark_20261103_lightgbm', 'candidate_lock.json'),
        'V5': (BENCHMARK, 'candidate_lock.json')}
    counts = {}
    for name, (root, lock_name) in roots.items():
        lock = read_json(root / lock_name)
        for path, expected in lock['immutable_files'].items():
            require(digest(root / path.replace('\\', '/')) == expected, 'Frozen file changed: ' + name + '/' + path)
        counts[name] = len(lock['immutable_files'])
        if name != 'V5':
            require(digest(root / lock_name) == refs[name]['lock_sha256'], name + ' reference lock differs')
            require(digest(root / 'frozen_predictions.json') == refs[name]['forecast_sha256'], name + ' reference forecast differs')
    old = {(r['station'], r['time']): r for r in read_json(roots['V2'][0] / 'frozen_predictions.json')['predictions']}
    package = read_json(BENCHMARK / 'frozen_predictions.json')
    forecasts = package['predictions']
    require(len(forecasts) == len(old) == 672, 'Forecast coverage mismatch')
    selection = read_json(BENCHMARK / 'selection.json')['model']
    for row in forecasts:
        original = old[row['station'], row['time']]
        for new_key, old_key in [('selected_t','v2_t'), ('selected_rain','v2_rain'), ('selected_rain_probability','rain_probability')]:
            a, b = row[new_key], original[old_key]
            require((a is None and b is None) or float(a).hex() == float(b).hex(), 'V5 changed a protected V2 component')
        if row['station'] == 'X66':
            expected = min(100., max(0., sum(w*row[k] for w,k in zip(selection['weights'], selection['components'])) + selection['bias_pp']))
            require(close(row['selected_h'], expected), 'V5 humidity combination mismatch')
        else:
            require(close(row['selected_h'], original['v2_h']), 'Unsupported station humidity changed')
    cases = csv_rows(EVALUATION / 'hourly_comparison.csv')
    metrics = csv_rows(EVALUATION / 'metrics.csv')
    index = {r['time']: r for r in forecasts if r['station'] == 'X66'}
    for row in cases:
        saved = index[int(row['time'])]
        for model, key in [('V2','v2_h'), ('V3','v3_h'), ('V4','v4_h'), ('V5','selected_h'),
                           ('CatBoost_hsht','catboost_hsht_h'), ('LightGBM_hsht','lightgbm_hsht_h')]:
            require(close(row[model + '_h'], saved[key]), 'Evaluated forecast differs from sealed output')
    for score in metrics:
        errors = [float(r[score['model'] + '_h']) - float(r['actual_hsht']) for r in cases]
        values = {'mae': statistics.mean(abs(e) for e in errors), 'rmse': math.sqrt(statistics.mean(e*e for e in errors)), 'bias': statistics.mean(errors)}
        require(len(errors) == int(score['n']) and all(close(v, score[k]) for k,v in values.items()), 'Evaluation metric mismatch')
    cv = csv_rows(BENCHMARK / 'validation_predictions.csv')
    chosen = read_json(BENCHMARK / 'selection.json')
    for family, field in [('v2','baseline_mae'), (chosen['best_development_family'],'best_mae')]:
        sample = [r for r in cv if r['family'] == family]
        require(close(statistics.mean(abs(float(r['prediction']) - float(r['actual_hsht'])) for r in sample), chosen[field]), 'October validation metric mismatch')
    print(json.dumps({'verified': True, 'published_v5_files': len(publication['files_sha256']), 'locked_files': counts,
        'protected_v2_forecast_rows': len(forecasts), 'humidity_metric_rows': len(metrics), 'matched_humidity_hours': len(cases),
        'models_refitted': False}, indent=2))


if __name__ == '__main__':
    main()
