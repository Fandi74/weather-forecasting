"""Render V2 and the renamed V3 candidate from their immutable predictions."""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V4 = Path(__file__).resolve().parent / 'output/benchmark_20261103_lightgbm'
OUT = V4 / 'graphs'
os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parent / '.mpl-cache'))

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

WIB = dt.timezone(dt.timedelta(hours=7))
STATIONS = ('X50', 'X51', 'X66', 'X67')
V2 = ROOT / 'v2/output/engine_v2/benchmark_20261103'
V3 = ROOT / 'v3/output/benchmark_20261103_catboost'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_lock(directory, name):
    lock = read(directory / name)
    for relative, expected in lock['immutable_files'].items():
        if sha(directory / relative) != expected:
            raise ValueError('Immutable file changed: ' + relative)
    return len(lock['immutable_files'])


def main():
    if (V4 / 'candidate_lock.json').exists():
        raise ValueError('V4 is locked; use the existing graphs or a separate output directory.')
    OUT.mkdir(parents=True, exist_ok=True)
    checked_before = [verify_lock(V2, 'benchmark_lock.json'), verify_lock(V3, 'candidate_lock.json')]
    v2 = read(V2 / 'frozen_predictions.json')['predictions']
    v3 = read(V3 / 'frozen_predictions.json')['predictions']
    selection = read(V3 / 'selection.json')
    v4 = read(V4 / 'frozen_predictions.json')['predictions']
    v4_selection = read(V4 / 'selection.json')
    assert len(v4) == 672
    assert {(r['station'], r['time']) for r in v4} == {(r['station'], r['time']) for r in v2}
    assert len(v2) == len(v3) == 672
    assert {(r['station'], r['time']) for r in v2} == {(r['station'], r['time']) for r in v3}
    for r2, r3 in zip(v2, v3):
        assert (r2['station'], r2['time']) == (r3['station'], r3['time'])
        assert all(r2['v2_' + k] == r3['v2_' + k] for k in ('t', 'h', 'rain'))
    t_values = [r['v2_t'] for r in v2] + [r['selected_t'] for r in v3] + [r['selected_t'] for r in v4]
    rain_values = [r['v2_rain'] for r in v2] + [r['selected_rain'] for r in v3] + [r['selected_rain'] for r in v4]
    limits = [(math.floor(min(t_values) - 1), math.ceil(max(t_values) + 1)),
              (0, 105), (0, max(0.1, max(rain_values) * 1.16)), (0, 100)]
    colors = ['#c96330', '#268d91', '#3e76b5', '#4c8b55']
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.edgecolor': '#b7c3ce', 'axes.labelcolor': '#26384a',
                         'xtick.color': '#536578', 'ytick.color': '#536578',
                         'savefig.facecolor': '#ffffff'})
    files, totals = [], {}
    for version, source, prefix in (('V2', v2, 'v2'), ('V3', v3, 'selected'), ('V4', v4, 'selected')):
        fig, axes = plt.subplots(4, 4, figsize=(18, 12), sharex=True, sharey='row')
        fig.subplots_adjust(left=0.065, right=0.985, top=0.82, bottom=0.12, wspace=0.12, hspace=0.20)
        fig.text(0.065, 0.955, 'FIELD FORECAST  /  FROZEN BENCHMARK', fontsize=10, color='#526b82', weight='bold')
        title = 'Engine V2 — prediction' if version == 'V2' else 'Engine V3 — CatBoost candidate' if version == 'V3' else 'Engine V4 — LightGBM candidate'
        fig.text(0.065, 0.912, title, fontsize=25, weight='bold', color='#18354b')
        fig.text(0.065, 0.879, '3–9 November 2026  ·  168 hourly intervals per location  ·  WIB (UTC+7)', fontsize=12, color='#314e65')
        fig.text(0.985, 0.950, 'ACTUALS WITHHELD\nAccuracy not yet scored', ha='right', va='top', fontsize=10,
                 color='#796334', bbox={'facecolor': '#fcf4df', 'edgecolor': 'none', 'pad': 8})
        totals[version] = {}
        for col, station in enumerate(STATIONS):
            rows = sorted((r for r in source if r['station'] == station), key=lambda r: r['time'])
            assert len(rows) == 168
            times = [dt.datetime.fromtimestamp(r['time'], WIB) for r in rows]
            centers = [t - dt.timedelta(minutes=30) for t in times]
            note = 'Raw GFS fallback' if station in ('X51', 'X67') else 'Sensor discrepancy flagged' if station == 'X66' else 'Station-based corrections'
            axes[0, col].set_title(station + '\n' + note, fontsize=11, color='#243f55', pad=14, weight='bold')
            series = [[r[prefix + '_t'] for r in rows], [r[prefix + '_h'] for r in rows],
                      [r[prefix + '_rain'] for r in rows],
                      [r['rain_probability'] if version == 'V2' else r['selected_rain_probability'] for r in rows]]
            totals[version][station] = sum(series[2])
            for row_index, (ax, values) in enumerate(zip(axes[:, col], series)):
                ax.set_facecolor('#fbfcfd')
                ax.set_ylim(limits[row_index])
                ax.grid(axis='y', color='#e2e8ed', linewidth=0.65)
                ax.set_axisbelow(True)
                ax.tick_params(axis='both', labelsize=8)
                ax.xaxis.set_major_locator(mdates.DayLocator(tz=WIB))
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b', tz=WIB))
                ax.set_xlim(dt.datetime(2026, 11, 3, tzinfo=WIB), dt.datetime(2026, 11, 10, tzinfo=WIB))
                if row_index < 2:
                    ax.plot(times, values, color=colors[row_index], linewidth=1.4)
                elif row_index == 2:
                    ax.bar(centers, values, width=0.035, color=colors[row_index], alpha=0.86)
                    ax.text(0.97, 0.94, f'Total {sum(values):.1f} mm', transform=ax.transAxes,
                            ha='right', va='top', fontsize=8, color='#355a82')
                    if ((version == 'V3' and station == 'X50') or (version == 'V4' and v4_selection[station]['rain']['method'] == 'engine_v2')):
                        ax.text(0.03, 0.94, 'V2 retained', transform=ax.transAxes, va='top', fontsize=8,
                                color='#6a5b3d', bbox={'facecolor': '#fcf4df', 'edgecolor': 'none', 'pad': 2})
                elif all(v is None for v in values):
                    ax.text(0.5, 0.5, 'Probability unavailable\nNo validated station model', ha='center', va='center',
                            transform=ax.transAxes, color='#7c8994', fontsize=10)
                else:
                    probability = [v * 100 if v is not None else np.nan for v in values]
                    ax.plot(centers, probability, color=colors[row_index], linewidth=1.3)
                    ax.fill_between(centers, probability, color=colors[row_index], alpha=0.12)
                if col == 0:
                    ax.set_ylabel(('Temperature\n°C', 'Relative humidity\n%', 'Rain amount\nmm / hour', 'Rain probability\n%')[row_index], fontsize=10, labelpad=12)
                if row_index == 3:
                    ax.tick_params(axis='x', rotation=40)
        fig.text(0.065, 0.053, 'Frozen issue: 3 Nov 00:00 WIB  |  Same GFS run: 2 Nov 06:00 UTC  |  Matching scales in both images', fontsize=9, color='#314e65')
        fig.text(0.065, 0.032, 'T/RH are interval-end values. Rain is the preceding hour’s total. Probability event: at least 0.28 mm within that hour.', fontsize=9, color='#536578')
        foot = ('V2: X51/X67 retain raw forecasts. X66 uses the flagged t/h sensor stream.' if version == 'V2' else
                'V3 = selected frozen CatBoost candidate; X50 rain retains V2, X51/X67 retain GFS. Nine-hour-old latest station values are masked.')
        if version == 'V4':
            kept = ', '.join(s + ' ' + variable for s in STATIONS for variable in ('temperature', 'humidity', 'rain', 'rain_probability') if v4_selection[s][variable]['method'] == 'engine_v2')
            foot = 'V4 = selected LightGBM candidate; V2 retained: ' + (kept or 'none') + '. X51/X67: raw GFS. X66 sensor warning; expired histories missing.'
        fig.text(0.065, 0.012, foot, fontsize=8.2, color='#6b7782')
        target = OUT / f'{version}_prediction_7days.png'
        fig.savefig(target, dpi=180)
        plt.close(fig)
        files.append(str(target))
    checked_after = [verify_lock(V2, 'benchmark_lock.json'), verify_lock(V3, 'candidate_lock.json')]
    assert checked_before == checked_after
    metadata = {'display_alias': {'V3': 'engine_v2_catboost.1 — selected frozen component forecast'},
                'sources': {'V2': str(V2 / 'frozen_predictions.json'), 'V3': str(V3 / 'frozen_predictions.json'), 'V4': str(V4 / 'frozen_predictions.json')},
                'source_sha256': {'V2': sha(V2 / 'frozen_predictions.json'), 'V3': sha(V3 / 'frozen_predictions.json'), 'V4': sha(V4 / 'frozen_predictions.json')},
                'locked_files_verified_before_and_after': checked_after, 'rows_per_engine': 672,
                'period_wib': ['2026-11-03T00:00:00+07:00', '2026-11-10T00:00:00+07:00'],
                'shared_y_limits': limits, 'rain_totals_mm': totals, 'v3_selection': selection, 'v4_selection': v4_selection,
                'files': {Path(p).name: sha(Path(p)) for p in files}}
    (OUT / 'graph_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    (OUT / 'README.md').write_text('# V2, V3 and V4 prediction graphs\n\n'
        'V3 is the user-selected name for the frozen CatBoost candidate formerly stored as '
        '`engine_v2_catboost.1`. V4 is independently trained LightGBM on matched V2/V3 data and features; earlier locked artifacts remain unchanged.\n\n'
        'All three graphs show the same seven-day period and share axis ranges. Every station has 168 hourly '
        'predictions. Temperature/humidity use the interval-end instant; rain uses the preceding hour. '
        'Rain probability is for at least 0.28 mm/hour. Actual observations remain withheld.\n\n'
        'V3 retains V2 for X50 rain amount. V4 retains V2 for X50/X66 rain amounts and X66 rain probability. '
        'X51/X67 retain raw GFS in all versions; X66 retains the sensor warning. Source identities, '
        'hashes, selected methods and rain totals are in graph_metadata.json. Drawing the graphs '
        'does not refit models. V4 has not been pushed to GitHub.\n', encoding='utf-8')
    print(json.dumps({'files': files, 'locked_files_verified': checked_after, 'rain_totals_mm': totals}, indent=2))


if __name__ == '__main__':
    main()
