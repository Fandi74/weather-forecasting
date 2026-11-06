"""Read only the existing V2 inputs, checking hashes and pre-benchmark boundaries."""
import sys
from pathlib import Path

from .common import (FREEZE, HISTORY_START, VARIABLES, digest, finite, read_json,
                     verify_files, wib)


def locate_baseline(workspace):
    workspace = Path(workspace).resolve()
    for root in (workspace / 'v2', workspace, workspace / 'versions/v2'):
        if (root / 'engine_v2/core.py').exists():
            return root
    raise FileNotFoundError('V2 engine_v2 source not found in v2, workspace or historical versions/v2')


def baseline_context(workspace):
    root = locate_baseline(workspace)
    output = root / 'output/engine_v2/benchmark_20261103'
    lock = read_json(output / 'benchmark_lock.json')
    verify_files(output, lock['immutable_files'])
    for source in (root / 'engine_v2').iterdir():
        if source.is_file() and ('frozen_source/' + source.name) in lock['immutable_files']:
            if digest(source) != lock['immutable_files']['frozen_source/' + source.name]:
                raise ValueError('Current V2 source differs from frozen source: ' + source.name)
    sys.path.insert(0, str(root / 'engine_v2'))
    import core
    return {'root': root, 'output': output, 'lock': lock, 'core': core}


def load_inputs(workspace):
    context = baseline_context(workspace)
    root, output, core = context['root'], context['output'], context['core']
    checksums = read_json(output / 'input_checksums.json')
    # Never collect new forecasts and never open newly supplied actual exports.
    verify_files(root, checksums['forecast_files'])
    manifest, annual, exact, frozen = core.load_gfs()
    observations, inputs = {}, {}
    for station in manifest['stations']:
        path = root / 'data/engine_v2/observations' / f'{station}_hourly.json'
        records = read_json(path)
        for record in records:
            if record['time'] >= FREEZE:
                raise ValueError('Post-cutoff observation cache detected; blinded actuals must stay unread')
            for key in VARIABLES.values():
                if key in record and (record[key + '_observed_at'] >= FREEZE or record[key + '_available_at'] >= FREEZE):
                    raise ValueError('Observation/arrival crosses frozen cutoff')
        observations[station] = {r['time']: r for r in records}
        inputs[str(path.relative_to(root)).replace('\\', '/')] = digest(path)
    inputs.update({name.replace('\\', '/'): checksum for name, checksum in checksums['forecast_files'].items()})
    inputs['data/engine_v2/gfs/manifest.json'] = digest(root / 'data/engine_v2/gfs/manifest.json')
    context.update(manifest=manifest, annual=annual, exact=exact, frozen=frozen,
                   observations=observations, input_checksums=inputs,
                   original_models=read_json(output / 'models.json')['models'])
    original = read_json(output / 'frozen_predictions.json')['predictions']
    reproduced = core.predict_frozen(frozen, context['original_models'])
    for a, b in zip(original, reproduced):
        if (a['station'], a['time']) != (b['station'], b['time']):
            raise ValueError('Frozen row alignment differs')
        for key in ('v2_t', 'v2_h', 'v2_rain', 'rain_probability'):
            if a[key] is None and b[key] is None:
                continue
            if abs(a[key] - b[key]) > 1e-10:
                raise ValueError('Cannot reproduce original V2 frozen prediction')
    context['original_frozen'] = original
    return context


def paired_rows(context, station, variable, cutoff, exact_only=False, validation=False):
    core = context['core']
    if validation:
        rows = list(core.attach_observations(context['exact'], context['observations'], variable, cutoff))
        rows = [r for r in rows if r['issue'] >= core.VALIDATION_START]
    elif exact_only:
        rows = list(core.attach_observations(context['exact'], context['observations'], variable, cutoff))
        rows = [r for r in rows if r['issue'] < cutoff]
    else:
        rows = core.training_rows(context['annual'], context['exact'], context['observations'], variable, cutoff)
    # Common rows for every compared model; missing history remains missing, not excluded.
    return sorted((r for r in rows if r['station'] == station and r['time'] >= HISTORY_START
                   and all(finite(r[k]) for k in ('forecast_t', 'forecast_h', 'forecast_rain'))),
                  key=lambda r: (r['time'], r['day']))


def reconstruct_v2_validation(context, station, variable, train, val):
    """Original selected recipe, parameters refitted only on pre-October examples.

    V2 selected these recipes on October: this reproduces selection evidence,
    never applies the final November-trained V2 parameters to October targets.
    """
    core = context['core']
    original = context['original_models'][station]
    if variable in ('temperature', 'humidity'):
        models = {}
        for day in range(1, 8):
            method = original[variable][str(day)]['method']
            models[day] = {'method': 'raw'} if method == 'raw' else core.fit_offset([r for r in train if r['day'] == day], method)
        return [core.offset_predict(r, models[r['day']], variable) for r in val]
    if variable == 'rain':
        model = original['rain']
        fit = core.fit_rain(train, model['method'], model.get('penalty', 1.0))
        return core.rain_predict(val, fit)
    raise ValueError(variable)


def reconstruct_v2_probability(context, station, train, val):
    core = context['core']
    selected = context['original_models'][station]['rain_probability']
    if selected is None:
        return [None] * len(val)
    if selected['method'] == 'logistic':
        model = core.fit_logistic(train, selected['penalty'])
    else:
        model = {'method': 'climatology', 'probability': sum(r['observed'] >= 0.28 - 1e-9 for r in train) / len(train)}
    return core.probability_predict(val, model)
