"""Combine component forecasts without changing their values or time meanings."""
import datetime as dt
import math

HORIZONS = (1, 6, 12, 24)
WIB = dt.timezone(dt.timedelta(hours=7))


def wib(value):
    return dt.datetime.fromtimestamp(value, WIB).isoformat()


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def compose_forecasts(hourly, rain):
    """Use V5 point values at each window end and V6 direct rain-window values."""
    if not hourly:
        raise ValueError('No hourly component forecasts')
    issues = {r['issue'] for r in hourly}
    if len(issues) != 1:
        raise ValueError('All component forecasts must share one issue time')
    issue = next(iter(issues))
    index = {(r['station'], r['time']): r for r in hourly}
    if len(index) != len(hourly):
        raise ValueError('Duplicate hourly component forecast')
    stations = sorted({r['station'] for r in hourly})
    rain_index = {}
    for r in rain:
        if r['issue'] != issue or r['end'] != issue + r['horizon']*3600:
            raise ValueError('Rain forecast issue/end does not align')
        key = (r['station'], r['horizon'])
        if key in rain_index:
            raise ValueError('Duplicate rain forecast')
        if r['horizon'] not in HORIZONS or r['station'] not in ['X50', 'X66']:
            raise ValueError('Unsupported V6 rain coverage')
        if not finite(r['selected_amount']) or r['selected_amount'] < 0:
            raise ValueError('Invalid rain amount')
        if not finite(r['selected_probability']) or not 0 <= r['selected_probability'] <= 1:
            raise ValueError('Invalid rain probability')
        rain_index[key] = r
    needed = {(s, h) for s in stations if s in ['X50', 'X66'] for h in HORIZONS}
    if set(rain_index) != needed:
        raise ValueError('Missing or unexpected V6 rain windows')
    result = []
    for station in stations:
        for horizon in HORIZONS:
            end = issue + horizon*3600
            try:
                point = index[station, end]
                pieces = [index[station, issue+k*3600] for k in range(1, horizon+1)]
            except KeyError as exc:
                raise ValueError('Missing hourly component coverage') from exc
            if not finite(point['selected_t']) or not finite(point['selected_h']) or not 0 <= point['selected_h'] <= 100:
                raise ValueError('Invalid point forecast')
            row = {'station': station, 'issue': issue, 'end': end, 'horizon': horizon,
                'issue_wib': wib(issue), 'end_wib': wib(end),
                'temperature_c': point['selected_t'], 'humidity_pct': point['selected_h'],
                'temperature_source': 'V2_via_V5', 'humidity_source': 'V5',
                'humidity_method': point['humidity_method'],
                'point_value_time': 'window_end', 'rain_amount_unit': 'mm_over_whole_window',
                'rain_event': 'whole_window_total_at_least_0.28_mm'}
            selected = rain_index.get((station, horizon))
            if selected:
                row.update(rainfall_mm=selected['selected_amount'],
                    rain_probability=selected['selected_probability'],
                    rainfall_source='V6_E11_corrected_1h_assumption',
                    rainfall_method=selected['selected_amount_method'],
                    rain_probability_method=selected['selected_probability_method'],
                    rainfall_experimental=True)
            else:
                if any(not finite(r['selected_rain']) or r['selected_rain'] < 0 for r in pieces):
                    raise ValueError('Invalid fallback rainfall')
                row.update(rainfall_mm=sum(r['selected_rain'] for r in pieces),
                    rain_probability=point['selected_rain_probability'] if horizon == 1 else None,
                    rainfall_source='V5_retained_V2_fallback',
                    rainfall_method='sum_of_existing_hourly_amounts',
                    rain_probability_method='retained_hourly_probability' if horizon == 1 else 'joint_probability_unavailable',
                    rainfall_experimental=False)
                if row['rain_probability'] is not None and (not finite(row['rain_probability']) or not 0 <= row['rain_probability'] <= 1):
                    raise ValueError('Invalid fallback probability')
            result.append(row)
    return result


def point_forecasts(hourly):
    """Keep all seven days of V5 temperature/humidity, without invented hourly rain."""
    return [{'station': r['station'], 'issue': r['issue'], 'time': r['time'],
        'end_wib': wib(r['time']), 'temperature_c': r['selected_t'], 'humidity_pct': r['selected_h'],
        'temperature_source': 'V2_via_V5', 'humidity_source': 'V5',
        'humidity_method': r['humidity_method']} for r in hourly]
