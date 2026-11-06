import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

VERSION_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(VERSION_DIR))

from weather_catboost.common import FREEZE, VALIDATION_START, row_signature
from weather_catboost.experiment import build, probability_metrics, train_audit
from weather_catboost.features import HistoryBuilder, feature_values
from weather_catboost import learner


def point(hour, value=20, rain=0.28, available=None):
    t = hour * 3600
    r = {'time': t}
    for key, val in (('t', value), ('h', 80), ('rain', rain)):
        r[key] = val
        r[key + '_observed_at'] = t
        r[key + '_available_at'] = t + 3600 if available is None else available
    return r


class CandidateTests(unittest.TestCase):
    def test_future_or_unreceived_observation_cannot_change_features(self):
        issue = 10 * 3600
        early, unavailable = point(8), point(9, value=999, available=issue + 1)
        obs = {'X': {r['time']: r for r in (early, unavailable, point(11, value=888))}}
        before = HistoryBuilder(obs, []).get('X', issue)
        unavailable['t'] = -999
        after = HistoryBuilder(obs, []).get('X', issue)
        self.assertEqual(before, after)
        self.assertEqual(before['t_latest'], 20)

    def test_missing_rain_hour_is_not_zero(self):
        obs = {'X': {p['time']: p for p in (point(7), point(9))}}
        features = HistoryBuilder(obs, []).get('X', 10 * 3600)
        self.assertIsNone(features['rain_3h_value'])
        self.assertAlmostEqual(features['rain_3h_coverage'], 2 / 3)

    def test_stale_station_is_masked_and_age_remains(self):
        features = HistoryBuilder({'X': {3600: point(1)}}, []).get('X', 10 * 3600)
        self.assertIsNone(features['t_latest'])
        self.assertEqual(features['t_age_hours'], 9)
        self.assertEqual(features['t_3h_coverage'], 0)

    def test_errors_use_previously_issued_forecasts_only(self):
        issue = 10 * 3600
        obs = {'X': {8 * 3600: point(8, value=20)}}
        old = {'station': 'X', 'issue': 0, 'time': 8 * 3600, 'forecast_t': 18, 'forecast_h': 70, 'forecast_rain': 0}
        future = {**old, 'issue': issue + 1, 'forecast_t': -999}
        builder = HistoryBuilder(obs, [old, future])
        features = builder.get('X', issue)
        self.assertEqual(features['t_error_3h'], 2)
        self.assertLess(builder.audit[0]['max_prior_forecast_issue'], issue)
        self.assertLessEqual(builder.audit[0]['max_observation_available_at'], issue)

    def test_proxy_issue_is_rejected_for_history(self):
        with self.assertRaisesRegex(ValueError, 'exact issue'):
            HistoryBuilder({}, []).get('X', None)

    def test_entire_week_uses_same_initial_context(self):
        builder = HistoryBuilder({'X': {8 * 3600: point(8)}}, [])
        row = {'station': 'X', 'issue': 10 * 3600, 'hour': 11, 'day': 1,
               'forecast_t': 20, 'forecast_h': 80, 'forecast_rain': 0}
        a = feature_values(row, 'catboost_history_exact', builder)
        b = feature_values({**row, 'day': 7, 'hour': 10}, 'catboost_history_exact', builder)
        self.assertEqual(a['t_latest'], b['t_latest'])
        self.assertEqual(len(builder.audit), 1)

    def test_training_enforces_label_arrival_and_known_issue(self):
        row = {'station': 'X', 'time': VALIDATION_START - 7200, 'issue': VALIDATION_START - 86400,
               'day': 1, 'observation_measured_at': VALIDATION_START - 7191,
               'observation_available_at': VALIDATION_START}
        with self.assertRaisesRegex(ValueError, 'crosses cutoff'):
            train_audit('X', 'temperature', 'catboost_base_exact', 'validation', [row], VALIDATION_START)

    def test_locked_candidate_cannot_read_or_refit_inputs(self):
        scratch = VERSION_DIR / '.tmp'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            output = Path(folder)
            (output / 'candidate_lock.json').write_text('{}')
            with patch('weather_catboost.experiment.load_inputs', side_effect=AssertionError('Must not read inputs')):
                with self.assertRaisesRegex(ValueError, 'locked'):
                    build(output, output)

    def test_probability_missing_is_unavailable(self):
        self.assertEqual(probability_metrics([{'observed': 0}], [None])['n'], 0)
        self.assertIsNone(probability_metrics([], [])['brier'])
        self.assertAlmostEqual(probability_metrics([{'observed': 0.28}], [0.8])['brier'], 0.04)

    def test_mixed_proxy_and_exact_row_fingerprint(self):
        rows = [{'station': 'X', 'time': 100, 'issue': None, 'day': 1},
                {'station': 'X', 'time': 100, 'issue': 0, 'day': 2}]
        self.assertEqual(row_signature(rows), row_signature(list(reversed(rows))))

    def test_catboost_models_reload_and_humidity_is_bounded(self):
        scratch = VERSION_DIR / '.tmp'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            output = Path(folder)
            rows = [{'station': 'X', 'issue': 0, 'time': (i + 1) * 3600, 'day': 1,
                     'hour': i % 24, 'forecast_t': 20 + i % 5, 'forecast_h': 80,
                     'forecast_rain': i % 3 / 10, 'raw': 80,
                     'observed': 82 + math.sin(i)} for i in range(60)]
            descriptor = learner.fit(rows, 'catboost_base_full', 'humidity', None, output / 'model', output)
            values, _ = learner.predict(descriptor, rows, None, output)
            learner.MODEL_CACHE.clear()
            reloaded, _ = learner.predict(descriptor, rows, None, output)
            self.assertEqual(values, reloaded)
            outside, _ = learner.predict(descriptor, [{**rows[0], 'raw': 150}], None, output)
            self.assertEqual(outside, [100])

    def test_frozen_file_tampering_is_detected(self):
        from weather_catboost.common import digest, verify_files
        scratch = VERSION_DIR / '.tmp'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            file = root / 'model.cbm'
            file.write_bytes(b'original')
            hashes = {'model.cbm': digest(file)}
            verify_files(root, hashes)
            file.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Immutable file mismatch'):
                verify_files(root, hashes)

    def test_scoring_uses_saved_predictions_and_never_fits(self):
        from types import SimpleNamespace
        from weather_catboost.common import VARIANTS, WORKSPACE, read_json, save_json
        from weather_catboost.scoring import score
        from weather_catboost.data import locate_baseline
        sys.path.insert(0, str(locate_baseline(WORKSPACE) / 'engine_v2'))
        import observations
        scratch = VERSION_DIR / '.tmp'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            root = Path(folder)
            output = root / 'candidate'
            output.mkdir()
            prediction = {'station': 'X', 'time': FREEZE + 3600,
                          'interval_end_wib': '2026-11-03T01:00:00+07:00'}
            for name in ('raw', 'v2') + VARIANTS + ('selected',):
                prediction.update({name + '_t': 20, name + '_h': 80, name + '_rain': 0.28,
                                   name + '_rain_probability': 0.7})
            save_json(output / 'frozen_predictions.json', {'stations': {'X': {}}, 'predictions': [prediction]})
            save_json(output / 'candidate_lock.json', {})
            before = (output / 'frozen_predictions.json').read_bytes()
            actual = {'t': 20, 'h': 80, 'rain': 0.28, 't_observed_at': FREEZE + 3600,
                      'h_observed_at': FREEZE + 3600, 'rain_observed_at': FREEZE + 3600}
            def metric(rows, values, rain=False):
                return {'n': len(rows), 'mae': sum(abs(p - r['observed']) for r, p in zip(rows, values)) / len(rows) if rows else None}
            with patch('weather_catboost.scoring.verify', return_value={}) as validation, \
                    patch('weather_catboost.scoring.baseline_context', return_value={'core': SimpleNamespace(metrics=metric)}), \
                    patch.object(observations, 'prepare_all', return_value=({'X': {FREEZE + 3600: actual}}, {})), \
                    patch('weather_catboost.learner.fit', side_effect=AssertionError('Scoring must never fit')), \
                    patch('weather_catboost.experiment.load_inputs', side_effect=AssertionError('Scoring must not read training data')):
                result = score(WORKSPACE, output, root)
            self.assertFalse(result['model_refitted'])
            self.assertEqual(result['matched_station_variable_hours'], 3)
            self.assertEqual((output / 'frozen_predictions.json').read_bytes(), before)
            self.assertEqual(validation.call_count, 2)
            self.assertTrue(all(call.kwargs['require_lock'] for call in validation.call_args_list))


if __name__ == '__main__':
    unittest.main()
