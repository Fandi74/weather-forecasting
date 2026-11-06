import collections
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil

from .common import (DEFAULT_OUTPUT, EVENT_MM, FREEZE, VALIDATION_START, VARIABLES,
                     VARIANTS, VERSION, VERSION_DIR, check_unlocked, digest, finite,
                     now, read_json, row_signature, save_json, verify_files, wib, write_csv)
from .data import (baseline_context, load_inputs, paired_rows,
                   reconstruct_v2_probability, reconstruct_v2_validation)
from .features import HistoryBuilder, feature_values
from .learner import PARAMETERS, fit, predict

MODEL_NAMES = ('raw_gfs', 'engine_v2') + VARIANTS


def probability_metrics(rows, values):
    paired = [(r['observed'] >= EVENT_MM - 1e-9, p) for r, p in zip(rows, values) if p is not None]
    if not paired:
        return {'n': 0, 'brier': None, 'logloss': None}
    import math
    return {'n': len(paired), 'brier': sum((p - y) ** 2 for y, p in paired) / len(paired),
            'logloss': -sum(y * math.log(max(1e-12, p)) + (1 - y) * math.log(max(1e-12, 1 - p))
                            for y, p in paired) / len(paired)}


def train_audit(station, variable, variant, stage, rows, cutoff):
    for row in rows:
        if max(row['time'], row['observation_measured_at'], row['observation_available_at']) >= cutoff:
            raise ValueError('Training label/availability crosses cutoff')
        if variant != 'catboost_base_full' and (row['issue'] is None or row['issue'] >= cutoff):
            raise ValueError('Exact training row has no eligible issue')
    return {'station': station, 'variable': variable, 'variant': variant, 'stage': stage,
            'training_rows': len(rows), 'unique_target_hours': len({r['time'] for r in rows}),
            'exact_rows': sum(r['issue'] is not None for r in rows),
            'proxy_rows': sum(r['issue'] is None for r in rows),
            'row_signature': row_signature(rows), 'cutoff_exclusive_wib': wib(cutoff),
            'latest_target_wib': wib(max(r['time'] for r in rows)) if rows else None,
            'latest_observation_available_wib': wib(max(r['observation_available_at'] for r in rows)) if rows else None}


def validation_scopes(rows):
    return {'all_168h': list(range(len(rows))),
            'first_24h': [i for i, r in enumerate(rows) if r['time'] - r['issue'] <= 24 * 3600],
            **{f'day_{day}': [i for i, r in enumerate(rows) if r['day'] == day] for day in range(1, 8)}}


def build(workspace, output=DEFAULT_OUTPUT):
    output = Path(output).resolve()
    check_unlocked(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new empty output folder; never overwrite experiment artifacts.')
    context = load_inputs(workspace)
    print('Original V2 lock, input hashes and frozen predictions verified.', flush=True)
    output.mkdir(parents=True, exist_ok=True)
    protocol = read_json(VERSION_DIR / 'protocol.json')
    assert all(PARAMETERS[k] == v for k, v in protocol['hyperparameters'].items())
    save_json(output / 'protocol.json', protocol)
    save_json(output / 'baseline_reference.json', {
        'baseline_root': str(context['root']),
        'baseline_model_sha256': digest(context['output'] / 'models.json'),
        'baseline_lock_sha256': digest(context['output'] / 'benchmark_lock.json'),
        'immutable_files': context['lock']['immutable_files']})
    save_json(output / 'input_checksums.json', {'root': str(context['root']), 'files': context['input_checksums']})
    save_json(output / 'environment.json', {'python': platform.python_version(), 'platform': platform.platform(),
              'packages': {name: importlib.metadata.version(name) for name in ('catboost', 'numpy', 'pandas', 'scipy', 'matplotlib')}})
    history = HistoryBuilder(context['observations'], context['exact'])
    core = context['core']
    validation, comparisons, audit, selections, catalog = [], [], [], {}, {}
    per_station = {}

    for station in context['manifest']['stations']:
        per_station[station], selections[station], catalog[station] = {}, {}, {}
        for variable in VARIABLES:
            train_full = paired_rows(context, station, variable, VALIDATION_START)
            train_exact = paired_rows(context, station, variable, VALIDATION_START, exact_only=True)
            val = paired_rows(context, station, variable, FREEZE, validation=True)
            supported = len(train_full) >= 168 and len(train_exact) >= 168 and len(val) >= 48
            estimates = {'raw_gfs': [r['raw'] for r in val]}
            probabilities = {'raw_gfs': [None] * len(val)}
            estimates['engine_v2'] = reconstruct_v2_validation(context, station, variable, train_full, val) if supported else estimates['raw_gfs']
            if variable == 'rain':
                probabilities['engine_v2'] = reconstruct_v2_probability(context, station, train_full, val) if supported else [None] * len(val)
                frequency = sum(r['observed'] >= EVENT_MM - 1e-9 for r in train_full) / len(train_full) if train_full else None
                probabilities['training_climatology'] = [frequency] * len(val)

            for variant in VARIANTS:
                train = train_full if variant == 'catboost_base_full' else train_exact
                audit.append(train_audit(station, variable, variant, 'validation', train, VALIDATION_START))
                if supported:
                    print(f'Validation fit: {station} {variable} {variant}, {len(train)} rows / {len(val)} validation', flush=True)
                    descriptor = fit(train, variant, variable, history,
                                     output / 'models/validation' / station / variant / variable, output)
                    estimates[variant], probabilities[variant] = predict(descriptor, val, history, output)
                else:
                    estimates[variant] = estimates['raw_gfs']
                    probabilities[variant] = [None] * len(val)

            for scope, indexes in validation_scopes(val).items():
                sample = [val[i] for i in indexes]
                for name, values in estimates.items():
                    scores = core.metrics(sample, [values[i] for i in indexes], rain=variable == 'rain')
                    validation.append({'station': station, 'variable': variable, 'scope': scope, 'model': name,
                                       'supported': supported, **scores})
                if variable == 'rain':
                    for name, values in probabilities.items():
                        scores = probability_metrics(sample, [values[i] for i in indexes])
                        validation.append({'station': station, 'variable': 'rain_probability', 'scope': scope,
                                           'model': name, 'supported': supported, **scores})

            for i, row in enumerate(val):
                for name, values in estimates.items():
                    comparisons.append({'station': station, 'variable': variable, 'issue_wib': wib(row['issue']),
                        'target_end_wib': wib(row['time']), 'forecast_day': row['day'], 'model': name,
                        'actual': row['observed'], 'prediction': values[i],
                        'rain_probability': probabilities.get(name, [None] * len(val))[i] if variable == 'rain' else None})
            per_station[station][variable] = {'supported': supported, 'validation_rows': len(val)}
            for component in ((variable, 'mae' if variable != 'rain' else 'rmse'),) + ((('rain_probability', 'brier'),) if variable == 'rain' else ()):
                name, metric = component
                options = [s for s in validation if s['station'] == station and s['variable'] == name
                           and s['scope'] == 'all_168h' and s.get(metric) is not None and s['n'] >= 48]
                priority = {m: i for i, m in enumerate(('engine_v2', 'raw_gfs') + VARIANTS + ('training_climatology',))}
                winner = min(options, key=lambda s: (s[metric], priority[s['model']])) if supported and options else None
                selections[station][name] = {'method': winner['model'] if winner else ('raw_gfs' if name != 'rain_probability' else 'unavailable'),
                    'metric': metric, 'validation_score': winner[metric] if winner else None,
                    'reason': 'October selection; blind benchmark pending' if winner else 'No eligible October validation'}

            for variant in VARIANTS:
                final = paired_rows(context, station, variable, FREEZE, exact_only=variant != 'catboost_base_full')
                audit.append(train_audit(station, variable, variant, 'final', final, FREEZE))
                if supported:
                    print(f'Final fit: {station} {variable} {variant}, {len(final)} rows; cutoff {wib(FREEZE)}', flush=True)
                    descriptor = fit(final, variant, variable, history,
                                     output / 'models/final' / station / variant / variable, output)
                    catalog[station].setdefault(variant, {})[variable] = descriptor

    # The exact-only control and history experiments must use identical labels/rows.
    for row in audit:
        if row['variant'] == 'catboost_base_exact':
            other = next(a for a in audit if a['station'] == row['station'] and a['variable'] == row['variable']
                         and a['stage'] == row['stage'] and a['variant'] == 'catboost_history_exact')
            assert row['row_signature'] == other['row_signature']
    save_json(output / 'models.json', {'version': VERSION, 'catalog': catalog, 'selection': selections})
    save_json(output / 'training_audit.json', audit)
    write_csv(output / 'validation_scores.csv', validation)
    write_csv(output / 'validation_predictions.csv', comparisons)
    save_json(output / 'selection.json', selections)

    predictions = []
    frozen_features = []
    originals = {(r['station'], r['time']): r for r in context['original_frozen']}
    for station in context['manifest']['stations']:
        rows = [r for r in context['frozen'] if r['station'] == station]
        outcomes = {}
        for variable, key in VARIABLES.items():
            inputs = [{**r, 'raw': r['forecast_' + key]} for r in rows]
            outcomes[variable] = {}
            for variant in VARIANTS:
                descriptor = catalog[station].get(variant, {}).get(variable)
                values, probs = predict(descriptor, inputs, history, output) if descriptor else ([r['raw'] for r in inputs], [None] * len(rows))
                outcomes[variable][variant] = values
                if variable == 'rain':
                    outcomes.setdefault('rain_probability', {})[variant] = probs
        rain_train = paired_rows(context, station, 'rain', FREEZE)
        frequency = sum(r['observed'] >= EVENT_MM - 1e-9 for r in rain_train) / len(rain_train) if rain_train else None
        for i, row in enumerate(rows):
            original = originals[station, row['time']]
            item = {'station': station, 'time': row['time'], 'issue': row['issue'], 'day': row['day'],
                    'interval_start_wib': wib(row['time'] - 3600), 'interval_end_wib': wib(row['time']),
                    'temperature_humidity_valid_at_wib': wib(row['time'])}
            for variant in VARIANTS:
                item[variant + '_status'] = 'trained_station_model' if variant in catalog[station] else 'raw_fallback_no_validation'
            for variable, key in VARIABLES.items():
                item['raw_' + key] = row['forecast_' + key]
                item['v2_' + key] = original['v2_' + key]
                for variant in VARIANTS:
                    item[variant + '_' + key] = outcomes[variable][variant][i]
                method = selections[station][variable]['method']
                column = {'raw_gfs': 'raw_' + key, 'engine_v2': 'v2_' + key}.get(method, method + '_' + key)
                item['selected_' + key] = item[column]
                item['selected_' + variable + '_method'] = method
            item['v2_rain_probability'] = original['rain_probability']
            for variant in VARIANTS:
                item[variant + '_rain_probability'] = outcomes['rain_probability'][variant][i]
            method = selections[station]['rain_probability']['method']
            item['selected_rain_probability'] = (original['rain_probability'] if method == 'engine_v2' else frequency if method == 'training_climatology'
                else item.get(method + '_rain_probability'))
            item['selected_rain_probability_method'] = method
            predictions.append(item)
            frozen_features.append({'station': station, 'time': row['time'], 'issue': row['issue'],
                'day': row['day'], 'hour': row['hour'], 'forecast_t': row['forecast_t'],
                'forecast_h': row['forecast_h'], 'forecast_rain': row['forecast_rain'],
                'base_features': feature_values(row, 'catboost_base_full', history),
                'history_features': history.get(station, FREEZE)})
    save_json(output / 'frozen_predictions.json', {'version': VERSION, 'created_at_utc': now(),
        'freeze_wib': wib(FREEZE), 'source_run_initialized_utc': context['manifest']['frozen_run_initialized_utc'],
        'benchmark_actuals_seen': False, 'stations': context['manifest']['stations'], 'predictions': predictions})
    save_json(output / 'frozen_features.json', frozen_features)
    write_csv(output / 'frozen_forecasts.csv', predictions)
    write_csv(output / 'feature_availability.csv', history.audit)
    save_json(output / 'station_support.json', per_station)
    write_summaries(predictions, output)
    from .report import plots, report
    plots(predictions, validation, output)
    report(output)
    verify_files(context['output'], context['lock']['immutable_files'])
    print(json.dumps({'output': str(output), 'frozen_rows': len(predictions), 'selection': selections}, indent=2), flush=True)


def write_summaries(predictions, output):
    daily, windows = [], []
    amount_columns = ['raw_rain', 'v2_rain'] + [v + '_rain' for v in VARIANTS] + ['selected_rain']
    for station in sorted({r['station'] for r in predictions}):
        rows = sorted((r for r in predictions if r['station'] == station), key=lambda r: r['time'])
        for hours in (1, 6, 12, 24):
            sample = rows[:hours]
            windows.append({'station': station, 'hours': hours, 'start_wib': sample[0]['interval_start_wib'],
                'end_wib': sample[-1]['interval_end_wib'], **{key: sum(r[key] for r in sample) for key in amount_columns},
                'selected_rain_probability': sample[0]['selected_rain_probability'] if hours == 1 else None,
                'probability_status': 'hourly_event' if hours == 1 else 'unavailable_joint_window'})
        groups = collections.defaultdict(list)
        for row in rows:
            groups[row['interval_start_wib'][:10]].append(row)
        for date, sample in sorted(groups.items()):
            assert len(sample) == 24
            daily.append({'station': station, 'date_wib': date, **{key: sum(r[key] for r in sample) for key in amount_columns},
                'selected_temperature_mean_c': sum(r['selected_t'] for r in sample) / 24,
                'selected_humidity_mean_pct': sum(r['selected_h'] for r in sample) / 24})
    write_csv(output / 'forecast_windows.csv', windows)
    write_csv(output / 'daily_forecasts.csv', daily)


def verify(output=DEFAULT_OUTPUT, require_lock=False):
    output = Path(output)
    lock_path = output / 'candidate_lock.json'
    if require_lock or lock_path.exists():
        lock = read_json(lock_path)
        verify_files(output, lock['immutable_files'])
    reference = read_json(output / 'baseline_reference.json')
    baseline = Path(reference['baseline_root']) / 'output/engine_v2/benchmark_20261103'
    verify_files(baseline, reference['immutable_files'])
    if digest(baseline / 'benchmark_lock.json') != reference['baseline_lock_sha256']:
        raise ValueError('Original V2 lock changed')
    inputs = read_json(output / 'input_checksums.json')
    verify_files(inputs['root'], inputs['files'])
    audit = read_json(output / 'training_audit.json')
    for row in audit:
        cutoff = VALIDATION_START if row['stage'] == 'validation' else FREEZE
        for field in ('latest_target_wib', 'latest_observation_available_wib'):
            if row[field]:
                import datetime as dt
                assert dt.datetime.fromisoformat(row[field]).timestamp() < cutoff
    import csv
    with (output / 'feature_availability.csv').open(encoding='utf-8-sig') as stream:
        for row in csv.DictReader(stream):
            issue = float(row['issue_unix'])
            assert issue <= FREEZE
            for name in ('max_observation_available_at', 'max_observation_measured_at'):
                assert not row[name] or float(row[name]) <= issue
            assert not row['max_prior_forecast_issue'] or float(row['max_prior_forecast_issue']) < issue
    # Confirm the original V2 validation recipe is reproduced on the same cases,
    # rather than accidentally scoring its final fitted parameters in-sample.
    with (baseline / 'validation_candidates.csv').open(encoding='utf-8-sig') as stream:
        original_validation = list(csv.DictReader(stream))
    with (output / 'validation_scores.csv').open(encoding='utf-8-sig') as stream:
        new_validation = list(csv.DictReader(stream))
    for station in ('X50', 'X66'):
        for variable in ('temperature', 'humidity', 'rain'):
            chosen = [r for r in original_validation if r['station'] == station and r['variable'] == variable
                      and r['selected'].lower() == 'true']
            total = sum(float(r['n']) for r in chosen)
            actual = next(r for r in new_validation if r['station'] == station and r['variable'] == variable
                          and r['model'] == 'engine_v2' and r['scope'] == 'all_168h')
            assert int(actual['n']) == total
            for metric in ('mae', 'bias'):
                expected = sum(float(r[metric]) * float(r['n']) for r in chosen) / total
                assert abs(float(actual[metric]) - expected) < 1e-8
    for row in audit:
        if row['variant'] == 'catboost_base_exact':
            other = next(a for a in audit if a['station'] == row['station'] and a['variable'] == row['variable']
                         and a['stage'] == row['stage'] and a['variant'] == 'catboost_history_exact')
            assert row['row_signature'] == other['row_signature']
    package = read_json(output / 'frozen_predictions.json')
    assert package['benchmark_actuals_seen'] is False
    assert package['source_run_initialized_utc'] == '2026-11-02T06:00:00+00:00'
    rows = package['predictions']
    selection = read_json(output / 'selection.json')
    original_probabilities = read_json(baseline / 'models.json')['models']
    assert len(rows) == 672 and len({(r['station'], r['time']) for r in rows}) == 672
    for station in package['stations']:
        sample = sorted((r for r in rows if r['station'] == station), key=lambda r: r['time'])
        assert [r['time'] for r in sample] == [int(FREEZE) + h * 3600 for h in range(1, 169)]
        for row in sample:
            assert row['issue'] == FREEZE
            for prefix in ('raw', 'v2') + VARIANTS + ('selected',):
                assert all(finite(row[prefix + '_' + key]) for key in VARIABLES.values())
                assert 0 <= row[prefix + '_h'] <= 100 and row[prefix + '_rain'] >= 0
                p = row.get(prefix + '_rain_probability')
                assert p is None or 0 <= p <= 1
            for variable, key in VARIABLES.items():
                method = selection[station][variable]['method']
                column = {'raw_gfs': 'raw_' + key, 'engine_v2': 'v2_' + key}.get(method, method + '_' + key)
                assert row['selected_' + key] == row[column]
                assert row['selected_' + variable + '_method'] == method
            method = selection[station]['rain_probability']['method']
            probability = (row['v2_rain_probability'] if method == 'engine_v2' else
                           original_probabilities[station]['rain_climatology_probability'] if method == 'training_climatology'
                           else row.get(method + '_rain_probability'))
            assert row['selected_rain_probability'] == probability
            if station in ('X51', 'X67'):
                assert all(row['selected_' + key] == row['raw_' + key] for key in VARIABLES.values())
                assert row['selected_rain_probability'] is None
                assert all(row[v + '_status'] == 'raw_fallback_no_validation' for v in VARIANTS)
    # Reproduce every CatBoost prediction by reloading the saved model files and
    # saved initial contexts, without reading any new observations.
    model_catalog = read_json(output / 'models.json')['catalog']
    frozen = read_json(output / 'frozen_features.json')
    class FrozenHistory:
        def get(self, station, issue):
            assert issue == FREEZE
            return next(r['history_features'] for r in frozen if r['station'] == station)
    for station, variants in model_catalog.items():
        target_rows = [r for r in frozen if r['station'] == station]
        expected = [r for r in rows if r['station'] == station]
        for variant, variables in variants.items():
            for variable, descriptor in variables.items():
                key = VARIABLES[variable]
                predictors = [{**r, 'raw': r['forecast_' + key]} for r in target_rows]
                values, probabilities = predict(descriptor, predictors, FrozenHistory(), output)
                assert max(abs(v - r[variant + '_' + key]) for v, r in zip(values, expected)) < 1e-8
                if variable == 'rain':
                    assert max(abs(p - r[variant + '_rain_probability']) for p, r in zip(probabilities, expected)) < 1e-10
    return {'verified': True, 'frozen_rows': len(rows), 'original_v2_immutable_files': len(reference['immutable_files']),
            'saved_models_reproduced': sum(len(v) for s in model_catalog.values() for v in s.values()),
            'candidate_locked': lock_path.exists()}


def lock(output=DEFAULT_OUTPUT):
    output = Path(output)
    if (output / 'candidate_lock.json').exists():
        return verify(output, require_lock=True)
    result = verify(output)
    for folder in ('weather_catboost', 'tests'):
        for path in (VERSION_DIR / folder).rglob('*'):
            if path.is_file() and path.suffix == '.py':
                dest = output / 'frozen_source' / path.relative_to(VERSION_DIR)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest)
    for name in ('run.py', 'README.md', 'protocol.json', 'requirements.txt', 'requirements.lock.txt'):
        shutil.copyfile(VERSION_DIR / name, output / 'frozen_source' / name)
    files = {p.relative_to(output).as_posix(): digest(p) for p in sorted(output.rglob('*'))
             if p.is_file() and p.name != 'candidate_lock.json'}
    save_json(output / 'candidate_lock.json', {'version': VERSION, 'locked_at_utc': now(),
        'benchmark_actuals_seen': False, 'immutable_files': files})
    return verify(output, require_lock=True)
