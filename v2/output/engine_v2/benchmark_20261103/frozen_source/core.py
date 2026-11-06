"""Fresh statistical baseline. No dependency on the original dashboard engine.

Annual fixed-day GFS pairs provide training history. Exact earlier weekly runs
add matching lead structure and form the October validation experiment. The
November benchmark is never used to select, fit or activate a correction.
"""
import collections
import csv
import datetime as dt
import json
import math
import statistics
from pathlib import Path

import numpy as np

from collect import DATA, FREEZE, ROOT, UTC, VARIABLES, WIB
from observations import TIP_MM

VALIDATION_START = dt.datetime(2026, 10, 1, tzinfo=WIB).timestamp()
MIN_TRAIN_PAIRS = 168
MIN_VALIDATION_PAIRS = 48
MIN_HOUR_PAIRS = 8
VARIABLE_KEYS = {'temperature': ('t', 'temperature_2m'),
                 'humidity': ('h', 'relative_humidity_2m'),
                 'rain': ('rain', 'precipitation')}


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def clip(value, variable):
    if variable == 'humidity':
        return min(100.0, max(0.0, value))
    return max(0.0, value) if variable == 'rain' else value


def target_day(hours):
    if not 0 < hours <= 168:
        raise ValueError('Forecast target is outside the seven-day benchmark')
    return int(math.ceil(hours / 24))


def read_envelope(path):
    return json.loads(path.read_text(encoding='utf-8'))['payload']


def daily_run_rows(payload, stations, issue):
    """168 preceding-hour intervals; temperature/humidity valid at interval end."""
    for station, slot in zip(stations, payload):
        hourly = slot['hourly']
        lookup = {t: i for i, t in enumerate(hourly['time'])}
        for h in range(1, 169):
            end = int(issue + h * 3600)
            i = lookup[end]
            yield {'station': station, 'time': end, 'issue': int(issue), 'day': target_day(h),
                   'hour': dt.datetime.fromtimestamp(end, WIB).hour,
                   'forecast_t': hourly['temperature_2m'][i],
                   'forecast_h': hourly['relative_humidity_2m'][i],
                   'forecast_rain': hourly['precipitation'][i], 'source_kind': 'exact_weekly_run'}


def load_gfs():
    manifest = json.loads((DATA / 'manifest.json').read_text())
    stations = list(manifest['stations'])
    if not manifest.get('history_complete') or len(manifest.get('history_chunks', [])) != 13:
        raise ValueError('The requested one-year GFS archive is incomplete')
    if len(manifest.get('weekly_samples', [])) != 30:
        raise ValueError('The weekly calibration/validation archive is incomplete')
    annual, exact, coverage = [], [], collections.Counter()
    for chunk in manifest['history_chunks']:
        payload = read_envelope(DATA / chunk['file'])
        for station, slot in zip(stations, payload):
            hourly = slot['hourly']
            for i, timestamp in enumerate(hourly['time']):
                if timestamp >= FREEZE.timestamp():
                    raise ValueError('Post-cutoff target detected in annual training history')
                coverage[station] += 1
                for day in range(1, 8):
                    annual.append({'station': station, 'time': timestamp, 'day': day,
                                   'hour': dt.datetime.fromtimestamp(timestamp, WIB).hour,
                                   'issue': None, 'source_kind': 'fixed_day_lead',
                                   **{f'forecast_{key}': hourly[f'{variable}_previous_day{day}'][i]
                                      for key, variable in (('t', VARIABLES[0]), ('h', VARIABLES[1]), ('rain', VARIABLES[2]))}})
    if any(coverage[s] != 8760 for s in stations):
        raise ValueError('Annual coverage does not equal 8760 target hours per station')
    for sample in manifest['weekly_samples']:
        issue = dt.datetime.fromisoformat(sample['service_issue_wib']).timestamp()
        exact.extend(daily_run_rows(read_envelope(DATA / sample['file']), stations, issue))
    frozen = list(daily_run_rows(read_envelope(DATA / manifest['frozen']['file']), stations, FREEZE.timestamp()))
    return manifest, annual, exact, frozen


def attach_observations(forecasts, observations, variable, cutoff):
    observation_key, _ = VARIABLE_KEYS[variable]
    forecast_key = 'forecast_' + observation_key
    for row in forecasts:
        point = observations.get(row['station'], {}).get(row['time'], {})
        observed = point.get(observation_key)
        available = point.get(observation_key + '_available_at', float('inf'))
        measured = point.get(observation_key + '_observed_at', float('inf'))
        if row['time'] >= cutoff or measured >= cutoff or available >= cutoff:
            continue
        if finite(row.get(forecast_key)) and finite(observed):
            yield {**row, 'raw': row[forecast_key], 'observed': observed,
                   'observation_available_at': available, 'observation_measured_at': measured}


def training_rows(annual, exact, observations, variable, cutoff):
    # One case per station, target and forecast-day band. Prefer an exact weekly
    # run when it represents that band; do not count it twice with its proxy.
    combined = {}
    for rows in (annual, exact):
        for row in attach_observations(rows, observations, variable, cutoff):
            combined[row['station'], row['time'], row['day']] = row
    return list(combined.values())


def metrics(rows, predictions=None, rain=False):
    if not rows:
        return {'n': 0, 'mae': None, 'rmse': None, 'bias': None}
    predicted = [r['raw'] for r in rows] if predictions is None else predictions
    error = [p - r['observed'] for p, r in zip(predicted, rows)]
    result = {'n': len(error), 'mae': statistics.mean(abs(e) for e in error),
              'rmse': math.sqrt(statistics.mean(e * e for e in error)), 'bias': statistics.mean(error)}
    if rain:
        obs, pred = [r['observed'] for r in rows], predicted
        wet = [o >= TIP_MM - 1e-9 for o in obs]
        hits = sum(w and p >= TIP_MM - 1e-9 for w, p in zip(wet, pred))
        misses = sum(w and p < TIP_MM - 1e-9 for w, p in zip(wet, pred))
        false = sum(not w and p >= TIP_MM - 1e-9 for w, p in zip(wet, pred))
        result.update({'observed_total_mm': sum(obs), 'predicted_total_mm': sum(pred),
                       'observed_wet_hours': sum(wet), 'hits': hits, 'misses': misses, 'false_alarms': false,
                       'recall': hits / (hits + misses) if hits + misses else None,
                       'precision': hits / (hits + false) if hits + false else None,
                       'wet_mae': statistics.mean(abs(p - o) for p, o, w in zip(pred, obs, wet) if w) if any(wet) else None})
    return result


def fit_offset(rows, method):
    residuals = [r['observed'] - r['raw'] for r in rows]
    base = statistics.median(residuals) if residuals else 0.0
    hours = {}
    if method == 'hourly_median_residual':
        grouped = collections.defaultdict(list)
        for row, residual in zip(rows, residuals):
            grouped[row['hour']].append(residual)
        hours = {str(h): statistics.median(values) for h, values in grouped.items() if len(values) >= MIN_HOUR_PAIRS}
    return {'method': method, 'offset': base, 'hour_offsets': hours, 'training_pairs': len(rows)}


def offset_predict(row, model, variable):
    if model['method'] == 'raw':
        return row['raw']
    adjustment = model.get('hour_offsets', {}).get(str(row['hour']), model['offset'])
    return clip(row['raw'] + adjustment, variable)


def rain_features(rows):
    return np.array([[math.log1p(max(0, r['forecast_rain'])), r['forecast_h'] / 100,
                      math.sin(2 * math.pi * r['hour'] / 24), math.cos(2 * math.pi * r['hour'] / 24),
                      r['day'] / 7] for r in rows], dtype=float)


def scale_features(rows, transform=None):
    raw = rain_features(rows)
    if transform is None:
        mean, std = raw.mean(axis=0), raw.std(axis=0)
        std[std < 1e-8] = 1
        transform = {'mean': mean.tolist(), 'std': std.tolist()}
    x = (raw - np.array(transform['mean'])) / np.array(transform['std'])
    return np.column_stack([np.ones(len(x)), x]), transform


def sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -35, 35)))


def fit_logistic(rows, penalty):
    x, transform = scale_features(rows)
    y = np.array([r['observed'] >= TIP_MM - 1e-9 for r in rows], dtype=float)
    frequency = float(y.mean())
    if y.sum() < 10 or (1 - y).sum() < 10:
        return {'method': 'climatology', 'probability': frequency}
    beta = np.zeros(x.shape[1])
    beta[0] = math.log(frequency / (1 - frequency))
    ridge = np.eye(x.shape[1]) * penalty
    ridge[0, 0] = 0
    for _ in range(60):
        p = sigmoid(x @ beta)
        hessian = x.T @ (x * np.maximum(p * (1 - p), 1e-8)[:, None]) + ridge
        step = np.linalg.solve(hessian, x.T @ (y - p) - ridge @ beta)
        beta += step
        if np.max(np.abs(step)) < 1e-7:
            break
    return {'method': 'logistic', 'penalty': penalty, 'coefficients': beta.tolist(), 'transform': transform}


def probability_predict(rows, model):
    if model['method'] == 'climatology':
        return [model['probability']] * len(rows)
    x, _ = scale_features(rows, model['transform'])
    return sigmoid(x @ np.array(model['coefficients'])).tolist()


def fit_positive_amount(rows, penalty):
    positive = [r for r in rows if r['observed'] >= TIP_MM - 1e-9]
    if len(positive) < 10:
        return None
    x, transform = scale_features(positive)
    y = np.log([r['observed'] for r in positive])
    ridge = np.eye(x.shape[1]) * penalty
    ridge[0, 0] = 0
    beta = np.linalg.solve(x.T @ x + ridge, x.T @ y)
    smearing = float(np.exp(y - x @ beta).mean())
    return {'penalty': penalty, 'coefficients': beta.tolist(), 'transform': transform, 'smearing': smearing}


def rain_predict(rows, model):
    if model['method'] == 'raw':
        return [r['raw'] for r in rows]
    if model['method'] == 'nonnegative_slope':
        return [max(0.0, r['raw'] * model['slope']) for r in rows]
    probabilities = probability_predict(rows, model['occurrence'])
    amount = model['positive_amount']
    x, _ = scale_features(rows, amount['transform'])
    positive_mean = np.exp(np.clip(x @ np.array(amount['coefficients']), -20, 20)) * amount['smearing']
    return (np.array(probabilities) * positive_mean).tolist()


def fit_rain(rows, method, penalty=1.0, occurrence_method=None):
    if method == 'raw':
        return {'method': 'raw'}
    if method == 'nonnegative_slope':
        denominator = sum(r['raw'] ** 2 for r in rows)
        slope = max(0.0, sum(r['raw'] * r['observed'] for r in rows) / denominator) if denominator else 1.0
        return {'method': method, 'slope': slope}
    occurrence = fit_logistic(rows, penalty)
    amount = fit_positive_amount(rows, penalty)
    if amount is None:
        return {'method': 'raw'}
    return {'method': 'hurdle', 'occurrence': occurrence, 'positive_amount': amount, 'penalty': penalty}


def fit_models(annual, exact, observations, stations):
    models, validation = {}, []
    cutoff = FREEZE.timestamp()
    for station in stations:
        models[station] = {'temperature': {}, 'humidity': {}}
        for variable in ('temperature', 'humidity'):
            initial = [r for r in training_rows(annual, exact, observations, variable, VALIDATION_START) if r['station'] == station]
            final = [r for r in training_rows(annual, exact, observations, variable, cutoff) if r['station'] == station]
            eligible = [r for r in attach_observations(exact, observations, variable, cutoff)
                        if r['station'] == station and r['issue'] >= VALIDATION_START]
            for day in range(1, 8):
                train, val = [r for r in initial if r['day'] == day], [r for r in eligible if r['day'] == day]
                choices = [('raw', {'method': 'raw'})]
                if len(train) >= MIN_TRAIN_PAIRS and len(val) >= MIN_VALIDATION_PAIRS:
                    choices.extend((name, fit_offset(train, name)) for name in ('median_residual', 'hourly_median_residual'))
                scored = [(name, model, metrics(val, [offset_predict(r, model, variable) for r in val])) for name, model in choices]
                selected = min(scored, key=lambda item: (item[2]['mae'] if item[2]['mae'] is not None else float('inf'), item[0] != 'raw'))
                name = selected[0]
                fit = {'method': 'raw'} if name == 'raw' else fit_offset([r for r in final if r['day'] == day], name)
                fit.update({'selected_on': 'October exact-run validation', 'validation_pairs': len(val),
                            'training_cutoff_exclusive_utc': FREEZE.astimezone(UTC).isoformat(),
                            'fallback_reason': 'no reliable October validation or raw was best' if name == 'raw' else None})
                models[station][variable][str(day)] = fit
                for candidate, _, scores in scored:
                    validation.append({'station': station, 'variable': variable, 'forecast_day': day,
                                       'candidate': candidate, 'selected': candidate == name, **scores})
        train = [r for r in training_rows(annual, exact, observations, 'rain', VALIDATION_START)
                 if r['station'] == station and finite(r['forecast_h'])]
        final = [r for r in training_rows(annual, exact, observations, 'rain', cutoff)
                 if r['station'] == station and finite(r['forecast_h'])]
        val = [r for r in attach_observations(exact, observations, 'rain', cutoff)
               if r['station'] == station and r['issue'] >= VALIDATION_START and finite(r['forecast_h'])]
        models[station]['rain_climatology_probability'] = (statistics.mean(r['observed'] >= TIP_MM - 1e-9 for r in final) if final else None)
        choices = [('raw', {'method': 'raw'})]
        if len(train) >= MIN_TRAIN_PAIRS and len(val) >= MIN_VALIDATION_PAIRS:
            choices.append(('nonnegative_slope', fit_rain(train, 'nonnegative_slope')))
            choices.extend((f'hurdle_{p}', fit_rain(train, 'hurdle', p)) for p in (0.1, 1.0, 10.0))
        scored = [(name, model, metrics(val, rain_predict(val, model), rain=True)) for name, model in choices]
        selected = min(scored, key=lambda item: (item[2]['rmse'] if item[2]['rmse'] is not None else float('inf'), item[0] != 'raw'))
        name, model, _ = selected
        models[station]['rain'] = fit_rain(final, model['method'], model.get('penalty', 1.0))
        models[station]['rain'].update({'training_pairs': len(final), 'validation_pairs': len(val),
                                        'selected_on': 'October exact-run RMSE', 'training_cutoff_exclusive_utc': FREEZE.astimezone(UTC).isoformat()})
        for candidate, _, scores in scored:
            validation.append({'station': station, 'variable': 'rain', 'forecast_day': 'all',
                               'candidate': candidate, 'selected': candidate == name, **scores})
        if len(train) >= MIN_TRAIN_PAIRS and len(val) >= MIN_VALIDATION_PAIRS:
            frequency = statistics.mean(r['observed'] >= TIP_MM - 1e-9 for r in train)
            probability_candidates = [('climatology', {'method': 'climatology', 'probability': frequency})]
            probability_candidates.extend((f'logistic_{p}', fit_logistic(train, p)) for p in (0.1, 1.0, 10.0))
            evaluated = []
            for candidate, probability in probability_candidates:
                predictions = probability_predict(val, probability)
                brier = statistics.mean((p - (r['observed'] >= TIP_MM - 1e-9)) ** 2 for p, r in zip(predictions, val))
                evaluated.append((candidate, probability, brier))
            winner = min(evaluated, key=lambda item: item[2])
            models[station]['rain_probability'] = (fit_logistic(final, winner[1]['penalty'])
                if winner[1]['method'] == 'logistic' else {'method': 'climatology', 'probability': statistics.mean(r['observed'] >= TIP_MM - 1e-9 for r in final)})
            for candidate, _, brier in evaluated:
                validation.append({'station': station, 'variable': 'rain_probability', 'forecast_day': 'all',
                                   'candidate': candidate, 'selected': candidate == winner[0], 'n': len(val), 'brier': brier})
        else:
            models[station]['rain_probability'] = None
    return models, validation


def predict_frozen(rows, models):
    result = []
    for row in rows:
        station, day = row['station'], str(row['day'])
        item = {**row}
        for variable in ('temperature', 'humidity'):
            key, _ = VARIABLE_KEYS[variable]
            model = models[station][variable][day]
            item['v2_' + key] = offset_predict({**row, 'raw': row['forecast_' + key]}, model, variable)
            item[key + '_method'] = model['method']
        rain_model = models[station]['rain']
        item['v2_rain'] = rain_predict([{**row, 'raw': row['forecast_rain']}], rain_model)[0]
        item['rain_method'] = rain_model['method']
        probability = models[station]['rain_probability']
        item['rain_probability'] = probability_predict([row], probability)[0] if probability else None
        item['probability_method'] = probability['method'] if probability else 'unavailable_no_valid_calibration'
        result.append(item)
    if len(result) != 672 or len({(r['station'], r['time']) for r in result}) != 672:
        raise ValueError('Frozen forecast must contain 168 unique intervals for each of four locations')
    return result


def historical_scores(annual, observations, stations):
    rows = []
    for variable in VARIABLE_KEYS:
        pairs = list(attach_observations(annual, observations, variable, FREEZE.timestamp()))
        for station in stations:
            for day in range(1, 8):
                group = [r for r in pairs if r['station'] == station and r['day'] == day]
                rows.append({'station': station, 'variable': variable, 'fixed_lead_days': day,
                             'expected_hours': 8760, **metrics(group, rain=variable == 'rain')})
    return rows
