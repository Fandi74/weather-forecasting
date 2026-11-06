import csv
import os

from .common import VERSION_DIR, VARIANTS, VARIABLES, read_json


def number(value, digits=3):
    return '—' if value is None or value == '' else f'{float(value):.{digits}f}'


def report(output):
    with (output / 'validation_scores.csv').open(encoding='utf-8-sig') as stream:
        scores = list(csv.DictReader(stream))
    selection = read_json(output / 'selection.json')
    audit = read_json(output / 'training_audit.json')
    environment = read_json(output / 'environment.json')
    frozen_features = read_json(output / 'frozen_features.json')
    lines = ['# Engine V2: local CatBoost candidate', '',
        '**The original V2 is unchanged. All November benchmark actuals remain withheld.**', '',
        'Three CatBoost candidates were trained and their predictions saved for 3–9 November 2026. '
        'The selected forecast uses the best October method per station/component, including original V2 '
        'or raw fallback when a CatBoost candidate did not improve the declared metric.', '',
        '## Data and experiment', '',
        '- Temperature/humidity: regress observation minus GFS with MAE loss. Humidity is bounded to 0–100%.',
        '- Rain: Logloss occurrence classifier plus RMSE positive-amount regressor; expected amount is their product.',
        '- Fixed CatBoost configuration: 400 trees, depth 4, learning rate 0.04, L2 10, CPU, fixed seed. No hyperparameter search or early stopping.',
        '- `catboost_base_full`: existing annual V2 pairs, preferring matching exact weekly runs.',
        '- `catboost_base_exact`: exact weekly forecasts only, using the same six existing-input features.',
        '- `catboost_history_exact`: same exact training rows plus then-available station history and recent forecast errors.',
        '- The exact-only comparison isolates added history features. Comparing history against base_full also changes the training dataset.',
        '- Fit for validation: all labels and assumed arrivals before 1 October. Evaluate four exact October weekly forecasts.',
        '- Select component methods using October MAE (temperature/humidity), RMSE (rain), Brier score (probability).',
        '- Refit all supported CatBoost variants using only labels/arrivals before 3 November 00:00 WIB.',
        '- Frozen future GFS: the same 2 November 06 UTC run as V2. No GFS updates from 3 November onward.',
        '- One fixed station context at the simulated issue is used for all 168 hours. No later actual is fed into later hours.', '',
        '## October validation comparison', '',
        'These are **model-selection results, not untouched final-test accuracy**. Original V2 recipes were selected '
        'on October in the earlier experiment; their parameters are refitted on pre-October data here. '
        'Final November-trained V2 parameters are never evaluated against October outcomes. '
        'All compared methods use identical valid cases per variable. Overlapping forecast errors and repeated '
        'targets across lead bands are correlated; row counts are not independent storm counts.', '',
        '| Station | Variable | Matched hours | Raw GFS | Original V2 recipe | CatBoost full | CatBoost exact | CatBoost + history | Selected |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for station in selection:
        for variable in ('temperature', 'humidity', 'rain', 'rain_probability'):
            metric = 'mae' if variable in ('temperature', 'humidity') else 'rmse' if variable == 'rain' else 'brier'
            rows = {r['model']: r for r in scores if r['station'] == station and r['variable'] == variable and r['scope'] == 'all_168h'}
            n = max((int(r['n']) for r in rows.values()), default=0)
            values = [number(rows.get(name, {}).get(metric), 4 if variable == 'rain_probability' else 3)
                      for name in ('raw_gfs', 'engine_v2') + VARIANTS]
            lines.append(f"| {station} | {variable} | {n} | {' | '.join(values)} | {selection[station][variable]['method']} |")
    lines += ['', 'Temperature is MAE in °C; humidity MAE in percentage points; rain RMSE in mm/hour; probability is Brier score. '
              'Lower is better. Raw GFS probability is unavailable because the archived input contains no matching event probability.', '',
        '![Validation comparison](validation.png)', '',
        '## First 24 hours of the October forecasts', '',
        'This subset is reported separately; selections above use the full seven-day validation period.', '',
        '| Station | Variable | Hours | Raw GFS | Original V2 | CatBoost full | CatBoost exact | CatBoost + history |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for station in ('X50', 'X66'):
        for variable in ('temperature', 'humidity', 'rain', 'rain_probability'):
            metric = 'mae' if variable in ('temperature', 'humidity') else 'rmse' if variable == 'rain' else 'brier'
            rows = {r['model']: r for r in scores if r['station'] == station and r['variable'] == variable and r['scope'] == 'first_24h'}
            values = [number(rows.get(name, {}).get(metric), 4 if variable == 'rain_probability' else 3)
                      for name in ('raw_gfs', 'engine_v2') + VARIANTS]
            n = max((int(r['n']) for r in rows.values()), default=0)
            lines.append(f"| {station} | {variable} | {n} | {' | '.join(values)} |")
    lines += ['', '## Rain amount diagnostics', '',
        'A small RMSE improvement is not evidence that rain timing or totals are solved. '
        'In particular, the X66 models substantially underpredict October rain. '
        'Hits below count hours whose expected amount reaches 0.28 mm, not probability-based event decisions.', '',
        '| Station | Method | Observed total mm | Expected total mm | Amount MAE | Wet-hour MAE | Hits | Misses | False alarms |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for station in ('X50', 'X66'):
        for name in ('raw_gfs', 'engine_v2') + VARIANTS:
            row = next(r for r in scores if r['station'] == station and r['variable'] == 'rain' and r['scope'] == 'all_168h' and r['model'] == name)
            values = [number(row.get(k)) for k in ('observed_total_mm', 'predicted_total_mm', 'mae', 'wet_mae')]
            counts = [row.get(k, '—') for k in ('hits', 'misses', 'false_alarms')]
            lines.append(f"| {station} | {name} | {' | '.join(values)} | {' | '.join(counts)} |")
    lines += ['', '## Final training sample counts', '',
        '| Station | Variable | Full paired rows | Exact-only paired rows | Full unique target hours |',
        '| --- | --- | ---: | ---: | ---: |']
    for station in ('X50', 'X66'):
        for variable in VARIABLES:
            full = next(a for a in audit if a['station'] == station and a['variable'] == variable and a['stage'] == 'final' and a['variant'] == 'catboost_base_full')
            exact = next(a for a in audit if a['station'] == station and a['variable'] == variable and a['stage'] == 'final' and a['variant'] == 'catboost_base_exact')
            lines.append(f"| {station} | {variable} | {full['training_rows']} | {exact['training_rows']} | {full['unique_target_hours']} |")
    lines += ['', '## Station history at the frozen issue', '',
        'The supplied exports end around 2 November 15:00 WIB. At the simulated '
        '3 November midnight issue, X50/X66 readings are about nine hours old. '
        'Latest/rolling station values therefore expire under the declared six-hour '
        'feature rule and remain missing. Ages and then-available 24-hour error features '
        'are still provided. The history model accepts missing features, but its October '
        'validation advantage may not carry over to this less recent context. '
        'All variant forecasts are retained for the blind comparison.', '',
        '| Station | Temperature age (hours) | Humidity age (hours) | Rain age (hours) | Latest readings usable |',
        '| --- | ---: | ---: | ---: | --- |']
    for station in selection:
        history = next(r['history_features'] for r in frozen_features if r['station'] == station)
        ages = [number(history[key + '_age_hours'], 2) for key in ('t', 'h', 'rain')]
        usable = ', '.join(key for key in ('t', 'h', 'rain') if history[key + '_latest'] is not None) or 'None'
        lines.append(f"| {station} | {' | '.join(ages)} | {usable} |")
    lines += ['', '## Boundaries and known issues', '',
        '- X51 has no October validation; X67 has no accepted independent observations. They retain raw GFS with unavailable fitted rain probabilities.',
        '- X66 uses the user-retained t/h sensor stream despite its disagreement with tsht/hsht. Lower error against that stream does not establish physical sensor accuracy.',
        '- Station receipt times remain an assumption of measurement plus one hour. Feature use is audited against that assumed availability, not verified historical receipts.',
        '- Raw input source hashes, normalized observation hashes, training cutoffs and all feature availability maxima are recorded.',
        '- Annual day-band forecasts are approximate lead representatives. History features are never attached to those rows because exact issue times are unknown.',
        '- Exact weekly simulations all issue at midnight WIB. Generalization to arbitrary hourly updates is untested.',
        '- Hourly rain means >=0.28 mm. Joint 6/12/24-hour probabilities remain unavailable. Amount/probability selections may differ, so the selected output is not a full joint predictive distribution.',
        '- The experiment is retrospective and the original GFS publication timestamp is unverified. Transfer to sites 50 km away is unproven.',
        '- No model has been uploaded to GitHub.', '',
        '## Artifacts', '',
        '- `frozen_forecasts.csv` / `frozen_predictions.json`: all 672 original/raw/candidate/selected hourly forecasts.',
        '- `models/final/`: saved CatBoost models and feature definitions for both eligible stations and all three variants.',
        '- `selection.json`: chosen components and October selection scores.',
        '- `forecast_windows.csv`: initial 1/6/12/24-hour rain totals; `daily_forecasts.csv`: seven daily summaries.',
        '- `validation_scores.csv`: identical-case scores for all horizons and each day/first 24h.',
        '- `validation_predictions.csv`: row-level October observations and predictions.',
        '- `training_audit.json`, `feature_availability.csv`, `frozen_features.json`, `input_checksums.json`: leakage/provenance audit.',
        '- `candidate_lock.json`: immutable hashes after review; later scoring writes separate output and never refits.', '',
        f"Runtime: Python {environment['python']}; " + ', '.join(f'{k} {v}' for k, v in environment['packages'].items()) + '.', '',
        'Official implementation references: [CatBoost regression](https://catboost.ai/docs/en/concepts/python-reference_catboostregressor), '
        '[classification](https://catboost.ai/docs/en/concepts/python-reference_catboostclassifier).', '',
        '## Frozen forecast comparisons', '']
    for station in ('X50', 'X66'):
        lines += [f'![{station}: raw GFS, original V2 and selected candidate](forecast_{station}.png)', '']
    (output / 'training_report.md').write_text('\n'.join(lines), encoding='utf-8')


def plots(predictions, validation, output):
    os.environ.setdefault('MPLCONFIGDIR', str(VERSION_DIR / '.mpl-cache'))
    import datetime as dt
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from .common import WIB
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    names = ('raw_gfs', 'engine_v2') + VARIANTS
    colors = ['#898989', '#2870aa', '#d98022', '#9e5ab5', '#2c9560']
    fig, axes = plt.subplots(2, 4, figsize=(17, 8), layout='constrained')
    for row_index, station in enumerate(('X50', 'X66')):
        for col, (variable, metric, unit) in enumerate((('temperature', 'mae', 'MAE °C'), ('humidity', 'mae', 'MAE pp'),
                                                     ('rain', 'rmse', 'RMSE mm/h'), ('rain_probability', 'brier', 'Brier'))):
            ax = axes[row_index, col]
            values = {r['model']: r.get(metric) for r in validation if r['station'] == station and r['variable'] == variable and r['scope'] == 'all_168h'}
            valid = [(i, values.get(name)) for i, name in enumerate(names) if values.get(name) is not None]
            ax.bar([i for i, _ in valid], [v for _, v in valid], color=[colors[i] for i, _ in valid])
            ax.set_xticks(range(5), ['GFS', 'V2', 'CB full', 'CB exact', 'CB history'], rotation=35, ha='right')
            ax.set_title(f'{station}: {variable}')
            ax.set_ylabel(unit)
            ax.grid(axis='y', alpha=0.2)
    fig.suptitle('October validation used for model selection — November blind accuracy pending', fontsize=15)
    fig.savefig(output / 'validation.png', dpi=150)
    plt.close(fig)
    for station in ('X50', 'X66'):
        rows = [r for r in predictions if r['station'] == station]
        dates = [dt.datetime.fromtimestamp(r['time'], WIB) for r in rows]
        rain_dates = [d - dt.timedelta(minutes=30) for d in dates]
        fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True, layout='constrained')
        for ax, key, label in zip(axes, ('t', 'h', 'rain'), ('Temperature °C', 'Humidity %', 'Rain mm/hour')):
            for prefix, color, title in (('raw', '#898989', 'Raw GFS'), ('v2', '#2870aa', 'Original V2'), ('selected', '#cc6722', 'Selected candidate')):
                ax.plot(rain_dates if key == 'rain' else dates, [r[prefix + '_' + key] for r in rows],
                        color=color, label=title, linewidth=1.2, alpha=0.85)
            ax.set_ylabel(label)
            ax.grid(alpha=0.2)
            ax.legend(loc='upper right', ncol=3, frameon=False)
        axes[1].set_ylim(0, 103)
        axes[2].set_ylim(bottom=0)
        fig.suptitle(f'{station}: frozen 3–9 November 2026 — actual measurements withheld', fontsize=15)
        fig.savefig(output / f'forecast_{station}.png', dpi=150)
        plt.close(fig)
