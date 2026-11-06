"""Build, lock and later score the blinded 3–9 November GFS benchmark.

Build/lock are separate from score. Scoring never calls fitting or collection.
"""
import argparse
import collections
import copy
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import zipfile

from collect import DATA, FREEZE, ROOT, UTC, WIB, utc_now
from core import (VARIABLE_KEYS, VALIDATION_START, attach_observations, fit_models,
                  historical_scores, load_gfs, metrics, predict_frozen, training_rows)
from observations import TIP_MM, prepare_all

DEFAULT_OUTPUT = ROOT / 'output/engine_v2/benchmark_20261103'


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path, rows, columns=None):
    if columns is None:
        columns = list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def wib(timestamp):
    return dt.datetime.fromtimestamp(timestamp, WIB).isoformat()


def frozen_csv(rows, stations):
    result = []
    for row in rows:
        m = stations[row['station']]
        result.append({'station': row['station'], 'interval_start_wib': wib(row['time'] - 3600),
                       'interval_end_wib': wib(row['time']), 'temperature_humidity_valid_at_wib': wib(row['time']),
                       'forecast_day': row['day'], 'latitude': m['latitude'], 'longitude': m['longitude'],
                       'site_elevation_m_used': m['elevation_m'],
                       'raw_gfs_temperature_c': row['forecast_t'], 'engine_v2_temperature_c': round(row['v2_t'], 6),
                       'raw_gfs_humidity_pct': row['forecast_h'], 'engine_v2_humidity_pct': round(row['v2_h'], 6),
                       'raw_gfs_rain_mm': row['forecast_rain'], 'engine_v2_rain_mm': round(row['v2_rain'], 6),
                       'engine_v2_rain_probability_pct': round(row['rain_probability'] * 100, 6) if row['rain_probability'] is not None else None,
                       'rain_event': 'interval rain >= 0.28 mm', 'temperature_method': row['t_method'],
                       'humidity_method': row['h_method'], 'rain_amount_method': row['rain_method'],
                       'probability_method': row['probability_method'],
                       'simulated_issue_wib': FREEZE.isoformat(), 'gfs_run_initialized_utc': '2026-11-02T06:00:00+00:00'})
    return result


def summaries(rows):
    daily, windows = [], []
    for station in sorted({r['station'] for r in rows}):
        station_rows = sorted((r for r in rows if r['station'] == station), key=lambda r: r['time'])
        groups = collections.defaultdict(list)
        for row in station_rows:
            groups[wib(row['time'] - 3600)[:10]].append(row)
        for date, group in sorted(groups.items()):
            assert len(group) == 24
            daily.append({'station': station, 'date_wib': date, 'hours': len(group),
                          'raw_gfs_rain_mm': sum(r['forecast_rain'] for r in group),
                          'engine_v2_rain_mm': sum(r['v2_rain'] for r in group),
                          'raw_gfs_temperature_mean_c': statistics.mean(r['forecast_t'] for r in group),
                          'engine_v2_temperature_mean_c': statistics.mean(r['v2_t'] for r in group),
                          'raw_gfs_humidity_mean_pct': statistics.mean(r['forecast_h'] for r in group),
                          'engine_v2_humidity_mean_pct': statistics.mean(r['v2_h'] for r in group)})
        for hours in (1, 6, 12, 24):
            group = station_rows[:hours]
            probability = group[0]['rain_probability'] if hours == 1 else None
            windows.append({'station': station, 'hours': hours, 'window_start_wib': wib(group[0]['time'] - 3600),
                            'window_end_wib': wib(group[-1]['time']),
                            'raw_gfs_rain_mm': sum(r['forecast_rain'] for r in group),
                            'engine_v2_rain_mm': sum(r['v2_rain'] for r in group),
                            'engine_v2_rain_probability_pct': probability * 100 if probability is not None else None,
                            'probability_status': ('hourly_event_model' if probability is not None else
                                                   'not_fitted_joint_window_probability' if hours > 1 else 'no_valid_calibration')})
    return daily, windows


def annual_exports(output, manifest):
    """Convenient full-year tables; raw provider envelopes remain preserved."""
    directory = output / 'history'
    directory.mkdir(exist_ok=True)
    tables = {station: [] for station in manifest['stations']}
    for chunk in manifest['history_chunks']:
        payload = json.loads((DATA / chunk['file']).read_text())['payload']
        for station, slot in zip(manifest['stations'], payload):
            hourly = slot['hourly']
            for i, timestamp in enumerate(hourly['time']):
                row = {'station': station, 'target_time_wib': wib(timestamp),
                       'target_time_utc': dt.datetime.fromtimestamp(timestamp, UTC).isoformat()}
                for variable, label, unit in [('temperature_2m', 'temperature', 'c'),
                                               ('relative_humidity_2m', 'humidity', 'pct'),
                                               ('precipitation', 'rain', 'mm')]:
                    for day in range(1, 8):
                        row[f'{label}_previous_day{day}_{unit}'] = hourly[f'{variable}_previous_day{day}'][i]
                tables[station].append(row)
    coverage = []
    for station, rows in tables.items():
        if len(rows) != 8760:
            raise ValueError('Annual CSV does not have 8760 targets')
        write_csv(directory / f'GFS_{station}_20251103_20261102.csv', rows)
        for field in rows[0]:
            if '_previous_day' in field:
                coverage.append({'station': station, 'series': field, 'expected_hours': 8760,
                                 'nonmissing_forecasts': sum(r[field] is not None for r in rows),
                                 'missing_forecasts': sum(r[field] is None for r in rows)})
    write_csv(output / 'gfs_archive_coverage.csv', coverage)


def training_audit(annual, exact, observations, stations):
    audit = {}
    for variable in VARIABLE_KEYS:
        pairs = training_rows(annual, exact, observations, variable, FREEZE.timestamp())
        audit[variable] = {}
        for station in stations:
            group = [r for r in pairs if r['station'] == station]
            audit[variable][station] = {'pairs': len(group),
                'unique_verification_hours': len({r['time'] for r in group}),
                'source_kinds': dict(collections.Counter(r['source_kind'] for r in group)),
                'latest_target_wib': wib(max(r['time'] for r in group)) if group else None,
                'latest_observation_available_wib': wib(max(r['observation_available_at'] for r in group)) if group else None}
            assert all(r['time'] < FREEZE.timestamp() and r['observation_available_at'] < FREEZE.timestamp() for r in group)
    return audit


def pooled_validation(validation, station, variable, selected):
    group = [r for r in validation if r['station'] == station and r['variable'] == variable
             and (r['selected'] if selected else r['candidate'] == 'raw')]
    n = sum(r.get('n', 0) for r in group)
    if not n:
        return {'n': 0, 'mae': None, 'rmse': None, 'bias': None}
    return {'n': n, 'mae': sum(r['mae'] * r['n'] for r in group) / n,
            'rmse': math.sqrt(sum(r['rmse'] ** 2 * r['n'] for r in group) / n),
            'bias': sum(r['bias'] * r['n'] for r in group) / n}


def display(value, decimals=3):
    return f'{value:.{decimals}f}' if value is not None else 'Unavailable'


def write_report(output, package, historical, validation, normalization):
    stations, predictions = package['stations'], package['predictions']
    lines = [
        '# Engine v2: frozen seven-day forecast and baseline report', '',
        '**Benchmark: 3–9 November 2026, WIB. The measurements for this week are deliberately withheld. Weekly accuracy is pending; it is not zero or perfect.**', '',
        '## Frozen experiment', '',
        '- Training target dates: 3 November 2025–2 November 2026. Every fitted observation and its assumed arrival precedes 3 November, 00:00 WIB.',
        '- Forecast target period: 3 November, 00:00 through 10 November, 00:00 WIB, expressed as 168 hourly intervals per location.',
        '- Future GFS source: the single run initialized **2 November 2026, 06:00 UTC (13:00 WIB)**. No GFS initialization from 3, 4 or 5 November is used.',
        '- Conservative availability assumption: six hours after initialization, before the simulated 3 November midnight issue. The actual historical Open-Meteo publication timestamp is not independently verified.',
        '- This forecast is reconstructed on 5 November from an archived earlier run. It was not operationally published by our system on 3 November.',
        '- This implementation was written fresh. It neither imports nor changes `dashboard/engine.mjs`, and does not use its 72/30 shrinkage formulas.', '',
        '## Inputs and station eligibility', '',
        '| Station | Accepted source readings | Latest supplied observation, WIB | Status |',
        '| --- | ---: | --- | --- |'
    ]
    for station, record in normalization.items():
        status = 'Historical measurements eligible; October validation determines corrections'
        if station == 'X51':
            status = 'History stops in August; no October validation, so raw forecast fallback'
        elif station == 'X67':
            status = 'Supplied export belongs to X66; excluded as X67 truth; raw forecast fallback'
        lines.append(f"| {station} | {record['accepted_source_records']:,} | {record['last_wib'] or 'Unavailable'} | {status} |")
    lines += ['', 'The X67 source duplicates 21,033 X66 weather/error records and carries X66’s device ID and coordinates. It is not counted as another station. X67 still receives its own location-specific GFS forecast.', '',
        'The user clarified E3=HDC1080, E8=soil temperature, E11=soil moisture and E12=leaf wetness. Those flags do not invalidate BME280 `t`/`h` or a valid rain gauge. Absent HDC/leaf fields can produce false firmware flags. This baseline uses BME280 `t`/`h` consistently and does not silently substitute SHT/HDC readings.', '',
        '**X66 reference discrepancy:** October medians are t=12.02°C versus tsht=18.885°C, and h=100% versus hsht=90%. The temperature streams were much closer in June. The user explicitly chose to retain t/h and flag this discrepancy. Thus X66 scores measure agreement with that retained stream; they do not verify the physical accuracy of the station. Its large temperature error remains visible.', '',
        'Temperature/humidity targets use the closest valid measurement within five minutes of the hourly instant. Rain totals require all six checked 10-minute intervals, 0.28 mm/tip consistency, no counter reset/gap and a maximum 90-second nominal-clock alignment. This clock adjustment is an explicit approximation. Missing rain coverage is not dry weather. Observation arrival is conservatively approximated as measurement time plus one hour because historical arrival timestamps were not exported.', '',
        '## One-year raw GFS baseline', '',
        'All four locations have 8,760 archived target hours and seven fixed day-lead series for each variable. Missing observations reduce verification coverage. The table shows the 24-hour-offset baseline across the supplied historical observations, not this week’s accuracy. Full day-1 through day-7 metrics are in `historical_gfs_accuracy.csv`.', '',
        '| Station | Variable | Valid hourly pairs | MAE | RMSE | Bias, forecast − measured |', '| --- | --- | ---: | ---: | ---: | ---: |']
    for row in historical:
        if row['fixed_lead_days'] == 1:
            lines.append(f"| {row['station']} | {row['variable']} | {row['n']:,} | {display(row['mae'])} | {display(row['rmse'])} | {display(row['bias'])} |")
    lines += ['', 'Units: temperature °C, humidity percentage points, rain mm per hour. GFS here means Open-Meteo’s explicit `gfs_seamless` recipe, including its elevation processing with the supplied site elevations; it is not untouched raw model-grid output.', '',
        '## Earlier October validation: selecting the new model', '',
        'Candidate fitting stops before 1 October. Selection uses four earlier seven-day forecasts issued on 6, 13, 20 and 27 October, with measurements available before the November cutoff. Annual fixed-day history supplies training pairs; earlier exact weekly-run cases replace matching station/target/day-band pairs rather than being counted twice. Fixed-day leads are representative of day bands, not every exact subdaily lead. The exact-run October check tests that approximation.', '',
        'These scores are validation results used to choose methods. They are not an untouched final test, and the chosen models are not proven to improve November forecasts. Final fitting then uses all eligible pre-cutoff training/validation history; November observations remain unseen.', '',
        '| Station | Variable | Validation pairs | Raw MAE | V2 MAE | Raw RMSE | V2 RMSE |', '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for station in stations:
        for variable in ('temperature', 'humidity', 'rain'):
            raw = pooled_validation(validation, station, variable, False)
            corrected = pooled_validation(validation, station, variable, True)
            lines.append(f"| {station} | {variable} | {raw['n']:,} | {display(raw['mae'])} | {display(corrected['mae'])} | {display(raw['rmse'])} | {display(corrected['rmse'])} |")
    lines += ['', '![Earlier October validation](validation.png)', '', 'Temperature/humidity choose raw, a median residual, or a forecast-day/local-hour median residual using MAE. Rain compares raw, a nonnegative least-squares slope and a two-part occurrence/positive-amount model using RMSE. The latter models use regularized regression; penalties are selected from declared candidates on October data. A selected improvement in one score can worsen another; inspect wet-event errors, misses and false alarms in `validation_candidates.csv`.', '',
        'Hourly rain occurrence is a separate probability model selected with Brier score against training-only climatology. Its event is **at least 0.28 mm in the forecast hour**, not Open-Meteo’s differently defined hourly probability. This baseline has no validated joint 6/12/24-hour probability model; those fields remain unavailable instead of being computed by adding hourly probabilities. Independent probability and amount candidates are not a fully coherent joint predictive distribution.', '',
        'The minimum training/validation counts and hour-specific support rules are declared prototype safeguards, not established scientific sufficiency criteria. X51 and X67 have no eligible October validation and retain raw forecasts. This experiment does not establish spatial correction over 50 km.', '',
        '## Forecast and baseline files', '',
        '- `history/GFS_[station]_20251103_20261102.csv`: full-year GFS tables, 8,760 targets per station with all seven fixed day-lead series for temperature, humidity and rain. `gfs_archive_coverage.csv` records missing-value coverage.',
        '- `frozen_forecasts.csv`: 672 rows, 168 per station, with raw GFS, V2, hourly rain-event probability when available and method labels.',
        '- `daily_forecasts.csv`: seven complete local dates per station. Rain is summed; temperature/humidity are means of the 24 interval-end instantaneous forecasts.',
        '- `forecast_windows.csv`: initial 1/6/12/24-hour rain totals with explicit endpoints.',
        '- `models.json`, `frozen_predictions.json`, `protocol.json` and the lock manifest preserve the exact baseline for later scoring.', '',
        '## Weekly benchmark status', '',
        '| Station | Expected forecast hours | Supplied benchmark observations | Weekly accuracy |', '| --- | ---: | ---: | --- |']
    for station in stations:
        lines.append(f'| {station} | 168 | 0 | Pending blinded actuals |')
    lines += ['', 'When the user supplies measurements from 3 November onward, run the scoring command without rebuilding the model. It verifies frozen file hashes, aligns measured outcomes and writes separate scores and comparison plots. Partial weeks report only matched observations and coverage; future or missing hours never count as zero rainfall.', '',
        '## Forecast plots', '']
    for station in stations:
        lines += [f'### {station}', '', f'![{station}: frozen raw and corrected forecasts](forecast_{station}.png)', '']
    lines += ['## Provenance and interpretation', '',
        'The station CSVs are preserved at their original paths. The training audit and source checksums are included in the package. Open-Meteo responses are saved under the project’s `data/engine_v2/gfs` directory, including monthly fixed-lead history, earlier exact-run samples and the frozen run. No station values or model values have been invented.', '',
        'The new station coordinates were supplied by the user; X50’s 1230 m elevation is estimated and other elevations are user-provided. These static metadata were used consistently in archive requests. Sensor quality checks establish consistency, not instrument calibration accuracy.', '',
        'Sources: [Open-Meteo Previous Runs](https://open-meteo.com/en/docs/previous-runs-api), [Single Runs](https://open-meteo.com/en/docs/single-runs-api), [variable definitions](https://open-meteo.com/en/docs). Weather data attribution: Open-Meteo, CC BY 4.0.', '']
    (output / 'baseline_report.md').write_text('\n'.join(lines), encoding='utf-8')


def build(source_root, output):
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'benchmark_lock.json').exists():
        raise ValueError('Benchmark is locked. Use score; never overwrite it with a new fit.')
    observations, normalization = prepare_all(source_root, ROOT / 'data/engine_v2/observations')
    manifest, annual, exact, frozen = load_gfs()
    print('GFS and station inputs checked; fitting fresh candidates...', flush=True)
    models, validation = fit_models(annual, exact, observations, manifest['stations'])
    predictions = predict_frozen(frozen, models)
    historical = historical_scores(annual, observations, manifest['stations'])
    audit = training_audit(annual, exact, observations, manifest['stations'])
    package = {'engine_version': 'engine_v2.0.0', 'created_at_utc': utc_now(),
               'simulated_issue_wib': FREEZE.isoformat(), 'stations': manifest['stations'],
               'gfs_run_initialized_utc': manifest['frozen_run_initialized_utc'],
               'predictions': predictions}
    save_json(output / 'models.json', {'version': 'engine_v2.0.0', 'models': models,
                                      'training_audit': audit, 'normalization': normalization})
    save_json(output / 'frozen_predictions.json', package)
    shutil.copyfile(ROOT / 'engine_v2/protocol.json', output / 'protocol.json')
    annual_exports(output, manifest)
    write_csv(output / 'frozen_forecasts.csv', frozen_csv(predictions, manifest['stations']))
    daily, windows = summaries(predictions)
    write_csv(output / 'daily_forecasts.csv', daily)
    write_csv(output / 'forecast_windows.csv', windows)
    write_csv(output / 'historical_gfs_accuracy.csv', historical)
    write_csv(output / 'validation_candidates.csv', validation)
    save_json(output / 'training_audit.json', audit)
    save_json(output / 'station_quality.json', normalization)
    inventory = ROOT / 'data/engine_v2/station_inventory.json'
    if inventory.exists():
        shutil.copyfile(inventory, output / 'source_inventory.json')
    # Preserve a manifest of every raw forecast envelope, not just a mutable path.
    raw_files = [DATA / c['file'] for c in manifest['history_chunks'] + manifest['weekly_samples']] + [DATA / manifest['frozen']['file']]
    save_json(output / 'input_checksums.json', {
        'forecast_files': {str(p.relative_to(ROOT)): digest(p) for p in raw_files},
        'station_files': {s['path']: s['sha256'] for r in normalization.values() for s in r['sources']},
        'excluded_sources': {s: r['excluded_sources'] for s, r in normalization.items() if r['excluded_sources']}})
    write_report(output, package, historical, validation, normalization)
    from plots import forecast_plots, validation_plot
    forecast_plots(predictions, output)
    validation_plot(validation, output)
    print(json.dumps({'output': str(output), 'forecast_rows': len(predictions),
                      'daily_rows': len(daily), 'history_metrics_rows': len(historical),
                      'validation_candidates': len(validation),
                      'rain_methods': {s: m['rain']['method'] for s, m in models.items()}}, indent=2), flush=True)


def verify_lock(output):
    lock = json.loads((output / 'benchmark_lock.json').read_text())
    for name, checksum in lock['immutable_files'].items():
        if digest(output / name) != checksum:
            raise ValueError('Locked benchmark file changed: ' + name)
    return lock


def lock(output):
    if (output / 'benchmark_lock.json').exists():
        verify_lock(output)
        print('Existing lock verified; no files rewritten.')
        return
    required = ['models.json', 'frozen_predictions.json', 'frozen_forecasts.csv', 'daily_forecasts.csv',
                'forecast_windows.csv', 'protocol.json', 'training_audit.json', 'input_checksums.json',
                'historical_gfs_accuracy.csv', 'validation_candidates.csv', 'station_quality.json', 'baseline_report.md', 'verification.json', 'gfs_archive_coverage.csv']
    for name in required:
        if not (output / name).exists():
            raise ValueError('Cannot lock incomplete benchmark: ' + name)
    archived = output / 'frozen_source'
    archived.mkdir(exist_ok=True)
    for path in sorted((ROOT / 'engine_v2').glob('*')):
        if path.suffix in ('.py', '.json', '.md'):
            shutil.copyfile(path, archived / path.name)
    required.extend(str(p.relative_to(output)).replace('\\', '/') for p in sorted(archived.iterdir()))
    required.extend(p.name for p in sorted(output.glob('*.png')))
    required.extend(str(p.relative_to(output)).replace('\\', '/') for p in sorted((output / 'history').glob('*.csv')))
    if (output / 'source_inventory.json').exists():
        required.append('source_inventory.json')
    value = {'locked_at_utc': utc_now(), 'benchmark_start_wib': FREEZE.isoformat(),
             'benchmark_end_exclusive_wib': (FREEZE + dt.timedelta(days=7)).isoformat(),
             'blinded_actuals': True, 'immutable_files': {name: digest(output / name) for name in required}}
    save_json(output / 'benchmark_lock.json', value)
    verify_lock(output)
    archive = output.parent / 'engine_v2_frozen_benchmark_20261103.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                bundle.write(path, 'benchmark_20261103/' + str(path.relative_to(output)))
    print(json.dumps({'lock': str(output / 'benchmark_lock.json'), 'files': len(required),
                      'model_sha256': value['immutable_files']['models.json'], 'archive': str(archive)}, indent=2))


def score(source_root, output, device_map=None):
    verify_lock(output)
    package = json.loads((output / 'frozen_predictions.json').read_text())
    models = json.loads((output / 'models.json').read_text())['models']
    config = copy.deepcopy(package['stations'])
    if device_map:
        for station, device in json.loads(device_map.read_text()).items():
            config[station]['expected_device_id'] = device
    observations, normalization = prepare_all(source_root, config=config)
    score_time = dt.datetime.now(UTC)
    directory = output.parent / ('scores_' + score_time.strftime('%Y%m%dT%H%M%SZ'))
    directory.mkdir(exist_ok=False)
    scores, comparisons, windows = [], [], []
    for station in config:
        group = sorted((r for r in package['predictions'] if r['station'] == station), key=lambda r: r['time'])
        for variable, (key, _) in VARIABLE_KEYS.items():
            paired = []
            for row in group:
                obs = observations[station].get(row['time'], {})
                actual = obs.get(key)
                if obs.get(key + '_observed_at', float('inf')) > score_time.timestamp():
                    actual = None
                comparisons.append({'station': station, 'variable': variable, 'interval_end_wib': wib(row['time']),
                                    'raw_gfs': row['forecast_' + key], 'engine_v2': row['v2_' + key],
                                    'actual': actual, 'status': 'matched' if actual is not None else 'missing_actual'})
                if actual is not None:
                    paired.append({**row, 'raw': row['forecast_' + key], 'observed': actual})
            for model in ('raw_gfs', 'engine_v2'):
                predicted = [r['raw'] if model == 'raw_gfs' else r['v2_' + key] for r in paired]
                scores.append({'station': station, 'variable': variable, 'model': model,
                               'expected_hours': 168, **metrics(paired, predicted, rain=variable == 'rain')})
        for horizon in (1, 6, 12, 24):
            valid_windows, raw_predictions, corrected_predictions = [], [], []
            for i in range(len(group) - horizon + 1):
                window = group[i:i + horizon]
                actuals = [observations[station].get(r['time'], {}).get('rain') for r in window]
                arrival = [observations[station].get(r['time'], {}).get('rain_observed_at', float('inf')) for r in window]
                if any(a is None for a in actuals) or max(arrival) > score_time.timestamp():
                    continue
                valid_windows.append({'raw': sum(r['forecast_rain'] for r in window), 'observed': sum(actuals)})
                raw_predictions.append(valid_windows[-1]['raw'])
                corrected_predictions.append(sum(r['v2_rain'] for r in window))
            for model, predictions in [('raw_gfs', raw_predictions), ('engine_v2', corrected_predictions)]:
                windows.append({'station': station, 'hours': horizon, 'model': model,
                                'expected_overlapping_windows': 169 - horizon, **metrics(valid_windows, predictions, rain=True)})
        probability_pairs = []
        for row in group:
            obs = observations[station].get(row['time'], {})
            if row['rain_probability'] is not None and obs.get('rain') is not None and obs.get('rain_observed_at', float('inf')) <= score_time.timestamp():
                probability_pairs.append((row['rain_probability'], obs['rain'] >= TIP_MM - 1e-9))
        brier = statistics.mean((p - y) ** 2 for p, y in probability_pairs) if probability_pairs else None
        clim = models[station].get('rain_climatology_probability')
        clim_brier = statistics.mean((clim - y) ** 2 for _, y in probability_pairs) if probability_pairs and clim is not None else None
        scores.append({'station': station, 'variable': 'rain_probability', 'model': 'engine_v2',
                       'expected_hours': 168, 'n': len(probability_pairs), 'brier': brier, 'climatology_brier': clim_brier})
    write_csv(directory / 'weekly_accuracy.csv', scores)
    write_csv(directory / 'rain_window_accuracy.csv', windows)
    write_csv(directory / 'hourly_comparison.csv', comparisons)
    save_json(directory / 'scoring_provenance.json', {'scored_at_utc': score_time.isoformat(),
        'frozen_model_sha256': digest(output / 'models.json'), 'frozen_predictions_sha256': digest(output / 'frozen_predictions.json'),
        'normalization': normalization, 'model_refitted': False})
    from plots import forecast_plots
    forecast_plots(package['predictions'], directory, observations)
    lines = ['# Blind weekly benchmark accuracy', '', 'Frozen forecast: 3–9 November 2026, WIB. Models were not refitted. Missing hours remain missing.', '',
             '| Station | Variable | Model | Matched hours / 168 | MAE | RMSE | Bias |', '| --- | --- | --- | ---: | ---: | ---: | ---: |']
    for row in scores:
        if row['variable'] != 'rain_probability':
            lines.append(f"| {row['station']} | {row['variable']} | {row['model']} | {row['n']} | {display(row.get('mae'))} | {display(row.get('rmse'))} | {display(row.get('bias'))} |")
    lines += ['', 'Temperature is in °C, humidity errors in percentage points, rainfall in mm per hour. Rain-window results use overlapping windows and are not independent storm counts. Inspect hits, misses and false alarms alongside amount errors.', '']
    for station in config:
        lines += [f'![{station}: forecast versus measured](forecast_{station}.png)', '']
    (directory / 'weekly_accuracy_report.md').write_text('\n'.join(lines), encoding='utf-8')
    verify_lock(output)
    print(json.dumps({'scoring_output': str(directory), 'matched_hourly_measurements': sum(r['n'] for r in scores if r['model'] == 'raw_gfs'), 'refitted': False}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'lock', 'score', 'verify'))
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--device-map', type=Path)
    args = parser.parse_args()
    if args.action in ('build', 'score') and args.source_root is None:
        parser.error('--source-root is required')
    if args.action == 'build':
        build(args.source_root, args.output)
    elif args.action == 'lock':
        lock(args.output)
    elif args.action == 'score':
        score(args.source_root, args.output, args.device_map)
    else:
        result = verify_lock(args.output)
        print(json.dumps({'verified': True, 'immutable_files': len(result['immutable_files'])}))
