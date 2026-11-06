"""Build, verify and score the humidity-only V5 candidate locally."""
import argparse
import csv
import datetime as dt
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

from common import (BASE_TRAIN_END, DEFAULT_OUTPUT, FREEZE, VERSION_DIR, WIB, WORKSPACE,
                    digest, locate, metrics, no_overwrite, read_json, save_json, verify_references, wib, write_csv)
from data import load_inputs
from ensemble import FAMILIES, eligible_calibration, fit, predict
from features import FEATURES, History, vector


def fingerprint(rows):
    import json
    data = [[r['issue'], r['time'], r['observed'], r['observed_at'], r['available_at']] for r in rows]
    return hashlib.sha256(json.dumps(data, separators=(',', ':')).encode()).hexdigest()


def worker(data, history, train, predict_rows, stage, algorithm, python, output):
    cutoff = BASE_TRAIN_END if stage == 'validation' else FREEZE
    if any(max(r['time'], r['available_at'], r['observed_at']) >= cutoff for r in train):
        raise ValueError('Humidity training label crosses cutoff')
    model_dir = output / 'models' / stage / algorithm
    model = model_dir / ('humidity.cbm' if algorithm == 'catboost' else 'humidity.txt')
    job = {'algorithm': algorithm, 'target': 'hsht_humidity_residual', 'feature_names': FEATURES,
        'train_x': [vector(r, history) for r in train], 'train_y_residual': [r['observed'] - r['forecast_h'] for r in train],
        'predict_x': [vector(r, history) for r in predict_rows], 'raw_predict': [r['forecast_h'] for r in predict_rows],
        'model_path': str(model), 'result_path': str(model_dir / 'predictions.json')}
    job_path = output / 'jobs' / (stage + '_' + algorithm + '.json')
    save_json(job_path, job)
    print(f'{stage}: {algorithm}, humidity only, {len(train)} training rows / {len(predict_rows)} predictions', flush=True)
    subprocess.run([str(python), str(VERSION_DIR / 'worker.py'), str(job_path)], check=True)
    result = read_json(model_dir / 'predictions.json')
    if len(result['predictions']) != len(predict_rows):
        raise ValueError('Worker prediction count mismatch')
    audit = {'stage': stage, 'algorithm': algorithm, 'target': 'hsht', 'training_rows': len(train),
        'unique_target_hours': len({r['time'] for r in train}), 'label_signature': fingerprint(train),
        'cutoff_exclusive_wib': wib(cutoff), 'latest_label_available_wib': wib(max(r['available_at'] for r in train)),
        'model_path': model.relative_to(output).as_posix(), 'job_sha256': digest(job_path),
        'package_version': result['package_version'], 'parameters': result['parameters']}
    return result['predictions'], audit


def walk_forward(rows, protocol):
    forecasts, audit, scores = [], [], []
    issues = [dt.datetime.fromisoformat(s).timestamp() for s in protocol['ensemble_folds']]
    for issue in issues:
        train = eligible_calibration(rows, issue)
        val = [r for r in rows if r['issue'] == issue]
        if min(len(train), len(val)) < 48:
            raise ValueError('Insufficient chronological calibration/validation rows')
        for family in FAMILIES:
            model = fit(train, family)
            values = predict(model, val)
            audit.append({'issue_wib': wib(issue), 'family': family, 'model': model,
                'calibration_rows': len(train), 'validation_rows': len(val),
                'max_calibration_label_available_wib': wib(max(r['available_at'] for r in train))})
            scores.append({'scope': wib(issue), 'family': family, **metrics([r['observed'] for r in val], values)})
            forecasts += [{'family': family, 'issue': issue, 'time': r['time'], 'actual_hsht': r['observed'], 'prediction': value}
                          for r, value in zip(val, values)]
    combined = []
    for family in FAMILIES:
        sample = [r for r in forecasts if r['family'] == family]
        combined.append({'scope': 'combined_later_october', 'family': family,
                         **metrics([r['actual_hsht'] for r in sample], [r['prediction'] for r in sample])})
    baseline = next(r for r in combined if r['family'] == 'v2')
    best = min(combined, key=lambda r: (r['mae'], FAMILIES.index(r['family'])))
    accepted = best['family'] != 'v2' and baseline['mae'] - best['mae'] >= protocol['minimum_mae_improvement_pp_to_replace_v2']
    selected = best['family'] if accepted else 'v2'
    selection = {'family': selected, 'best_development_family': best['family'], 'accepted_humidity_update': accepted,
        'baseline_mae': baseline['mae'], 'best_mae': best['mae'], 'improvement_pp': baseline['mae'] - best['mae'],
        'selection_metric': 'MAE', 'selection_status': 'October development validation; November actuals excluded',
        'model': fit(rows, selected)}
    return selection, scores + combined, forecasts, audit


def preserve_components(originals, previous, humidity, selection):
    predictions = []
    for old in originals:
        station, time = old['station'], old['time']
        updated = humidity.get(time) if station == 'X66' else None
        row = {'station': station, 'time': time, 'issue': old['issue'], 'day': old['day'],
            'interval_start_wib': wib(time - 3600), 'interval_end_wib': wib(time),
            'selected_t': old['v2_t'], 'selected_rain': old['v2_rain'], 'selected_rain_probability': old['rain_probability'],
            'temperature_method': 'unchanged_engine_v2', 'rain_method': 'unchanged_engine_v2',
            'rain_probability_method': 'unchanged_engine_v2', 'v2_h': old['v2_h'],
            'v3_h': previous['V3'][station, time]['selected_h'], 'v4_h': previous['V4'][station, time]['selected_h'],
            'selected_h': updated['selected_h'] if updated else old['v2_h'],
            'humidity_method': selection['family'] if updated else 'retained_v2_no_independent_hsht_support'}
        if updated:
            row.update(catboost_hsht_h=updated['catboost_hsht_h'], lightgbm_hsht_h=updated['lightgbm_hsht_h'])
        predictions.append(row)
    return predictions


def check_passthrough(predictions, originals):
    old = {(r['station'], r['time']): r for r in originals}
    if len(predictions) != 672 or len(old) != 672:
        raise ValueError('Expected 168 forecast hours at each of four stations')
    for row in predictions:
        reference = old[row['station'], row['time']]
        for key, original in [('selected_t', 'v2_t'), ('selected_rain', 'v2_rain'), ('selected_rain_probability', 'rain_probability')]:
            if row[key] != reference[original]:
                raise ValueError('V5 changed a protected V2 component: ' + key)
        if not 0 <= row['selected_h'] <= 100:
            raise ValueError('Humidity outside [0,100]')
    return len(predictions)


def build(output, catboost_python, lightgbm_python):
    output = Path(output).resolve()
    no_overwrite(output)
    before = verify_references()
    protocol = read_json(VERSION_DIR / 'protocol.json')
    data = load_inputs()
    output.mkdir(parents=True, exist_ok=True)
    save_json(output / 'protocol.json', protocol)
    save_json(output / 'reference_locks.json', before)
    save_json(output / 'station_support.json', data['support'])
    history = History(data['observations'], data['exact'])
    validation = [dict(r) for r in data['validation']]
    final_rows = [dict(r) for r in data['frozen']]
    roots = locate()
    originals = read_json(roots['V2'][0] / 'frozen_predictions.json')['predictions']
    original_index = {(r['station'], r['time']): r for r in originals}
    for r in final_rows:
        r['v2_h'] = original_index['X66', r['time']]['v2_h']
    audit = []
    for algorithm, python in [('catboost', catboost_python), ('lightgbm', lightgbm_python)]:
        values, record = worker(data, history, data['train'], validation, 'validation', algorithm, python, output)
        audit.append(record)
        for r, value in zip(validation, values):
            r[algorithm + '_hsht_h'] = value
    selection, cv_scores, cv_forecasts, ensemble_audit = walk_forward(validation, protocol)
    save_json(output / 'selection.json', selection)
    write_csv(output / 'validation_scores.csv', cv_scores)
    write_csv(output / 'validation_predictions.csv', cv_forecasts)
    write_csv(output / 'october_base_predictions.csv', [{k: r[k] for k in ['issue', 'time', 'observed', 'observed_at', 'available_at', 'v2_h', 'catboost_hsht_h', 'lightgbm_hsht_h']} for r in validation])
    save_json(output / 'ensemble_calibration_audit.json', ensemble_audit)
    for algorithm, python in [('catboost', catboost_python), ('lightgbm', lightgbm_python)]:
        values, record = worker(data, history, data['final'], final_rows, 'final', algorithm, python, output)
        audit.append(record)
        for r, value in zip(final_rows, values):
            r[algorithm + '_hsht_h'] = value
    selected = predict(selection['model'], final_rows)
    humidity = {r['time']: {**r, 'selected_h': value} for r, value in zip(final_rows, selected)}
    previous = {name: {(r['station'], r['time']): r for r in read_json(roots[name][0] / 'frozen_predictions.json')['predictions']} for name in ('V3', 'V4')}
    predictions = preserve_components(originals, previous, humidity, selection)
    check_passthrough(predictions, originals)
    created = dt.datetime.now(dt.timezone.utc)
    prospective_start = int(created.timestamp() // 3600 + 1) * 3600
    save_json(output / 'frozen_predictions.json', {'version': protocol['version'], 'candidate_created_at_utc': created.isoformat(),
        'forecast_issue_wib': wib(FREEZE), 'source_gfs_run_utc': '2026-11-02T06:00:00+00:00',
        'prior_november_actuals_already_revealed': True, 'november_actuals_used_for_fitting_or_selection': False,
        'future_confirmation_start_wib': wib(prospective_start), 'predictions': predictions})
    write_csv(output / 'frozen_forecasts.csv', predictions)
    save_json(output / 'training_audit.json', audit)
    save_json(output / 'feature_availability.json', history.audit)
    save_json(output / 'initial_humidity_context.json', history.get(FREEZE))
    save_json(output / 'input_checksums.json', {'historical_station_source': str(data['source']), 'source_sha256': data['source_hash'],
        'forecast_files': data['forecast_input_hashes'], 'hourly_hsht_signature': fingerprint([
            {'issue': 0, 'time': p['time'], 'observed': p['value'], 'observed_at': p['observed_at'], 'available_at': p['available_at']} for p in sorted(data['observations'].values(), key=lambda p: p['time'])])})
    if before != verify_references() or digest(data['source']) != data['source_hash']:
        raise ValueError('Old references or historical source changed during V5 training')
    from reporting import build_report
    build_report(output)
    snapshot = output / 'frozen_source'
    snapshot.mkdir()
    for source in VERSION_DIR.glob('*'):
        if source.is_file() and source.suffix in {'.py', '.json', '.md', '.txt'}:
            shutil.copyfile(source, snapshot / source.name)
    files = {p.relative_to(output).as_posix(): digest(p) for p in sorted(output.rglob('*')) if p.is_file() and 'jobs' not in p.relative_to(output).parts and '.matplotlib_cache' not in p.relative_to(output).parts}
    save_json(output / 'candidate_lock.json', {'version': protocol['version'], 'created_at_utc': created.isoformat(), 'immutable_files': files,
        'selection_completed_without_november_actuals': True, 'prior_november_actuals_revealed_in_chat': True})
    print({'output': str(output), 'selection': selection, 'locked_files': len(files), 'protected_forecast_rows': len(predictions)}, flush=True)


def verify(output):
    output = Path(output).resolve()
    lock = read_json(output / 'candidate_lock.json')
    for path, expected in lock['immutable_files'].items():
        if digest(output / path) != expected:
            raise ValueError('V5 immutable file changed: ' + path)
    if verify_references() != read_json(output / 'reference_locks.json'):
        raise ValueError('Original V2/V3/V4 reference no longer matches')
    originals = read_json(locate()['V2'][0] / 'frozen_predictions.json')['predictions']
    predictions = read_json(output / 'frozen_predictions.json')['predictions']
    n = check_passthrough(predictions, originals)
    return {'verified': True, 'v5_locked_files': len(lock['immutable_files']), 'v2_v3_v4_locked_files': 280,
            'temperature_rows_identical_to_v2': n, 'rain_and_probability_rows_identical_to_v2': n}


def default_runtime(kind):
    paths = [WORKSPACE / ('versions/v2_catboost' if kind == 'catboost' else 'version/v4') / '.venv/Scripts/python.exe',
             WORKSPACE / ('v3' if kind == 'catboost' else 'v4') / '.venv/Scripts/python.exe']
    return next((p for p in paths if p.exists()), Path(sys.executable))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build', 'verify', 'score'])
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--catboost-python', type=Path, default=default_runtime('catboost'))
    parser.add_argument('--lightgbm-python', type=Path, default=default_runtime('lightgbm'))
    parser.add_argument('--actuals', type=Path)
    parser.add_argument('--score-output', type=Path, default=VERSION_DIR / 'output/evaluation_20261106')
    args = parser.parse_args()
    if args.command == 'build':
        build(args.output, args.catboost_python, args.lightgbm_python)
    elif args.command == 'verify':
        print(verify(args.output))
    else:
        if args.actuals is None:
            parser.error('score requires --actuals')
        from score import score
        score(args.output, args.actuals, args.score_output)
