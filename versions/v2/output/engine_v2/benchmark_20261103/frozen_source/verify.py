"""Validate the actual experiment files before sealing the blind benchmark."""
import collections
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import statistics
import urllib.parse
import sys
import numpy as np

from collect import DATA, FREEZE, ROOT, UTC, WIB, utc_now
from run import DEFAULT_OUTPUT, digest, save_json


def verify(output=DEFAULT_OUTPUT):
    package = json.loads((output / 'frozen_predictions.json').read_text())
    models = json.loads((output / 'models.json').read_text())
    source_manifest = json.loads((DATA / 'manifest.json').read_text())
    checks = []
    assert source_manifest['history_complete']
    assert len(source_manifest['history_chunks']) == 13
    assert len(source_manifest['weekly_samples']) == 30
    annual_coverage = collections.Counter()
    for entry in source_manifest['history_chunks']:
        path = DATA / entry['file']
        envelope = json.loads(path.read_text())
        query = urllib.parse.parse_qs(urllib.parse.urlparse(envelope['request_url']).query)
        assert query['models'] == ['gfs_seamless']
        assert query['end_date'][0] <= '2026-11-02'
        for station, slot in zip(package['stations'], envelope['payload']):
            times = slot['hourly']['time']
            assert max(times) < FREEZE.timestamp()
            assert all(b - a == 3600 for a, b in zip(times, times[1:]))
            annual_coverage[station] += len(times)
    assert all(n == 8760 for n in annual_coverage.values())
    checks.append('One complete year, 8760 targets per location; only explicit GFS; history ends before cutoff')
    raw_paths = [DATA / r['file'] for r in source_manifest['weekly_samples']] + [DATA / source_manifest['frozen']['file']]
    for path in raw_paths:
        envelope = json.loads(path.read_text())
        query = urllib.parse.parse_qs(urllib.parse.urlparse(envelope['request_url']).query)
        assert query['models'] == ['gfs_seamless']
        initialized = dt.datetime.fromisoformat(query['run'][0]).replace(tzinfo=UTC)
        assert initialized + dt.timedelta(hours=6) <= FREEZE.astimezone(UTC)
    assert source_manifest['frozen_run_initialized_utc'] == '2026-11-02T06:00:00+00:00'
    checks.append('All individual GFS runs initialized before freeze; no 3/4/5 November update')
    for variable, stations in models['training_audit'].items():
        for station, audit in stations.items():
            for field in ('latest_target_wib', 'latest_observation_available_wib'):
                if audit[field]:
                    assert dt.datetime.fromisoformat(audit[field]) < FREEZE
    checks.append('Every fitted target and assumed observation arrival precedes benchmark start')
    predictions = package['predictions']
    assert len(predictions) == 672
    for station in package['stations']:
        group = sorted((r for r in predictions if r['station'] == station), key=lambda r: r['time'])
        assert [r['time'] for r in group] == list(range(int(FREEZE.timestamp()) + 3600, int(FREEZE.timestamp()) + 169 * 3600, 3600))
        for row in group:
            assert all(math.isfinite(row[k]) for k in ('forecast_t', 'forecast_h', 'forecast_rain', 'v2_t', 'v2_h', 'v2_rain'))
            assert 0 <= row['v2_h'] <= 100 and row['v2_rain'] >= 0
            assert row['rain_probability'] is None or 0 <= row['rain_probability'] <= 1
        if station in ('X51', 'X67'):
            assert all(r['v2_' + k] == r['forecast_' + k] for r in group for k in ('t', 'h', 'rain'))
            assert all(r['rain_probability'] is None for r in group)
    checks.append('672 finite forecast intervals, correct endpoints/bounds; X51/X67 use raw fallback')
    exported = list(csv.DictReader((output / 'frozen_forecasts.csv').open(encoding='utf-8-sig')))
    assert len(exported) == 672
    assert all(r['interval_end_wib'] == r['temperature_humidity_valid_at_wib'] for r in exported)
    for csv_row, row in zip(exported, predictions):
        assert csv_row['station'] == row['station']
        for column, key in [('engine_v2_rain_mm', 'v2_rain'), ('engine_v2_temperature_c', 'v2_t'), ('engine_v2_humidity_pct', 'v2_h')]:
            assert abs(float(csv_row[column]) - row[key]) <= 0.00000051
    daily = list(csv.DictReader((output / 'daily_forecasts.csv').open(encoding='utf-8-sig')))
    assert len(daily) == 28
    for station in package['stations']:
        group = [r for r in predictions if r['station'] == station]
        summary = [r for r in daily if r['station'] == station]
        assert len(summary) == 7 and all(int(r['hours']) == 24 for r in summary)
        for column, key in [('raw_gfs_rain_mm', 'forecast_rain'), ('engine_v2_rain_mm', 'v2_rain')]:
            assert math.isclose(sum(float(r[column]) for r in summary), sum(r[key] for r in group), rel_tol=1e-10, abs_tol=1e-8)
    windows = list(csv.DictReader((output / 'forecast_windows.csv').open(encoding='utf-8-sig')))
    assert len(windows) == 16
    assert all(not r['engine_v2_rain_probability_pct'] for r in windows if int(r['hours']) > 1)
    checks.append('CSV values reconcile with frozen JSON; 28 daily totals and 16 horizon summaries reconcile')
    for station in package['stations']:
        path = output / f'history/GFS_{station}_20251103_20261102.csv'
        with path.open(encoding='utf-8-sig') as stream:
            history_table = list(csv.DictReader(stream))
        assert len(history_table) == 8760
        assert history_table[0]['target_time_wib'] == '2025-11-03T00:00:00+07:00'
        assert history_table[-1]['target_time_wib'] == '2026-11-02T23:00:00+07:00'
        assert len([k for k in history_table[0] if '_previous_day' in k]) == 21
    checks.append('Four full-year CSV tables preserve 8760 hourly targets and 21 forecast series each')
    observed = {s: {r['time']: r for r in json.loads((ROOT / f'data/engine_v2/observations/{s}_hourly.json').read_text())} for s in package['stations']}
    assert all(t < FREEZE.timestamp() for site in observed.values() for t in site)
    historical = list(csv.DictReader((output / 'historical_gfs_accuracy.csv').open(encoding='utf-8-sig')))
    assert len(historical) == 84
    # Independent arithmetic check of one report headline using archived values.
    differences = []
    for chunk in source_manifest['history_chunks']:
        slot = json.loads((DATA / chunk['file']).read_text())['payload'][0]
        for timestamp, forecast in zip(slot['hourly']['time'], slot['hourly']['temperature_2m_previous_day1']):
            obs = observed['X50'].get(timestamp, {})
            if 't' in obs and obs['t_available_at'] < FREEZE.timestamp():
                differences.append(forecast - obs['t'])
    headline = next(r for r in historical if r['station'] == 'X50' and r['variable'] == 'temperature' and r['fixed_lead_days'] == '1')
    assert int(headline['n']) == len(differences)
    assert math.isclose(float(headline['mae']), statistics.mean(abs(e) for e in differences), abs_tol=1e-10)
    assert math.isclose(float(headline['rmse']), math.sqrt(statistics.mean(e * e for e in differences)), abs_tol=1e-10)
    checks.append('Blinded actuals absent; historical headline error independently reconciled')
    hashes = json.loads((output / 'input_checksums.json').read_text())
    for path, checksum in {**hashes['forecast_files'], **hashes['station_files']}.items():
        p = Path(path)
        p = p if p.is_absolute() else ROOT / p
        assert digest(p) == checksum
    checks.append('All archived forecast and accepted original station checksums verified')
    report = (output / 'baseline_report.md').read_text(encoding='utf-8')
    assert 'X66 reference discrepancy' in report
    assert 'Weekly accuracy is pending' in report
    for station in package['stations']:
        assert (output / f'forecast_{station}.png').stat().st_size > 1000
    assert (output / 'validation.png').stat().st_size > 1000
    checks.append('Report preserves reference warning and pending benchmark status; all plot artifacts present')
    result = {'verified_at_utc': utc_now(), 'checks': checks, 'passed': True,
              'forecast_rows': 672, 'annual_hours_per_location': dict(annual_coverage),
              'model_sha256': digest(output / 'models.json'), 'predictions_sha256': digest(output / 'frozen_predictions.json')}
    result['python_version'] = sys.version
    result['numpy_version'] = np.__version__
    if (output / 'benchmark_lock.json').exists():
        from run import verify_lock
        verify_lock(output)
        result['existing_lock_verified_without_rewriting_files'] = True
    else:
        save_json(output / 'verification.json', result)
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    verify()
