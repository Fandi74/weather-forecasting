"""Build and verify the V7 composition, without fitting any component."""
import argparse
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from composition import compose_forecasts, point_forecasts

V7 = Path(__file__).resolve().parent
ROOT = V7.parent
OUTPUT = V7/'output/merged_candidate_20261106'
V5 = ROOT/'v5/output/benchmark_20261103_humidity_v5'
V6 = ROOT/'v6/output/e11_corrected_20261106'
VERSION = 'engine_v7_combined.1'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf-8', newline='\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_roots():
    v2 = ROOT if (ROOT/'engine_v2/core.py').exists() else ROOT/'v2'
    v3 = next(p for p in [ROOT/'v3', ROOT/'versions/v2_catboost'] if p.exists())
    v4 = next(p for p in [ROOT/'v4', ROOT/'version/v4'] if p.exists())
    return {
        'V2': (v2/'output/engine_v2/benchmark_20261103','benchmark_lock.json'),
        'V3': (v3/'output/benchmark_20261103_catboost','candidate_lock.json'),
        'V4': (v4/'output/benchmark_20261103_lightgbm','candidate_lock.json'),
        'V5': (V5,'candidate_lock.json'),
        'V6_initial': (ROOT/'v6/output/rainfall_candidate_20261106','candidate_lock.json'),
        'V6_weekly': (ROOT/'v6/output/rolling_refresh_20261106','rolling_lock.json'),
        'V6_E11': (V6,'clarification_lock.json')}


def resolve_source(path):
    direct = ROOT/path
    return direct if direct.exists() else ROOT/'v2'/path


def verify_references():
    result = {}
    for name, (folder, lock_name) in reference_roots().items():
        lock = load(folder/lock_name)
        for path, expected in lock['immutable_files'].items():
            if sha(folder/path.replace('\\','/')) != expected:
                raise ValueError('Earlier frozen file changed: '+name+'/'+path)
        result[name] = {'files': len(lock['immutable_files']), 'lock_sha256': sha(folder/lock_name)}
    return result


def worker(command, output, input_path=None):
    args = [sys.executable, str(V7/'rainfall_worker.py'), command, str(output)]
    if input_path is not None:
        args += ['--input',str(input_path)]
    subprocess.run(args, check=True, cwd=ROOT)


def copy_components():
    copies = []
    pairs = [(V5/'selection.json',V7/'models/humidity_selection.json'),
        (V6/'model_catalog.json',V7/'models/rainfall_catalog.json'),
        (ROOT/'v6/output/rainfall_candidate_20261106/selection.json',V7/'models/rainfall_selection.json'),
        (reference_roots()['V2'][0]/'models.json',V7/'models/temperature/v2_models.json')]
    for algorithm, filename in [('catboost','humidity.cbm'),('lightgbm','humidity.txt')]:
        pairs.append((V5/'models/final'/algorithm/filename,V7/'models/humidity'/algorithm/filename))
    rain_models = V6/'raw_srm_1h/models/final'
    pairs += [(p,V7/'models/rainfall'/p.relative_to(rain_models)) for p in sorted(rain_models.rglob('*')) if p.is_file()]
    for source, destination in pairs:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and sha(destination) != sha(source):
            raise ValueError('Existing V7 component differs: '+str(destination))
        shutil.copyfile(source,destination)
        copies.append({'source': source.relative_to(ROOT).as_posix(), 'copy': destination.relative_to(V7).as_posix(), 'sha256': sha(source)})
    return copies


def write_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build():
    if OUTPUT.exists():
        raise ValueError('Use the existing verify/replay commands; V7 output cannot be overwritten')
    before = verify_references()
    copies = copy_components()
    OUTPUT.mkdir(parents=True)
    save(OUTPUT/'reference_locks.json',before)
    save(OUTPUT/'component_copies.json',copies)
    original = load(V5/'frozen_predictions.json')
    save(OUTPUT/'humidity_temperature_component.json',original)
    snapshot_path = OUTPUT/'rainfall_feature_snapshot.json'
    worker('snapshot',snapshot_path)
    worker('predict',OUTPUT/'v6_corrected_rainfall_predictions.json',snapshot_path)
    rain = load(OUTPUT/'v6_corrected_rainfall_predictions.json')
    merged = compose_forecasts(original['predictions'],rain)
    points = point_forecasts(original['predictions'])
    metadata = {'version': VERSION, 'created_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'forecast_issue_wib': original['forecast_issue_wib'],
        'source_gfs_run_utc': original['source_gfs_run_utc'],
        'mode': 'Retrospective composition of already-frozen component models; no retraining',
        'temperature_component': 'V2 via V5', 'humidity_component': 'V5 frozen equal-third ensemble at X66',
        'rainfall_component': 'V6 E11-corrected final models; assumed +1h receipt delay',
        'humidity_update_stations': ['X66'], 'rainfall_component_stations': ['X50','X66'],
        'rainfall_fallback_stations': ['X51','X67'],
        'rainfall_windows_hours': [1,6,12,24],
        'point_forecast_hours_per_station': 168,
        'november_actuals_previously_revealed': True,
        'new_training_or_model_selection': False,
        'new_combined_accuracy_claim': False,
        'rainfall_status': 'Experimental; no consistent gain over raw GFS established',
        'timing_status': 'Assigned CSV timestamp semantics unconfirmed; +1h is inherited assumption',
        'unsupported_joint_rain_probability': 'Null for multi-hour X51/X67 fallback windows; hourly probabilities are not summed',
        'forecast_window_coherence': 'Separate V6 windows/components are retained; no coherent joint distribution is claimed'}
    save(OUTPUT/'frozen_predictions.json',{**metadata,'predictions':merged})
    save(OUTPUT/'hourly_temperature_humidity.json',{'version':VERSION,'predictions':points})
    write_csv(OUTPUT/'merged_forecasts.csv',merged)
    write_csv(OUTPUT/'hourly_temperature_humidity.csv',points)
    dependencies = {}
    v2_engine = reference_roots()['V2'][0].parents[2]/'engine_v2'
    for path in list((ROOT/'v6').glob('*.py')) + [v2_engine/name for name in ['core.py','collect.py','observations.py']]:
        dependencies[path.relative_to(ROOT).as_posix()] = sha(path)
    save(OUTPUT/'source_dependencies.json',dependencies)
    from plotting import render
    render(OUTPUT,original['predictions'],merged)
    if verify_references() != before:
        raise ValueError('Earlier references changed during composition')
    (OUTPUT/'report.md').write_text(report_text(), encoding='utf-8', newline='\n')
    source_dir = OUTPUT/'frozen_source'
    source_dir.mkdir()
    for path in sorted(V7.glob('*.py')):
        shutil.copyfile(path,source_dir/path.name)
    excluded = {'.matplotlib_cache','__pycache__'}
    sealed = {}
    for folder in [V7/'models', OUTPUT]:
        for path in sorted(folder.rglob('*')):
            if path.is_file() and not excluded.intersection(path.parts):
                sealed[path.relative_to(V7).as_posix()] = sha(path)
    save(OUTPUT/'candidate_lock.json',{'version':VERSION,'immutable_files':sealed})
    print(json.dumps(verify(),indent=2))


def report_text():
    return """# V7: V5 humidity + V6 rainfall

V7 combines the existing component models. Temperature remains V2, humidity
retains V5 exactly, and X50/X66 rainfall uses the E11-corrected final V6 models
with the inherited assumed one-hour observation delay. No model is retrained.

The issue is 3 November 2026 00:00 WIB, using the same archived GFS input.
This is a retrospective snapshot built after November observations were seen,
not a new live forecast or untouched accuracy test.

There are 672 unchanged hourly temperature/humidity points and 16 combined
station/window forecasts. Temperature and humidity are values at each window
end; rain amount is the total over the whole 1/6/12/24-hour window.

X51/X67 retain their existing V5/V2 hourly rain amounts summed over each window.
Only the one-hour probability is available for those stations. Multi-hour
fallback probabilities are null, because hourly probabilities cannot be summed.

The V5 humidity improvement applies at X66. The V6 rain component applies at
X50/X66 and still includes the original validation-selected weather-only and
V2-recipe fallback routes. Combining the components does not establish a new
accuracy improvement; V6 amount has not consistently beaten raw GFS.

![V7 component composition](V7_merged_forecasts.png)

The rain bars compare inherited V5 hourly amounts summed to the same windows
with the V6 component now used by V7. They are predictions, not accuracy scores.
Overlapping temperature/humidity lines have identical values.

See [merged forecasts](merged_forecasts.csv), [seven-day point values](hourly_temperature_humidity.csv),
[exact component copies](component_copies.json), and [feature snapshot](rainfall_feature_snapshot.json).

Run `python v7/run.py verify` without ML dependencies.
Run `python v7/run.py replay` with the LightGBM runtime to re-run rain inference.
All earlier versions are preserved. Nothing in this build publishes to GitHub.
"""


def verify():
    lock = load(OUTPUT/'candidate_lock.json')
    for path, expected in lock['immutable_files'].items():
        if sha(V7/path) != expected:
            raise ValueError('V7 frozen file differs: '+path)
    refs = verify_references()
    if refs != load(OUTPUT/'reference_locks.json'):
        raise ValueError('Reference locks changed')
    for path, expected in load(OUTPUT/'source_dependencies.json').items():
        if sha(resolve_source(path)) != expected:
            raise ValueError('Source dependency changed: '+path)
    copies = load(OUTPUT/'component_copies.json')
    for record in copies:
        if sha(resolve_source(record['source'])) != record['sha256'] or sha(V7/record['copy']) != record['sha256']:
            raise ValueError('Copied model differs')
    v5 = load(V5/'frozen_predictions.json')['predictions']
    original = load(OUTPUT/'humidity_temperature_component.json')['predictions']
    if original != v5:
        raise ValueError('V5 input changed')
    rain = load(OUTPUT/'v6_corrected_rainfall_predictions.json')
    merged = load(OUTPUT/'frozen_predictions.json')['predictions']
    if compose_forecasts(v5,rain) != merged:
        raise ValueError('Composition differs from selected component outputs')
    points = load(OUTPUT/'hourly_temperature_humidity.json')['predictions']
    if points != point_forecasts(v5) or len(points) != 672:
        raise ValueError('Hourly temperature/humidity changed')
    for r in load(OUTPUT/'rainfall_feature_snapshot.json')['feature_availability']:
        if r['max_assumed_availability_used'] is not None and (r['max_assumed_availability_used'] > r['issue'] or r['max_csv_timestamp_used'] > r['issue']):
            raise ValueError('Future observation feature used')
    return {'verified':True,'version':VERSION,'frozen_v7_files':len(lock['immutable_files']),
        'earlier_frozen_files_unchanged':sum(r['files'] for r in refs.values()),
        'copied_component_files':len(copies),'unchanged_temperature_humidity_rows':len(points),
        'combined_window_rows':len(merged),'v6_rainfall_windows':len(rain),'models_retrained':False}


def replay():
    result = verify()
    with tempfile.TemporaryDirectory(prefix='.replay-', dir=V7) as tmp:
        if Path(tmp).resolve().parent != V7.resolve():
            raise ValueError('Replay scratch path leaves the V7 folder')
        path = Path(tmp)/'predictions.json'
        worker('predict',path,OUTPUT/'rainfall_feature_snapshot.json')
        if load(path) != load(OUTPUT/'v6_corrected_rainfall_predictions.json'):
            raise ValueError('Rain model replay differs from the frozen composition')
    print(json.dumps({**result,'rainfall_model_replay_identical':True},indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['build','verify','replay'])
    args = parser.parse_args()
    if args.command == 'build':
        build()
    elif args.command == 'verify':
        print(json.dumps(verify(),indent=2))
    else:
        replay()
