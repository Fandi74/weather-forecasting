"""Forecast and issue-time SHT humidity history; no target-time features."""
import math
import statistics

FEATURES = ['gfs_temperature_c', 'gfs_humidity_pct', 'gfs_rain_mm', 'hour_sin', 'hour_cos', 'forecast_day',
            'hsht_latest', 'hsht_age_hours']
for hours in (3, 6, 12, 24):
    FEATURES += [f'hsht_{hours}h_mean', f'hsht_{hours}h_coverage']
FEATURES += ['hsht_change_3h', 'hsht_error_24h', 'hsht_error_24h_count']


class History:
    def __init__(self, observations, exact):
        self.observations, self.exact = observations, exact
        self.cache, self.audit = {}, []

    def get(self, issue):
        if issue is None:
            raise ValueError('Exact issue time required for humidity history')
        if issue in self.cache:
            return self.cache[issue]
        eligible = sorted((p for p in self.observations.values() if max(p['time'], p['available_at'], p['observed_at']) <= issue), key=lambda p: p['time'])
        by_time = {p['time']: p for p in eligible}
        latest = eligible[-1] if eligible else None
        age = (issue - latest['observed_at']) / 3600 if latest else None
        recent = latest is not None and age <= 6
        used = []
        def use(point):
            if max(point['time'], point['available_at'], point['observed_at']) > issue:
                raise ValueError('Future or unreceived feature observation')
            used.append(point['available_at'])
            return point['value']
        values = {'hsht_age_hours': age, 'hsht_latest': use(latest) if recent else None}
        for hours in (3, 6, 12, 24):
            points = [by_time.get(latest['time'] - k * 3600) for k in range(hours)] if recent else []
            observed = [use(p) for p in points if p is not None]
            values[f'hsht_{hours}h_mean'] = statistics.mean(observed) if observed else None
            values[f'hsht_{hours}h_coverage'] = len(observed) / hours
        prior = by_time.get(latest['time'] - 3 * 3600) if recent else None
        values['hsht_change_3h'] = use(latest) - use(prior) if prior else None
        previous = {}
        for row in self.exact:
            if row['issue'] < issue and issue - 26 * 3600 < row['time'] <= issue:
                if row['time'] not in previous or row['issue'] > previous[row['time']]['issue']:
                    previous[row['time']] = row
        errors, used_issues = [], []
        for time, forecast in previous.items():
            point = by_time.get(time)
            if point and issue - 24 * 3600 < point['observed_at'] <= issue:
                errors.append(use(point) - forecast['forecast_h'])
                used_issues.append(forecast['issue'])
        values['hsht_error_24h'] = statistics.mean(errors) if errors else None
        values['hsht_error_24h_count'] = len(errors)
        self.audit.append({'issue': issue, 'max_observation_available_at': max(used) if used else None,
                           'max_prior_forecast_issue': max(used_issues) if used_issues else None, 'latest_age_hours': age})
        self.cache[issue] = values
        return values


def vector(row, history):
    values = {'gfs_temperature_c': row['forecast_t'], 'gfs_humidity_pct': row['forecast_h'], 'gfs_rain_mm': row['forecast_rain'],
              'hour_sin': math.sin(2*math.pi*row['hour']/24), 'hour_cos': math.cos(2*math.pi*row['hour']/24), 'forecast_day': row['day']}
    values.update(history.get(row['issue']))
    return [values[k] for k in FEATURES]
