"""Independent result checks and a balanced comparison with the stronger controls."""
import csv
import datetime as dt
import json
import math
from pathlib import Path
import statistics

import numpy as np

from common import DEFAULT_OUTPUT,HORIZONS,VERSION_DIR,WIB,digest,read_json,save_json,write_csv
from data import SOURCES,read_sources,window_label
from reporting import plotting


def csv_rows(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))


def verify_metrics(folder,predictions_name,scores_name):
    rows=csv_rows(folder/predictions_name);saved=csv_rows(folder/scores_name)
    for score in saved:
        sample=[r for r in rows if r['station']==score['station'] and r['horizon']==score['horizon']]
        actual=np.array([float(r['actual']) for r in sample]);name=score['model']
        if score['amount_available']=='True':
            predicted=np.array([float(r[name+'_amount']) for r in sample]);error=predicted-actual
            values={'mae':np.abs(error).mean(),'rmse':np.sqrt(np.square(error).mean()),'bias':error.mean()}
            if not all(np.isclose(v,float(score[k]),rtol=1e-12,atol=1e-12) for k,v in values.items()):raise ValueError('Independent amount metric check failed')
        if score['probability_available']=='True':
            probability=np.array([float(r[name+'_probability']) for r in sample]);truth=actual>=.28-1e-9
            if not np.isclose(np.square(probability-truth).mean(),float(score['brier']),rtol=1e-12,atol=1e-12):raise ValueError('Independent Brier check failed')
    return rows,saved


def index_scores(rows):return {(r['station'],int(r['horizon']),r['model']):r for r in rows}


def comparisons(saved,regime):
    idx=index_scores(saved);result=[]
    for s in ['X50','X66']:
        for h in HORIZONS:
            get=lambda name,key:float(idx[s,h,name][key])
            v6=get('selected','rmse');gfs=get('raw_gfs','rmse');v2=get('v2_recipe','rmse')
            result.append({'regime':regime,'station':s,'horizon_hours':h,'cases':int(idx[s,h,'selected']['n']),
                'v2_recipe_rmse':v2,'raw_gfs_rmse':gfs,'v6_selected_rmse':v6,
                'v6_lower_rmse_than_v2_recipe':v6<v2,'v6_lower_rmse_than_raw_gfs':v6<gfs,
                'gfs_learner_brier':get('gfs','brier'),'network_rain_brier':get('network_rain','brier'),
                'network_rain_soil_brier':get('network_rain_soil','brier'),'v6_selected_brier':get('selected','brier'),
                'neighbor_rain_brier_better_than_gfs_learner':get('network_rain','brier')<get('gfs','brier'),
                'adding_network_soil_improves_brier':get('network_rain_soil','brier')<get('network_rain','brier')})
    return result


def main():
    output=VERSION_DIR/'output/review_20261106';output.mkdir(parents=True,exist_ok=True)
    data,quality=read_sources()
    static_rows,static=verify_metrics(DEFAULT_OUTPUT,'test_predictions.csv','test_scores.csv')
    rolling_folder=VERSION_DIR/'output/rolling_refresh_20261106'
    rolling_rows,rolling=verify_metrics(rolling_folder,'predictions.csv','scores.csv')
    # Independently check every scored window against raw cumulative gauge
    # endpoints; no soil or neighboring station enters this calculation.
    raw_boundaries={}
    for station,path in SOURCES.items():
        with path.open(encoding='utf-8-sig',newline='') as stream:raw=list(csv.DictReader(stream))
        raw_boundaries[station]={round(int(r['timestamp_ms'])/1000/600)*600:r for r in raw}
    for row in static_rows:
        a=raw_boundaries[row['station']].get(int(row['issue']));b=raw_boundaries[row['station']].get(int(row['end']))
        if a is None or b is None:raise ValueError('Scored window lacks measured gauge boundaries')
        measured=(float(b['rfc'])-float(a['rfc']))*.28
        if not np.isclose(measured,float(row['actual']),rtol=1e-12,atol=1e-12):raise ValueError('Independent gauge total differs')
    candidate=read_json(DEFAULT_OUTPUT/'temperature_humidity_passthrough.json')
    v5=read_json(VERSION_DIR.parent/'v5/output/benchmark_20261103_humidity_v5/frozen_predictions.json')['predictions']
    for a,b in zip(candidate,v5):
        if a['station']!=b['station'] or a['time']!=b['time']:raise ValueError('Passthrough alignment differs')
        for x,y in [('temperature_c','selected_t'),('humidity_pct','selected_h')]:
            if float(a[x]).hex()!=float(b[y]).hex():raise ValueError('Protected component changed')
    availability=read_json(DEFAULT_OUTPUT/'feature_availability.json')
    if not all(r['max_measurement_receipt_used'] is None or r['max_measurement_receipt_used']<=r['issue'] for r in availability):raise ValueError('Future feature receipt detected')
    for path in [DEFAULT_OUTPUT/'training_audit.json',rolling_folder/'training_audit.json']:
        for r in read_json(path):
            if dt.datetime.fromisoformat(r['latest_label_available_wib'] if 'latest_label_available_wib' in r else r['latest_training_label_available_wib'])>=dt.datetime.fromisoformat(r['cutoff_exclusive_wib']):raise ValueError('Training label crosses cutoff')
    table=comparisons(static,'static_pre_october')+comparisons(rolling,'weekly_refresh')
    write_csv(output/'control_comparison.csv',table)
    summary={}
    for regime in ['static_pre_october','weekly_refresh']:
        sample=[r for r in table if r['regime']==regime]
        summary[regime]={'amount_groups_improved_vs_v2_recipe':sum(r['v6_lower_rmse_than_v2_recipe'] for r in sample),
            'amount_groups_improved_vs_raw_gfs':sum(r['v6_lower_rmse_than_raw_gfs'] for r in sample),
            'neighbor_rain_brier_improved_vs_gfs_learner':sum(r['neighbor_rain_brier_better_than_gfs_learner'] for r in sample),
            'adding_network_soil_brier_improved':sum(r['adding_network_soil_improves_brier'] for r in sample)}
    save_json(output/'independent_verification.json',{'static_metric_rows_verified':len(static),'rolling_metric_rows_verified':len(rolling),
        'independent_raw_counter_window_totals_verified':len(static_rows),'temperature_humidity_bitwise_passthrough':len(candidate),
        'feature_availability_records_checked':len(availability),'all_training_labels_before_cutoffs':True,
        'raw_source_hashes':{s:q['sha256'] for s,q in quality.items()},'summary':summary})
    lines=['# V6 review: useful rain evidence, limited forecast gains','',
        '**V6 remains an experimental candidate. The soil hypothesis does not yet establish a consistently more accurate rainfall forecast.**','',
        'Nearby recent rain helps the rain-occurrence models more consistently than adding all soil signals. '
        'Rainfall amount must also be compared with raw GFS; improvement over a dry-period V2 recipe refit alone is insufficient.','',
        '| Evaluation | V6 amount better than V2 recipe | V6 amount better than raw GFS | Nearby-rain Brier better than weather-only learner | Adding network soil improves Brier |',
        '| --- | ---: | ---: | ---: | ---: |']
    for regime,label in [('static_pre_october','Original fixed pre-October fit'),('weekly_refresh','Weekly refresh follow-up')]:
        z=summary[regime]
        lines.append(f"| {label} | {z['amount_groups_improved_vs_v2_recipe']}/8 | {z['amount_groups_improved_vs_raw_gfs']}/8 | {z['neighbor_rain_brier_improved_vs_gfs_learner']}/8 | {z['adding_network_soil_brier_improved']}/8 |")
    lines+=['','The weekly follow-up preserves the original validation-selected routing and model settings. It refits on data available before 20 and 27 October. '
        'This schedule was investigated after inspecting the first results, so it is another development diagnostic, not an untouched validation. '
        'No first-experiment model, selection or score was overwritten.','',
        '![Occurrence-score ablations](rain_occurrence_ablation.png)','',
        '## What the sensors show','',
        '- In valid onset examples, an srm decrease appeared within one hour for 53/65 X50 and 29/35 X66 rain onsets. A decline of at least 5% appeared in 19/65 and 8/35 respectively.',
        '- There are 391 X50 and 96 X66 hourly cases with at least a 5% srm drop and neither checked gauge recording rain nearby. These overlapping cases are unconfirmed wetting, not confirmed fertigation events.',
        '- Both checked gauges were wet in 46 shared hours; X50 alone in 74 and X66 alone in 16. The sites are 3.56 km apart, so neighbor measurements add context without becoming the target station’s rainfall labels.',
        '- Valid cumulative counters recover whole-window rain totals across missing packets. The first experiment recovered 786 overlapping window labels; within-gap rain timing stays unknown.','',
        '![Rain and mirrored soil-wetting examples](wetting_examples.png)','',
        'The mirrored soil index is the percentage srm decline from the beginning of each plotted window. It is only a visual comparison, not rainfall millimetres. '
        'The wet example uses a strong shared gauge event with adequate soil coverage; the dry example uses a large soil decline inside a 12-hour window with both gauges at zero. Neither plot identifies the irrigation cause.','',
        '## Interpretation for the next V6 iteration','',
        'Treat srm/sm as wetting and gauge-consistency signals, and evaluate their incremental value alongside recent local/neighbor rain. '
        'Do not convert a soil decline into a rain amount or replace a dry/missing gauge with its neighbor. '
        'The late-October period was much wetter than the earlier validation: X50 one-hour wet frequency rose from 2.47% to 23.92%, and X66 from 1.10% to 15.06%. '
        'The fixed dry-period fit therefore gives a weak amount control; the separate raw-GFS comparison is essential.','',
        'All feature replays currently assume a one-hour receipt delay. Arrival timestamps and confirmed fertigation logs are absent. '
        'Fresh delivery timing may change near-term usefulness and should be checked before treating these as live forecasts. '
        'E11 also needs clarification: X66 retains numeric raw srm below 5000 while sm is blank. The current models exclude those soil readings; '
        'an unconfirmed raw-ADC-only sensitivity is recorded separately and does not alter these model fits.','',
        '## Files','',
        '- [Original experiment report](../rainfall_candidate_20261106/report.md)',
        '- [Three-month overview](../rainfall_candidate_20261106/rain_soil_patterns_3months.png)',
        '- [Original validation/test ablations](../rainfall_candidate_20261106/test_scores.csv)',
        '- [Weekly follow-up scores](../rolling_refresh_20261106/scores.csv)',
        '- [Control comparison](control_comparison.csv), [independent verification](independent_verification.json)','',
        'V2/V3/V4/V5 remain unchanged. V5 temperature and humidity pass through bit for bit. Nothing was pushed to GitHub.']
    (output/'review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    plt,dates=plotting(output)
    fig,axes=plt.subplots(2,2,figsize=(14,9),sharex=True)
    fig.subplots_adjust(top=.82,bottom=.13,hspace=.32,wspace=.24)
    fig.suptitle('Rain-occurrence prediction: neighbor rain versus added soil signals',fontsize=19,y=.965)
    styles=[('gfs','Weather-only learner','#2464b4','-'),('network_rain','Local + nearby rain','#df7c21','--'),('network_rain_soil','Rain + both soil streams','#238d64',':')]
    for i,(regime,saved) in enumerate([('static_pre_october',static),('weekly_refresh',rolling)]):
        idx=index_scores(saved)
        for j,station in enumerate(['X50','X66']):
            for model,label,color,style in styles:
                axes[i,j].plot(range(4),[float(idx[station,h,model]['brier']) for h in HORIZONS],label=label,color=color,linestyle=style,marker='o',linewidth=1.8)
            axes[i,j].set_title(station+(' · fixed earlier fit' if i==0 else ' · weekly refresh'))
            axes[i,j].set_ylabel('Brier score (lower is better)');axes[i,j].set_xticks(range(4),[str(h) for h in HORIZONS]);axes[i,j].grid(axis='y',alpha=.2)
            if i==1:axes[i,j].set_xlabel('Forecast window (hours)')
    fig.legend(*axes[0,0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.5,.905),ncol=3,frameon=False)
    fig.text(.09,.035,'Same later-period gauge cases. Lower scores are better. Soil is observed only before each issue; later soil response is never a predictor.',fontsize=10,color='#536778')
    fig.savefig(output/'rain_occurrence_ablation.png',dpi=170,facecolor='white');plt.close(fig)
    flags=csv_rows(DEFAULT_OUTPUT/'soil_rain_flags.csv')
    matched=csv_rows(DEFAULT_OUTPUT/'matched_hourly_rain.csv')
    wet_options=sorted([r for r in matched if float(r['X50_rain'])>0 and float(r['X66_rain'])>0],key=lambda r:float(r['X50_rain'])+float(r['X66_rain']),reverse=True)
    wet_time=None
    for row in wet_options:
        centre=int(row['time'])
        cover=[sum(r['soil_ok'] for r in d['records'] if abs(r['time']-centre)<=6*3600)/max(1,sum(abs(r['time']-centre)<=6*3600 for r in d['records'])) for d in data.values()]
        if min(cover)>=.6:wet_time=centre;break
    dry_time=None
    for row in sorted((r for r in flags if r['ambiguous_wetting_no_gauge_rain']=='True'),key=lambda r:float(r['srm_drop_1h_pct']),reverse=True):
        centre=int(row['time']);labels=[window_label(d,centre-6*3600,12) for d in data.values()]
        if all(v is not None and v['amount']==0 for v in labels):dry_time=centre;break
    if wet_time is None or dry_time is None:raise ValueError('No eligible descriptive examples')
    fig,axes=plt.subplots(2,2,figsize=(15,8));fig.subplots_adjust(top=.80,bottom=.16,hspace=.45,wspace=.30)
    fig.suptitle('Rain and mirrored SRM: wetting evidence can have different causes',fontsize=20,y=.96)
    for col,(centre,label) in enumerate([(wet_time,'Shared rain event'),(dry_time,'Soil drop; both gauges dry over 12 hours')]):
        for i,(station,color) in enumerate([('X50','#2464b4'),('X66','#238d64')]):
            d=data[station];raw=[r for r in d['records'] if abs(r['time']-centre)<=6*3600]
            valid=[r for r in raw if r['srm'] is not None];baseline=valid[0]['srm']
            ax=axes[i,col];soil_ax=ax.twinx()
            hours=[r for r in d['hours'].values() if abs(r['time']-centre)<=6*3600 and r['rain'] is not None]
            ax.bar([dt.datetime.fromtimestamp(r['time']-1800,WIB) for r in hours],[r['rain'] for r in hours],width=.025,color=color,alpha=.7,label='Gauge rain')
            soil_ax.plot([dt.datetime.fromtimestamp(r['time'],WIB) for r in raw],[100*(baseline-r['srm'])/baseline if r['srm'] is not None else float('nan') for r in raw],color='#d96c20',linewidth=1.5,label='Mirrored srm decline')
            ax.set_title(station+' · '+label,fontsize=10);ax.set_ylabel('Gauge mm/hour',color=color);soil_ax.set_ylabel('srm decline (%)',color='#d96c20')
            ax.set_ylim(0,max(.56,max((r['rain'] for r in hours),default=0)*1.15));ax.xaxis.set_major_locator(dates.HourLocator(interval=3,tz=WIB));ax.xaxis.set_major_formatter(dates.DateFormatter('%d %b\n%H:%M',tz=WIB));ax.grid(axis='y',alpha=.15)
    fig.text(.08,.045,'Orange rises when srm falls relative to the window’s first valid reading. This is a soil comparison index, not inferred rainfall. E11 soil readings are excluded.',fontsize=10,color='#536778')
    fig.savefig(output/'wetting_examples.png',dpi=170,facecolor='white');plt.close(fig)
    save_json(output/'example_selection.json',{'shared_rain_example_wib':dt.datetime.fromtimestamp(wet_time,WIB).isoformat(),'both_gauges_dry_example_wib':dt.datetime.fromtimestamp(dry_time,WIB).isoformat(),'diagnostic_examples_only':True})
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
