"""Issue-time station context. No target-time observations enter predictors."""
import math
import statistics

import numpy as np

from .common import VARIABLES, finite, wib

BASE_FEATURES = ['gfs_temperature_c', 'gfs_humidity_pct', 'gfs_rain_mm',
                 'local_hour_sin', 'local_hour_cos', 'forecast_day_band']
HISTORY_FEATURES = []
for _key in VARIABLES.values():
    HISTORY_FEATURES.extend([f'{_key}_latest', f'{_key}_age_hours'])
    for _hours in (3, 6, 12, 24):
        HISTORY_FEATURES.extend([f'{_key}_{_hours}h_value', f'{_key}_{_hours}h_coverage'])
    if _key in ('t', 'h'):
        HISTORY_FEATURES.append(f'{_key}_change_3h')
    for _hours in (3, 6, 24):
        HISTORY_FEATURES.extend([f'{_key}_error_{_hours}h', f'{_key}_error_{_hours}h_count'])


class HistoryBuilder:
    def __init__(self, observations, exact):
        self.observations = observations
        self.exact = exact
        self.cache = {}
        self.audit = []

    def get(self, station, issue):
        if issue is None:
            raise ValueError('History features require a known exact issue time')
        cache_key = (station, issue)
        if cache_key in self.cache:
            return self.cache[cache_key]
        observations = self.observations.get(station, {})
        features, used_available, used_measured, used_forecast_issues = {}, [], [], []

        def use(point, key):
            available, measured = point[key + '_available_at'], point[key + '_observed_at']
            if not (available <= issue and measured <= issue and point['time'] <= issue):
                raise ValueError('Feature observation was not available at issue')
            used_available.append(available)
            used_measured.append(measured)
            return point[key]

        for key in VARIABLES.values():
            eligible = [r for r in observations.values() if finite(r.get(key)) and r['time'] <= issue
                        and r[key + '_available_at'] <= issue and r[key + '_observed_at'] <= issue]
            eligible.sort(key=lambda r: r['time'])
            latest = eligible[-1] if eligible else None
            age = (issue - latest[key + '_observed_at']) / 3600 if latest else None
            features[key + '_age_hours'] = age
            recent = latest is not None and age <= 6
            features[key + '_latest'] = use(latest, key) if recent else None
            by_time = {r['time']: r for r in eligible}
            for hours in (3, 6, 12, 24):
                points = [by_time.get(latest['time'] - h * 3600) for h in range(hours)] if recent else []
                points = [p for p in points if p is not None]
                values = [use(p, key) for p in points]
                features[f'{key}_{hours}h_coverage'] = len(values) / hours
                # Missing rain hours are never zero-filled.
                features[f'{key}_{hours}h_value'] = ((sum(values) if len(values) == hours else None)
                    if key == 'rain' else (statistics.mean(values) if values else None))
            if key in ('t', 'h'):
                prior = by_time.get(latest['time'] - 3 * 3600) if recent else None
                features[key + '_change_3h'] = use(latest, key) - use(prior, key) if prior else None

            past_forecasts = {}
            for row in self.exact:
                if row['station'] != station or row['issue'] >= issue or row['time'] > issue:
                    continue
                if row['time'] <= issue - 26 * 3600:
                    continue
                previous = past_forecasts.get(row['time'])
                if previous is None or previous['issue'] < row['issue']:
                    past_forecasts[row['time']] = row
            for hours in (3, 6, 24):
                errors = []
                for time, row in past_forecasts.items():
                    point = by_time.get(time)
                    raw = row.get('forecast_' + key)
                    if point and issue - hours * 3600 < point[key + '_observed_at'] <= issue and finite(raw):
                        errors.append(use(point, key) - raw)
                        used_forecast_issues.append(row['issue'])
                features[f'{key}_error_{hours}h'] = statistics.mean(errors) if errors else None
                features[f'{key}_error_{hours}h_count'] = len(errors)

        self.audit.append({'station': station, 'issue_wib': wib(issue), 'issue_unix': issue,
                           'max_observation_available_at': max(used_available) if used_available else None,
                           'max_observation_measured_at': max(used_measured) if used_measured else None,
                           'max_prior_forecast_issue': max(used_forecast_issues) if used_forecast_issues else None})
        self.cache[cache_key] = features
        return features


def feature_names(variant):
    return BASE_FEATURES + (HISTORY_FEATURES if variant == 'catboost_history_exact' else [])


def feature_values(row, variant, history):
    result = {'gfs_temperature_c': row['forecast_t'], 'gfs_humidity_pct': row['forecast_h'],
              'gfs_rain_mm': row['forecast_rain'],
              'local_hour_sin': math.sin(2 * math.pi * row['hour'] / 24),
              'local_hour_cos': math.cos(2 * math.pi * row['hour'] / 24),
              'forecast_day_band': row['day']}
    if variant == 'catboost_history_exact':
        result.update(history.get(row['station'], row['issue']))
    return result


def matrix(rows, variant, history):
    names = feature_names(variant)
    values = [feature_values(r, variant, history) for r in rows]
    return np.array([[np.nan if v.get(name) is None else v[name] for name in names] for v in values], dtype=np.float32)
