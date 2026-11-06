"""Later blinded scoring. No fit, collection or feature updates are performed."""
import datetime as dt
import copy
from pathlib import Path

from .common import (EVENT_MM, FREEZE, UTC, VARIABLES, VARIANTS, digest, now,
                     read_json, save_json, write_csv)
from .data import baseline_context
from .experiment import probability_metrics, verify


def score(workspace, output, source_root, device_map=None):
    output = Path(output)
    verify(output, require_lock=True)
    context = baseline_context(workspace)
    from observations import prepare_all
    package = read_json(output / 'frozen_predictions.json')
    config = copy.deepcopy(package['stations'])
    mapping = read_json(device_map) if device_map else {}
    for station, identity in mapping.items():
        if station not in config or not isinstance(identity, str) or not identity:
            raise ValueError('Invalid scoring-only device identity mapping')
        config[station]['expected_device_id'] = identity
    observations, quality = prepare_all(Path(source_root), config=config)
    score_time = dt.datetime.now(UTC).timestamp()
    directory = output.parent / ('scores_' + dt.datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ'))
    directory.mkdir(exist_ok=False)
    names = ('raw', 'v2') + VARIANTS + ('selected',)
    scores, comparisons, windows = [], [], []
    for station in package['stations']:
        rows = sorted((r for r in package['predictions'] if r['station'] == station), key=lambda r: r['time'])
        for variable, key in VARIABLES.items():
            paired = []
            for row in rows:
                obs = observations.get(station, {}).get(row['time'], {})
                actual = obs.get(key)
                if obs.get(key + '_observed_at', float('inf')) > score_time:
                    actual = None
                if actual is not None:
                    paired.append({**row, 'raw': row['raw_' + key], 'observed': actual})
                comparisons.append({'station': station, 'variable': variable, 'interval_end_wib': row['interval_end_wib'],
                    'actual': actual, 'status': 'matched' if actual is not None else 'missing_actual',
                    **{name: row[name + '_' + key] for name in names}})
            for name in names:
                values = [r[name + '_' + key] for r in paired]
                scores.append({'station': station, 'variable': variable, 'model': name, 'expected_hours': 168,
                               **context['core'].metrics(paired, values, rain=variable == 'rain')})
        probability_rows, probabilities = [], {name: [] for name in names if name != 'raw'}
        for row in rows:
            obs = observations.get(station, {}).get(row['time'], {})
            if obs.get('rain') is not None and obs.get('rain_observed_at', float('inf')) <= score_time:
                probability_rows.append({'observed': obs['rain']})
                for name in probabilities:
                    probabilities[name].append(row.get(name + '_rain_probability'))
        for name, values in probabilities.items():
            scores.append({'station': station, 'variable': 'rain_probability', 'model': name,
                           'expected_hours': 168, **probability_metrics(probability_rows, values)})
        for hours in (1, 6, 12, 24):
            pairs = []
            for i in range(len(rows) - hours + 1):
                group = rows[i:i + hours]
                actuals = [observations.get(station, {}).get(r['time'], {}) for r in group]
                if any(a.get('rain') is None or a.get('rain_observed_at', float('inf')) > score_time for a in actuals):
                    continue
                pairs.append({'observed': sum(a['rain'] for a in actuals),
                              **{name: sum(r[name + '_rain'] for r in group) for name in names}})
            for name in names:
                windows.append({'station': station, 'hours': hours, 'model': name,
                    'expected_overlapping_windows': max(0, 169 - hours),
                    **context['core'].metrics(pairs, [r[name] for r in pairs], rain=False)})
    write_csv(directory / 'weekly_accuracy.csv', scores)
    write_csv(directory / 'hourly_comparison.csv', comparisons)
    write_csv(directory / 'rain_window_accuracy.csv', windows)
    save_json(directory / 'scoring_provenance.json', {'scored_at_utc': now(), 'model_refitted': False,
        'frozen_predictions_sha256': digest(output / 'frozen_predictions.json'),
        'candidate_lock_sha256': digest(output / 'candidate_lock.json'), 'quality': quality,
        'scoring_only_device_map': mapping})
    lines = ['# Frozen CatBoost benchmark scoring', '',
        'Original GFS, V2, all CatBoost variants and selected components are compared on identical '
        'available observations. Models were not refitted. Missing observations remain missing.', '',
        '| Station | Variable | Model | Matched hours | MAE | RMSE | Brier |',
        '| --- | --- | --- | ---: | ---: | ---: | ---: |']
    for row in scores:
        def fmt(key):
            value = row.get(key)
            return '—' if value is None else f'{value:.4f}'
        lines.append(f"| {row['station']} | {row['variable']} | {row['model']} | {row['n']} | {fmt('mae')} | {fmt('rmse')} | {fmt('brier')} |")
    (directory / 'accuracy_report.md').write_text('\n'.join(lines), encoding='utf-8')
    verify(output, require_lock=True)
    return {'output': str(directory), 'model_refitted': False,
            'matched_station_variable_hours': sum(r['n'] for r in scores if r['model'] == 'raw')}
