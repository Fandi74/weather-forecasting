"""Scientific plots and an explicit distinction between wetting evidence and rain."""
import csv
import datetime as dt
import math
import os
from pathlib import Path

from common import HORIZONS,WIB,read_json,wib
from data import window_label


def fmt(value,digits=3):
    return '—' if value is None else f'{float(value):.{digits}f}'


def plotting(output):
    os.environ.setdefault('MPLCONFIGDIR',str(Path(output)/'.matplotlib_cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as dates
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    return plt,dates


def report_and_plots(output,data,pattern,flags,test_predictions,test_scores):
    output=Path(output);quality=read_json(output/'source_quality.json');selection=read_json(output/'selection.json')
    coverage=read_json(output/'sample_coverage.json')
    index={(r['station'],r['horizon'],r['model']):r for r in test_scores}
    better_amount=sum(index[s,h,'selected']['rmse']<index[s,h,'v2_recipe']['rmse'] for s in ['X50','X66'] for h in HORIZONS)
    better_prob=sum(index[s,h,'selected']['brier']<index[s,h,'gfs_logistic']['brier'] for s in ['X50','X66'] for h in HORIZONS)
    lines=['# V6 rainfall research: X50 and X66','',
        f'**The validation-selected V6 candidate has lower later-test amount RMSE in {better_amount}/8 station/window groups than the past-only V2 recipe refit, and lower Brier score in {better_prob}/8 groups than the GFS-window logistic control.**','',
        'These are retrospective, hourly-issued 1/6/12/24-hour forecasts. Weekly GFS snapshots are reused between their recorded issue times. '
        'This is a different evaluation from the original once-issued seven-day V2/V5 benchmark; the original final V2 parameters are not applied to earlier test outcomes.','',
        '## Three months of rain and soil patterns','',
        'The supplied station coordinates put X50 and X66 about **3.56 km apart**. Nearby data supplies additional context, while each station retains its own independent gauge labels.','',
        '| Station | Readings | Raw rf total mm | Checked ten-minute mm | Complete-hour mm | Gaps >15 min |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for station,q in quality.items():
        lines.append(f"| {station} | {q['readings']} | {q['raw_recorded_rain_mm']:.2f} | {q['checked_ten_minute_rain_mm']:.2f} | {q['complete_hour_rain_mm']:.2f} | {q['gaps_gt_15_minutes']} |")
    lines+=['','The complete-hour totals cover different valid periods and are not complete three-month rainfall estimates. '
        'Gauge counter boundaries can recover additional whole-window totals when record-ID continuity verifies missing packets; the timings of tips within those gaps remain unknown.','',
        '| Station | Rain onsets with valid 1h soil response | Any srm drop within 1h | Drop ≥5% within 1h | Drop ≥5% with neither gauge wet nearby |',
        '| --- | ---: | ---: | ---: | ---: |']
    for station,p in pattern['station_patterns'].items():
        response=p['onset_soil_response']['60']
        lines.append(f"| {station} | {response['onsets']} | {response['any_drop']} | {response['drop_at_least_5pct']} | {p['ambiguous_wetting_no_gauge_rain_hours']} hourly cases |")
    cross=pattern['cross_station']
    lines+=['','Rain does not produce a measured srm decrease in every eligible episode. Small decreases also occur in dry gauge intervals; a drop alone cannot distinguish rain from manual fertigation, local wetting, sensor noise or a missed gauge event. '
        'No fertigation logs or independent rain truth were supplied, so the possible causes remain unconfirmed. E11 soil faults are excluded even if raw srm is present.','',
        f"Across {cross['matched_complete_hours']} jointly complete gauge hours, both stations were wet in {cross['both_wet_hours']} hours; "
        f"X50 alone was wet in {cross['X50_only_wet_hours']} and X66 alone in {cross['X66_only_wet_hours']}. "
        f"Hourly amount correlation is {cross['hourly_amount_correlation']:.3f}. Time lags and localized rain can affect this overlap; it does not justify copying rainfall quantities.",'',
        '![Daily rain and raw soil pattern](rain_soil_patterns_3months.png)','',
        '## Forecast comparison on the later period','',
        'Training labels and receipts end before 1 October. Model families/components are selected using 1–19 October. '
        'The fixed selection is then scored on 20 October–2 November, with boundary windows purged if their labels arrived too late. '
        'The source dataset was explored retrospectively; this is research evidence, not prospective validation.','',
        '| Station | Window h | Cases | Wet cases | V2 recipe RMSE mm | V6 RMSE mm | GFS logistic Brier | V6 Brier |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for station in ['X50','X66']:
        for h in HORIZONS:
            base=index[station,h,'v2_recipe'];v=index[station,h,'selected'];p=index[station,h,'gfs_logistic']
            lines.append(f"| {station} | {h} | {v['n']} | {v['wet_cases']} | {base['rmse']:.3f} | {v['rmse']:.3f} | {p['brier']:.5f} | {v['brier']:.5f} |")
    lines+=['','RMSE compares expected rainfall amount with measured window totals. Brier compares the probability of at least 0.28 mm anywhere in the whole window with its observed event. '
        'Longer-window probabilities are trained directly, never obtained by adding hourly probabilities. '
        'Overlapping windows share observations and are not independent storms. The counts above are issued forecast cases.','',
        '![Later-period rain amount and probability scores](rainfall_test_metrics.png)','',
        '![Hourly rain observations versus forecasts](rainfall_test_1h_overlays.png)','',
        '## Validation-selected methods','',
        '| Station | Window h | Amount method | Probability method |','| --- | ---: | --- | --- |']
    for station,windows in selection.items():
        for h,choice in windows.items():lines.append(f"| {station} | {h} | {choice['amount_method']} | {choice['probability_method']} |")
    lines+=['','Five LightGBM hurdle families have identical training cases and fixed settings: GFS only; own recent rain; own rain plus soil; own/neighbor rain; own/neighbor rain plus soil. '
        'Continuous srm/sm levels, changes and measurement ages are predictors. Soil readings after issue time never enter features. '
        'The V2 amount control refits its original method on the same past period; separate GFS-logistic and training-climatology controls support window probabilities.','',
        'See [all validation scores](validation_scores.csv) and [all later-test ablations](test_scores.csv). '
        'A validation improvement may not carry over to later dates. Selected amount and probability components are separate estimates; cross-window/joint-distribution coherence is not established.','',
        '## Missing data and gauge evidence','',
        f"{coverage['label_sources'].get('counter_endpoints_packet_continuity',0)} overlapping forecast-window labels were recovered from valid cumulative-counter boundaries and continuous device record IDs. "
        'This count is not a number of independent storms. Reset or discontinuous-device periods remain missing. Neighbor observations and soil drops never create target labels.','',
        'The [soil/rain flags](soil_rain_flags.csv) identify possible gauge disagreements and ambiguous wetting. They are diagnostics, not corrected rainfall measurements. '
        'Any use of future soil response in the pattern analysis is retrospective only and is excluded from the predictive feature schema.','',
        '## Frozen outputs and limitations','',
        '- Final selected rainfall components are refitted using only cases/label receipts before 3 November midnight WIB. The saved initial forecasts are whole windows from the same original 3 November issue and GFS run.',
        '- Later-period scores above use the pre-October training fits, not these final refitted models.',
        '- November replay results are a separate development diagnostic. These hourly updates may use earlier November observations available at their own issue times; they are not forecasts all issued on 3 November.',
        '- V5 temperature and humidity are copied unchanged for all 672 rows. No temperature/humidity learners are fitted.',
        '- Historical GFS publication and observation-plus-one-hour receipt timing are assumptions. Fresh operational GFS updates and confirmed fertigation logs are not present.',
        '- Nothing is pushed to GitHub by this experiment.','',
        'Files: [source quality](source_quality.json), [pattern analysis](pattern_analysis.json), [training audit](training_audit.json), '
        '[feature availability](feature_availability.json), [frozen window forecasts](frozen_window_forecasts.csv), '
        '[November diagnostic](november_diagnostic_scores.csv), [model catalog](model_catalog.json).']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    plt,dates=plotting(output)
    first=min(d['records'][0]['time'] for d in data.values());last=max(d['records'][-1]['time'] for d in data.values())
    start=dt.datetime.fromtimestamp(first,WIB).replace(hour=0,minute=0,second=0,microsecond=0)
    day_times=[];daily={s:[] for s in data}
    t=int(start.timestamp())
    while t<last:
        day_times.append(dt.datetime.fromtimestamp(t,WIB))
        for s in data:
            label=window_label(data[s],t,24);daily[s].append(label['amount'] if label else float('nan'))
        t+=86400
    fig,axes=plt.subplots(3,1,figsize=(15,10),sharex=True)
    fig.subplots_adjust(left=.075,right=.97,top=.86,bottom=.12,hspace=.28)
    fig.text(.075,.95,'X50 and X66: three months of rain and soil response',fontsize=21,weight='bold',color='#17364c')
    fig.text(.075,.904,'6 August–6 November 2026 (WIB). Daily rain uses valid gauge windows; gaps remain missing.',fontsize=11,color='#435e73')
    for station,color,offset in [('X50','#2464b4',-.18),('X66','#238d64',.18)]:
        times=[d+dt.timedelta(days=offset) for d in day_times]
        axes[0].bar(times,daily[station],width=.34,color=color,alpha=.8,label=station)
    axes[0].set_ylabel('Daily gauge rain (mm)');axes[0].legend(ncol=2,frameon=False)
    for ax,station,color in [(axes[1],'X50','#2464b4'),(axes[2],'X66','#238d64')]:
        records=data[station]['records'];times=[];values=[];previous=None
        for r in records:
            if previous is not None and r['time']-previous>900:
                times.append(dt.datetime.fromtimestamp(r['time'],WIB));values.append(float('nan'))
            times.append(dt.datetime.fromtimestamp(r['time'],WIB));values.append(r['srm'] if r['srm'] is not None else float('nan'));previous=r['time']
        ax.plot(times,values,color=color,linewidth=.65)
        ax.set_ylabel(station+' srm (raw)')
        possible=[r for r in flags if r['station']==station and r['possible_gauge_disagreement']]
        for r in possible:ax.axvline(dt.datetime.fromtimestamp(r['time'],WIB),color='#df7c21',alpha=.45,linewidth=.7)
    for ax in axes:
        ax.grid(axis='y',color='#dfe6ed')
        ax.xaxis.set_major_locator(dates.WeekdayLocator(interval=2,tz=WIB));ax.xaxis.set_major_formatter(dates.DateFormatter('%d %b',tz=WIB))
    axes[-1].set_xlabel('Local time, WIB (UTC+7)')
    fig.text(.075,.035,'srm drops indicate wetting evidence. Orange lines: soil drop with local gauge dry and nearby rain; causes are unconfirmed. Raw sensor scales differ by station.',fontsize=9,color='#536778')
    fig.savefig(output/'rain_soil_patterns_3months.png',dpi=170,facecolor='white');plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(13,8));fig.subplots_adjust(top=.84,bottom=.15,hspace=.38,wspace=.28)
    fig.suptitle('Later-period rainfall scores: fixed validation-selected V6',fontsize=18,y=.96)
    for col,station in enumerate(['X50','X66']):
        x=list(range(4));base=[index[station,h,'v2_recipe']['rmse'] for h in HORIZONS];v6=[index[station,h,'selected']['rmse'] for h in HORIZONS]
        axes[0,col].bar([i-.18 for i in x],base,width=.34,color='#2464b4',label='V2 recipe refit')
        axes[0,col].bar([i+.18 for i in x],v6,width=.34,color='#8b3fb0',label='V6 selected')
        axes[0,col].set_title(station+' amount');axes[0,col].set_ylabel('Rain-window RMSE (mm)')
        p=[index[station,h,'gfs_logistic']['brier'] for h in HORIZONS];q=[index[station,h,'selected']['brier'] for h in HORIZONS]
        axes[1,col].bar([i-.18 for i in x],p,width=.34,color='#df7c21',label='GFS-window logistic')
        axes[1,col].bar([i+.18 for i in x],q,width=.34,color='#8b3fb0',label='V6 selected')
        axes[1,col].set_title(station+' probability');axes[1,col].set_ylabel('Brier score');axes[1,col].set_xlabel('Forecast window (hours)')
        for row in range(2):
            axes[row,col].set_xticks(x,[str(h) for h in HORIZONS]);axes[row,col].grid(axis='y',alpha=.2);axes[row,col].set_axisbelow(True);axes[row,col].legend(frameon=False,fontsize=8)
    fig.text(.10,.04,'20 October–2 November retrospective test. Lower is better. Same valid cases per comparison; overlapping windows are correlated.',fontsize=10,color='#536778')
    fig.savefig(output/'rainfall_test_metrics.png',dpi=170,facecolor='white');plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(15,8),sharex=True);fig.subplots_adjust(left=.07,right=.97,top=.84,bottom=.14,hspace=.30)
    fig.text(.07,.95,'Hourly rain: measurements versus V2 recipe and V6',fontsize=21,weight='bold',color='#17364c')
    fig.text(.07,.90,'20 October–2 November 2026. Each prediction is issued before its own one-hour window.',fontsize=11,color='#435e73')
    for ax,station in zip(axes,['X50','X66']):
        sample=sorted((r for r in test_predictions if r['station']==station and r['horizon']==1),key=lambda r:r['issue'])
        times=[dt.datetime.fromtimestamp(r['issue']+1800,WIB) for r in sample]
        ax.bar(times,[r['actual'] for r in sample],width=.027,color='#151b22',label='Gauge amount',alpha=.85)
        ax.plot(times,[r['v2_recipe_amount'] for r in sample],color='#2464b4',linewidth=1.2,label='V2 recipe refit')
        ax.plot(times,[r['selected_amount'] for r in sample],color='#8b3fb0',linewidth=1.3,label='V6 selected')
        ax.set_ylabel(station+' rain (mm/hour)');ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.2);ax.legend(ncol=3,frameon=False)
        ax.xaxis.set_major_locator(dates.DayLocator(interval=2,tz=WIB));ax.xaxis.set_major_formatter(dates.DateFormatter('%d %b',tz=WIB))
    axes[-1].set_xlabel('Local time, WIB (UTC+7)')
    fig.text(.07,.035,'Missing gauge windows are omitted, not treated as zero. Weekly GFS is shared by both methods. Soil/neighbor data is restricted to receipt before each issue.',fontsize=9,color='#536778')
    fig.savefig(output/'rainfall_test_1h_overlays.png',dpi=170,facecolor='white');plt.close(fig)
