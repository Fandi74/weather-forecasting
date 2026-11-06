"""Development reports and humidity-only comparison plots."""
import datetime as dt
import json
import math
import os
from pathlib import Path

from common import WIB, read_json


def plotting(output):
    os.environ.setdefault('MPLCONFIGDIR', str(Path(output) / '.matplotlib_cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    return plt, mdates


def build_report(output):
    import csv
    output = Path(output)
    selection = read_json(output / 'selection.json')
    support = read_json(output / 'station_support.json')['X66']
    with (output / 'validation_scores.csv').open(encoding='utf-8-sig', newline='') as stream:
        scores = [r for r in csv.DictReader(stream) if r['scope'] == 'combined_later_october']
    lines = ['# V5 humidity development experiment', '',
        '**Temperature, rainfall amount and rain probability are exact V2 passthroughs for all 672 forecast rows.**', '',
        'V5 combines V2 humidity with humidity-only CatBoost and LightGBM learners based on V3/V4 designs. '
        'Both new learners target `hsht` residuals against GFS. The original V2/V3/V4 models remain unchanged.', '',
        f"X66 has {support['pre_october_training_rows']} pre-October exact-run training rows, "
        f"{support['october_calibration_rows']} October calibration/validation cases and {support['final_training_rows']} final pre-November training rows. "
        'Latest/rolling SHT history expires after six hours. The frozen issue has older readings, so expired values remain missing.', '',
        '## Later-October development results', '',
        'Base learner validation fits use labels/assumed arrivals before 1 October. Ensemble weights at the 20 and 27 October issues use only earlier available labels. '
        'These later-week results select the combination; they are not an untouched final test. V2 method recipes had also been selected on October in earlier work.', '',
        '| Family | Cases | MAE pp | RMSE pp | Bias pp |', '| --- | ---: | ---: | ---: | ---: |']
    for row in scores:
        lines.append(f"| {row['family']} | {row['n']} | {float(row['mae']):.3f} | {float(row['rmse']):.3f} | {float(row['bias']):+.3f} |")
    lines += ['', f"Selected family: **{selection['family']}**. Best-family MAE improvement over V2: **{selection['improvement_pp']:.3f} pp**. "
        'A replacement needs at least 0.5 pp improvement; otherwise V5 retains V2 humidity.', '',
        'Final combination after fitting its parameters to all eligible October out-of-time base predictions:', '',
        '```json', json.dumps(selection['model'], indent=2), '```', '',
        'A component may receive zero weight if calibration does not support it. Each learned convex combination has nonnegative weights summing to one; '
        'an optional global humidity offset is fitted only on earlier calibration outcomes. Final humidity is clipped to [0,100].', '',
        '## Frozen X66 humidity forecast', '', '![V2 through V5 humidity forecasts](X66_humidity_forecasts_V2_V3_V4_V5.png)', '',
        '## Evaluation boundaries', '',
        '- X50/X51 have no historical hsht column. X67 has no accepted independent pre-cutoff history. Their V5 humidity remains V2 with explicit support status.',
        '- No November labels are used to fit learners, ensemble weights or select the family.',
        '- The November outcomes already discussed in chat make a later 3–6 November comparison a development diagnostic. Confirmation needs later observations unseen when this candidate is sealed.',
        '- Historical GFS publication and measurement-plus-one-hour receipt timings remain assumptions.',
        '- No temperature or rainfall learners are fitted. No sm/srm features are enabled; rainfall work is reserved for V6.',
        '- No GitHub publication is performed.', '',
        'Audits: [training](training_audit.json), [ensemble calibration](ensemble_calibration_audit.json), '
        '[feature availability](feature_availability.json), [station support](station_support.json), '
        '[selection](selection.json), [original reference locks](reference_locks.json).']
    (output / 'training_report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    plt, mdates = plotting(output)
    rows = [r for r in read_json(output / 'frozen_predictions.json')['predictions'] if r['station'] == 'X66']
    times = [dt.datetime.fromtimestamp(r['time'], WIB) for r in rows]
    fig, ax = plt.subplots(figsize=(15, 5.5))
    for name, key, color, style in [('V2', 'v2_h', '#2464b4', '-'), ('V3', 'v3_h', '#df7c21', '--'),
                                  ('V4', 'v4_h', '#238d64', ':'), ('V5 humidity', 'selected_h', '#8b3fb0', '-')]:
        ax.plot(times, [r[key] for r in rows], color=color, linestyle=style, linewidth=2.5 if name.startswith('V5') else 1.5, label=name)
    ax.set_title('X66 humidity: frozen V2, V3, V4 and new V5 candidate', fontsize=17, loc='left', pad=16)
    ax.set_ylabel('Relative humidity (%)')
    ax.set_ylim(0, 103)
    ax.xaxis.set_major_locator(mdates.DayLocator(tz=WIB))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b', tz=WIB))
    ax.set_xlabel('Local time, WIB (UTC+7)')
    ax.grid(axis='y', color='#dfe6ed')
    ax.legend(ncol=4, frameon=False, loc='lower left')
    fig.subplots_adjust(left=.065, right=.985, bottom=.20, top=.86)
    fig.text(.065, .045, 'Original 3 November issue / 2 November 06 UTC GFS run. V5 changes humidity only; temperature and rain retain V2.', fontsize=10, color='#536778')
    fig.savefig(output / 'X66_humidity_forecasts_V2_V3_V4_V5.png', dpi=170, facecolor='white')
    plt.close(fig)


def score_report(output, rows, scores, metadata):
    output = Path(output)
    indexed = {r['model']: r for r in scores}
    improvement = indexed['V2']['mae'] - indexed['V5']['mae']
    lines = ['# V5: X66 humidity development comparison', '',
        '**This is a post-development comparison with previously revealed November observations, not an untouched blind test.**', '',
        'Humidity reference: `hsht`. Temperature, rainfall and rain probability remain exactly the frozen V2 outputs. '
        'No November observations entered humidity fitting, ensemble calibration or family selection.', '',
        '| Model | Matched hours | MAE pp | RMSE pp | Bias pp | Correlation |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for r in scores:
        lines.append(f"| {r['model']} | {r['n']} | {r['mae']:.3f} | {r['rmse']:.3f} | {r['bias']:+.3f} | {r['correlation']:.3f} |")
    lines += ['', f'V5 MAE change relative to V2: **{improvement:+.3f} pp improvement**. '
        'A negative value means V5 is worse. This sample does not establish performance across other seasons or stations.', '',
        '![X66 observed humidity and all four forecasts](X66_humidity_actual_V2_V3_V4_V5.png)', '',
        'The new CatBoost/LightGBM component rows are trained within V5 against hsht. V3/V4 rows remain the original frozen versions.', '',
        f"Source period: {metadata['first_observation_wib']} through {metadata['last_observation_wib']}. "
        'Hourly targets use the nearest valid SHT reading within five minutes, with no filling of missing observations.', '',
        'The candidate was sealed before this scoring command opened the supplied export. Earlier outcomes had already been discussed in chat. '
        'The prospective confirmation boundary is recorded with the frozen predictions; observations after that boundary can provide a separate later check.', '',
        'Nothing was pushed to GitHub. All original and V5 immutable file hashes verify after scoring.']
    (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    plt, mdates = plotting(output)
    fig, axes = plt.subplots(2, 1, figsize=(15, 8), sharex=True)
    fig.subplots_adjust(left=.075, right=.97, top=.80, bottom=.15, hspace=.28)
    fig.text(.075, .95, 'X66 humidity: observations versus V2, V3, V4 and V5', fontsize=21, weight='bold', color='#17364c')
    fig.text(.075, .902, '3–6 November 2026 (WIB). Development diagnostic; no November labels used for fitting or selection.', fontsize=11, color='#435e73')
    times = [dt.datetime.fromtimestamp(r['time'], WIB) for r in rows]
    axes[0].plot(times, [r['actual_hsht'] for r in rows], color='#151b22', linewidth=2, marker='o', markersize=3, label='Measured hsht', zorder=8)
    for name, color, style in [('V2', '#2464b4', '-'), ('V3', '#df7c21', '--'), ('V4', '#238d64', ':'), ('V5', '#8b3fb0', '-')]:
        values = [r[name + '_h'] for r in rows]
        axes[0].plot(times, values, color=color, linestyle=style, linewidth=2.5 if name == 'V5' else 1.5, label=name)
        axes[1].plot(times, [r[name + '_h'] - r['actual_hsht'] for r in rows], color=color, linestyle=style, linewidth=2 if name == 'V5' else 1.4)
    fig.legend(*axes[0].get_legend_handles_labels(), loc='upper left', bbox_to_anchor=(.072, .865), ncol=5, frameon=False)
    axes[0].set_ylabel('Relative humidity (%)')
    minimum = min([r['actual_hsht'] for r in rows] + [r[name + '_h'] for r in rows for name in ['V2','V3','V4','V5']])
    axes[0].set_ylim(max(0, math.floor((minimum - 3)/5)*5), 103)
    axes[0].set_title('MAE: ' + ' / '.join(f"{name} {indexed[name]['mae']:.2f}" for name in ['V2','V3','V4','V5']) + ' pp', loc='left', fontsize=10)
    axes[1].set_ylabel('Forecast − measured (pp)')
    axes[1].axhline(0, color='#151b22', linewidth=1)
    axes[1].set_xlabel('Local time, WIB (UTC+7)')
    for ax in axes:
        ax.grid(axis='y', color='#dfe6ed')
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 12], tz=WIB))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b\n%H:%M', tz=WIB))
    fig.text(.075, .045, 'V5 temperature, rain amount and rain probability are unchanged from V2 across all 672 forecast rows. Confirm humidity gains on later unseen data.', fontsize=10, color='#536778')
    fig.savefig(output / 'X66_humidity_actual_V2_V3_V4_V5.png', dpi=170, facecolor='white')
    plt.close(fig)
