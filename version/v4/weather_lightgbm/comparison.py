"""Read frozen V3 results only as a comparison, never as LightGBM inputs."""
import csv
from pathlib import Path

from .common import read_json, verify_files, wib


def read_v3(workspace):
    workspace = Path(workspace)
    roots = (workspace / 'versions/v2_catboost', workspace / 'version/v3',
             workspace / '.repo-preparation/weather-forecasting/version/v3')
    for root in roots:
        output = root / 'output/benchmark_20261103_catboost'
        if (output / 'candidate_lock.json').exists():
            break
    else:
        raise FileNotFoundError('Frozen V3 CatBoost experiment not found')
    lock = read_json(output / 'candidate_lock.json')
    verify_files(output, lock['immutable_files'])
    with (output / 'validation_predictions.csv').open(encoding='utf-8-sig') as stream:
        validation = list(csv.DictReader(stream))
    index = {(r['station'], r['variable'], r['model'], r['issue_wib'], r['target_end_wib']): r for r in validation}
    package = read_json(output / 'frozen_predictions.json')
    return {'output': output, 'lock': lock, 'selection': read_json(output / 'selection.json'),
            'validation_index': index, 'audit': read_json(output / 'training_audit.json'),
            'frozen': {(r['station'], r['time']): r for r in package['predictions']},
            'features': read_json(output / 'frozen_features.json')}


def validation_values(v3, station, variable, rows):
    selection = v3['selection'][station][variable]['method']
    probability = variable == 'rain_probability'
    if not rows:
        return []
    if selection == 'unavailable':
        return [None] * len(rows)
    if selection == 'training_climatology':
        raise ValueError('A climatology-selected V3 reference requires its explicit training probability')
    variable_key = 'rain' if probability else variable
    result = []
    for row in rows:
        key = (station, variable_key, selection, wib(row['issue']), wib(row['time']))
        reference = v3['validation_index'].get(key)
        if reference is None:
            raise ValueError('V3 validation case missing: ' + str(key))
        if abs(float(reference['actual']) - row['observed']) > 1e-9:
            raise ValueError('V3/V4 validation observations differ')
        value = reference['rain_probability' if probability else 'prediction']
        result.append(float(value) if value != '' else None)
    return result


def compare_training_audits(v3_audit, v4_audit):
    for row in v4_audit:
        name = row['variant'].replace('lightgbm_', 'catboost_')
        reference = next(r for r in v3_audit if r['station'] == row['station'] and r['variable'] == row['variable']
                         and r['variant'] == name and r['stage'] == row['stage'])
        for key in ('row_signature', 'training_rows', 'unique_target_hours', 'latest_target_wib', 'latest_observation_available_wib'):
            if row[key] != reference[key]:
                raise ValueError('V3/V4 training data differs: ' + str((row['station'], row['variable'], row['stage'], key)))
    return len(v4_audit)
