"""Scientific plots for the frozen forecast and later blinded verification."""
import datetime as dt
import os
from pathlib import Path
import sys

from collect import ROOT, WIB

os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'data/engine_v2/matplotlib_cache'))
try:
    import matplotlib
except ImportError:
    # Plotting is absent from the bundled runtime. Reuse the existing plotting
    # dependency, without altering it; bundled NumPy remains earlier on sys.path.
    vendor = ROOT / '.forecast-graphs/vendor'
    if not vendor.exists():
        raise RuntimeError('Matplotlib is needed for report plots')
    sys.path.append(str(vendor))
    import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np


def forecast_plots(rows, output, observations=None):
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    for station in sorted({r['station'] for r in rows}):
        group = sorted((r for r in rows if r['station'] == station), key=lambda r: r['time'])
        dates = [dt.datetime.fromtimestamp(r['time'], WIB) for r in group]
        rain_dates = [d - dt.timedelta(minutes=30) for d in dates]
        fig, axes = plt.subplots(3, 1, figsize=(13, 9), sharex=True, layout='constrained')
        fig.suptitle(f'{station}: 3–9 November 2026\nFrozen at 3 Nov 00:00 WIB; GFS run 2 Nov 06:00 UTC', fontsize=15, x=0.07, ha='left')
        for ax, key, label in zip(axes[:2], ('t', 'h'), ('Temperature (°C)', 'Relative humidity (%)')):
            ax.plot(dates, [r['forecast_' + key] for r in group], color='#8b6d48', linestyle='--', linewidth=1.3, label='Raw GFS')
            ax.plot(dates, [r['v2_' + key] for r in group], color='#1769aa', linewidth=1.6, label='Engine v2')
            if observations:
                actual = [observations.get(station, {}).get(r['time'], {}).get(key, np.nan) for r in group]
                ax.plot(dates, actual, color='#222222', linewidth=1.5, label='Measured')
            ax.set_ylabel(label)
            ax.grid(axis='y', color='#dddddd', linewidth=0.6)
            ax.legend(loc='upper right', ncol=3, frameon=False)
        ax = axes[2]
        ax.bar(rain_dates, [r['v2_rain'] for r in group], width=0.032, color='#5b9bd5', alpha=0.75, label='Engine v2 amount')
        ax.step(rain_dates, [r['forecast_rain'] for r in group], color='#8b6d48', linewidth=1.1, where='mid', label='Raw GFS amount')
        if observations:
            actual = [observations.get(station, {}).get(r['time'], {}).get('rain', np.nan) for r in group]
            ax.plot(rain_dates, actual, color='#222222', linewidth=1.5, label='Measured amount')
        ax.set_ylabel('Hourly rain amount (mm)')
        ax.set_ylim(bottom=0)
        ax.grid(axis='y', color='#dddddd', linewidth=0.6)
        ax.legend(loc='upper left', ncol=2, frameon=False)
        if any(r['rain_probability'] is not None for r in group):
            right = ax.twinx()
            right.plot(rain_dates, [r['rain_probability'] * 100 if r['rain_probability'] is not None else np.nan for r in group],
                       color='#38823c', linewidth=1.0, linestyle=':', label='Rain probability')
            right.set_ylim(0, 100)
            right.set_ylabel('P(rain ≥0.28 mm), %', color='#38823c')
            right.spines['top'].set_visible(False)
        axes[-1].xaxis.set_major_locator(mdates.DayLocator(tz=WIB))
        axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d %b', tz=WIB))
        axes[-1].set_xlabel('WIB; rain bars describe the preceding hour, temperature/humidity the interval end')
        axes[-1].set_xlim(dt.datetime(2026, 11, 3, tzinfo=WIB), dt.datetime(2026, 11, 10, tzinfo=WIB))
        message = 'Benchmark measurements deliberately withheld' if observations is None else 'Only available valid measurements are drawn'
        if station in ('X51', 'X67'):
            message += '; raw fallback for this station'
        axes[0].text(0.01, 1.02, message, transform=axes[0].transAxes, fontsize=9, color='#555555')
        fig.savefig(output / f'forecast_{station}.png', dpi=140)
        plt.close(fig)


def validation_plot(validation, output):
    from run import pooled_validation
    stations = ('X50', 'X51', 'X66', 'X67')
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), layout='constrained')
    for ax, variable, metric, units in zip(axes, ('temperature', 'humidity', 'rain'),
                                         ('mae', 'mae', 'rmse'), ('°C MAE', 'percentage points MAE', 'mm RMSE')):
        raw = [pooled_validation(validation, s, variable, False)[metric] for s in stations]
        corrected = [pooled_validation(validation, s, variable, True)[metric] for s in stations]
        positions = np.arange(len(stations))
        ax.bar(positions - 0.18, [v if v is not None else np.nan for v in raw], width=0.34, color='#b19b7e', label='Raw GFS')
        ax.bar(positions + 0.18, [v if v is not None else np.nan for v in corrected], width=0.34, color='#1769aa', label='Engine v2')
        ax.set_xticks(positions, stations)
        ax.set_title(variable.capitalize())
        ax.set_ylabel(units)
        ax.set_ylim(bottom=0)
        for i, value in enumerate(raw):
            if value is None:
                ax.text(i, 0.03, 'No October\nvalidation', ha='center', va='bottom', transform=ax.get_xaxis_transform(), fontsize=8, color='#555555')
        ax.grid(axis='y', color='#dddddd', linewidth=0.6)
        ax.set_axisbelow(True)
    axes[0].legend(frameon=False)
    fig.suptitle('Earlier October validation used for model selection; November benchmark remains unseen', fontsize=13)
    fig.savefig(output / 'validation.png', dpi=140)
    plt.close(fig)
