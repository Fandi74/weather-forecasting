import csv
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'engine_v2'))
from core import attach_observations, daily_run_rows, fit_rain, metrics, rain_predict, target_day
from observations import load_station, prepare_hours, quality


class EngineV2Tests(unittest.TestCase):
    def test_auxiliary_errors_do_not_invalidate_bme_or_rain(self):
        row = {'t': '20', 'h': '80', 'rf': '0', 'rfc': '7', 'error': 'E3 E8 E11 E12'}
        parsed = quality(row)
        self.assertEqual((parsed['t'], parsed['h'], parsed['rain_ok']), (20, 80, True))
        self.assertIsNone(quality({**row, 'error': 'E2'})['t'])
        self.assertFalse(quality({**row, 'error': 'E4'})['rain_ok'])
        self.assertEqual(quality({**row, 'error': 'E4'})['t'], 20)

    def test_unknown_sensor_error_is_exposed_and_excluded(self):
        parsed = quality({'t': '20', 'h': '80', 'rf': '0', 'rfc': '7', 'error': 'E99'})
        self.assertIsNone(parsed['t'])
        self.assertFalse(parsed['rain_ok'])
        self.assertEqual(parsed['unknown_codes'], ['E99'])

    def test_rain_requires_six_valid_intervals(self):
        records = [{'ms': int((i * 600 + 9) * 1000), 't': 20.0, 'h': 80.0,
                    'rf': 0.28 if i else 0, 'rfc': i, 'rain_ok': True,
                    'unknown_codes': []} for i in range(7)]
        complete, _ = prepare_hours(records)
        self.assertAlmostEqual(complete[3600]['rain'], 1.68)
        gap, _ = prepare_hours(records[:3] + records[4:])
        self.assertNotIn('rain', gap.get(3600, {}))
        reset, _ = prepare_hours(records[:-1] + [{**records[-1], 'rfc': 0}])
        self.assertNotIn('rain', reset.get(3600, {}))

    def test_temperature_is_matched_at_instant_not_hour_average(self):
        records = [{'ms': 9000, 't': 21.0, 'h': 80.0, 'rf': 0, 'rfc': 0, 'rain_ok': True, 'unknown_codes': []},
                   {'ms': 609000, 't': 40.0, 'h': 30.0, 'rf': 0, 'rfc': 0, 'rain_ok': True, 'unknown_codes': []}]
        hourly, _ = prepare_hours(records)
        self.assertEqual(hourly[0]['t'], 21.0)
        self.assertEqual(hourly[0]['t_offset_seconds'], 9.0)

    def test_training_excludes_late_arrivals_and_cutoff_targets(self):
        forecasts = [{'station': 'X', 'time': t, 'forecast_t': 20} for t in (100, 200, 300)]
        observations = {'X': {100: {'t': 21, 't_observed_at': 100, 't_available_at': 150},
                              200: {'t': 22, 't_observed_at': 200, 't_available_at': 310},
                              300: {'t': 99, 't_observed_at': 300, 't_available_at': 300}}}
        paired = list(attach_observations(forecasts, observations, 'temperature', 300))
        self.assertEqual([r['time'] for r in paired], [100])

    def test_future_rain_interval_uses_end_timestamp(self):
        issue = 100000
        times = [issue + h * 3600 for h in range(169)]
        payload = [{'hourly': {'time': times, 'temperature_2m': list(range(169)),
                              'relative_humidity_2m': [80] * 169, 'precipitation': list(range(169))}}]
        rows = list(daily_run_rows(payload, ['X'], issue))
        self.assertEqual(len(rows), 168)
        self.assertEqual(rows[0]['forecast_rain'], 1)
        self.assertEqual(rows[-1]['forecast_rain'], 168)
        self.assertEqual([target_day(x) for x in (1, 24, 25, 168)], [1, 1, 2, 7])

    def test_duplicate_device_is_not_a_second_station(self):
        scratch = Path(__file__).resolve().parents[1] / 'data/engine_v2/test_temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            base = Path(folder)
            self.assertTrue(base.resolve().is_relative_to(scratch.resolve()))
            (base / 'X67').mkdir()
            path = base / 'X67/export.csv'
            path.write_text('device_id,timestamp_ms,t,h,rf,rfc\nX66-device,1000,20,80,0,0\n')
            config = {'X66': {'expected_device_id': 'X66-device'}, 'X67': {'expected_device_id': None}}
            records, _, issues = load_station('X67', config['X67'], base, config)
            self.assertEqual(records, [])
            self.assertEqual(issues[0]['reason'], 'device_belongs_to_another_station')

    def test_empty_scores_are_missing_not_perfect(self):
        scores = metrics([])
        self.assertEqual(scores['n'], 0)
        self.assertIsNone(scores['mae'])

    def test_nonnegative_rain_slope_is_fitted_without_legacy_shrinkage(self):
        rows = [{'raw': 1, 'observed': 2}, {'raw': 2, 'observed': 4}]
        model = fit_rain(rows, 'nonnegative_slope')
        self.assertAlmostEqual(model['slope'], 2)
        self.assertEqual(rain_predict(rows, model), [2, 4])
        scores = metrics(rows, [2, 4], rain=True)
        self.assertEqual(scores['rmse'], 0)

    def test_scoring_verifies_frozen_files_and_never_refits(self):
        from run import build, digest, save_json, score, verify_lock
        from collect import FREEZE
        scratch = Path(__file__).resolve().parents[1] / 'data/engine_v2/test_temp'
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            base = Path(folder)
            self.assertTrue(base.resolve().is_relative_to(scratch.resolve()))
            output = base / 'benchmark'
            output.mkdir()
            end = int(FREEZE.timestamp()) + 3600
            prediction = {'station': 'X', 'time': end, 'day': 1, 'forecast_t': 20, 'forecast_h': 80,
                          'forecast_rain': 0, 'v2_t': 20, 'v2_h': 80, 'v2_rain': 0,
                          'rain_probability': None}
            save_json(output / 'frozen_predictions.json', {'stations': {'X': {'expected_device_id': 'X-device'}}, 'predictions': [prediction]})
            save_json(output / 'models.json', {'models': {'X': {'rain_climatology_probability': 0.1}}})
            hashes = {name: digest(output / name) for name in ('models.json', 'frozen_predictions.json')}
            save_json(output / 'benchmark_lock.json', {'immutable_files': hashes})
            actual = {'t': 20, 'h': 80, 'rain': 0, 't_observed_at': end,
                      'h_observed_at': end, 'rain_observed_at': end}
            with patch('run.prepare_all', return_value=({'X': {end: actual}}, {})), \
                    patch('run.fit_models', side_effect=AssertionError('Scoring must not refit')), \
                    patch('plots.forecast_plots'):
                score(base, output)
            self.assertEqual({name: digest(output / name) for name in hashes}, hashes)
            report = next(base.glob('scores_*/weekly_accuracy.csv'))
            with report.open(encoding='utf-8-sig') as stream:
                scored = list(csv.DictReader(stream))
            raw_temperature = next(r for r in scored if r['model'] == 'raw_gfs' and r['variable'] == 'temperature')
            self.assertEqual(int(raw_temperature['n']), 1)
            self.assertEqual(float(raw_temperature['mae']), 0)
            with patch('run.prepare_all', side_effect=AssertionError('A locked build must not read new training data')):
                with self.assertRaisesRegex(ValueError, 'Benchmark is locked'):
                    build(base, output)
            (output / 'models.json').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'Locked benchmark file changed'):
                verify_lock(output)


if __name__ == '__main__':
    unittest.main()
