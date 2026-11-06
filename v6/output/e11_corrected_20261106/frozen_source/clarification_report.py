"""Reports for the threshold-flag correction and availability sensitivity."""
import csv
from pathlib import Path

from common import VERSION_DIR,write_csv
from reporting import plotting


def read_scores(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))


def write_report(output,new_scores,pattern,profile):
    old=read_scores(VERSION_DIR/'output/rolling_refresh_20261106/scores.csv')
    cases={'original_1h':{(r['station'],int(r['horizon']),r['model']):r for r in old}}
    for name in ['raw_srm_1h','raw_srm_timestamp']:
        cases[name]={(r['station'],r['horizon'],r['model']):r for r in new_scores if r['scenario']==name}
    table=[]
    for scenario,idx in cases.items():
        for station in ['X50','X66']:
            for horizon in [1,6,12,24]:
                selected=idx[station,horizon,'selected'];soil=idx[station,horizon,'network_rain_soil']
                rain=idx[station,horizon,'network_rain']
                table.append({'scenario':scenario,'station':station,'horizon':horizon,'cases':int(selected['n']),
                    'selected_rmse':float(selected['rmse']),'selected_brier':float(selected['brier']),
                    'network_rain_brier':float(rain['brier']),'network_rain_soil_brier':float(soil['brier'])})
    write_csv(output/'comparison.csv',table)
    lines=['# V6 update: E11 threshold flags and CSV timestamp assumptions','',
        'E11 is treated as the user-described threshold flag. A finite positive raw srm value is retained under E11, while sm remains unavailable. '
        'Rainfall labels, original validation routing, model parameters and scoring case IDs are unchanged.','',
        '## UTC time versus availability','',
        'The CSV timestamp_ms is a Unix-millisecond timestamp. The time_WIB column is the same assigned instant displayed in UTC+7. '
        'For example, X66 timestamp 1786008008000 is 6 August 2026 09:20:08 UTC, or 16:20:08 WIB. '
        'The CSV does not identify whether that assigned time came from device measurement or server receipt, and it has no separate arrival timestamp.','',
        'The earlier one-hour receipt delay was a conservative assumption, not a fact established by the file. '
        'This update holds rainfall label availability and case partitions fixed, and compares past features under two assumptions: availability at assigned CSV time, or one hour later. '
        'The immediate-time case is a sensitivity, not confirmation of live delivery latency. Even there, no reading timestamped after the forecast issue is used.','',
        '## Threshold handling','',
        '| Station | E11 rows | Numeric raw srm present | Raw range during E11 | Unflagged srm below 7000 |',
        '| --- | ---: | ---: | --- | ---: |']
    for station,p in profile.items():
        span='—' if p['E11_raw_range'] is None else f"{p['E11_raw_range'][0]:.0f}–{p['E11_raw_range'][1]:.0f}"
        lines.append(f"| {station} | {p['E11_rows']} | {p['E11_raw_srm_present']} | {span} | {p['unflagged_raw_below_7000']} |")
    lines+=['','The approximate 7000 threshold is not hard-coded or used to recompute flags. Device flags and raw-value presence determine handling. '
        'This restores 143 X66 raw ADC readings. X50 missing raw ADC readings stay missing; no zero or inferred sm value replaces them.','',
        'With this correction, the valid one-hour soil-response examples are:','',
        '| Station | Rain onsets checked | Any srm decline within one hour | Decline at least 5% |',
        '| --- | ---: | ---: | ---: |']
    for station,p in pattern['station_patterns'].items():
        r=p['onset_soil_response']['60']
        lines.append(f"| {station} | {r['onsets']} | {r['any_drop']} | {r['drop_at_least_5pct']} |")
    lines+=['','These are retrospective soil responses, not forecast inputs from the future. The correction does not make every rain episode show a soil drop, or identify the cause of every drop without rain.','',
        '## Fixed-routing rainfall forecast comparison','',
        '| Station | Window h | Old selected RMSE | Raw-srm selected RMSE, +1h | Raw-srm selected RMSE, CSV time |',
        '| --- | ---: | ---: | ---: | ---: |']
    lookup={(r['scenario'],r['station'],r['horizon']):r for r in table}
    for s in ['X50','X66']:
        for h in [1,6,12,24]:
            values=[lookup[name,s,h]['selected_rmse'] for name in cases]
            lines.append(f'| {s} | {h} | '+' | '.join(f'{x:.3f}' for x in values)+' |')
    lines+=['','Some selected probability/amount routes are weather-only or climatology controls, so those outputs do not change with soil policy or timing. '
        'The figure below directly compares the network-rain-plus-soil learner to isolate these input assumptions.','',
        '![Rain probability under E11 and timing policies](rain_probability_e11_timing.png)','',
        'The same two weekly fit dates, same rainfall targets and same later-period cases are used. '
        'Only soil-field handling and then-available feature timing vary. Model routing is not reselected using the later outcomes. '
        'This follows prior inspection of those outcomes and is development evidence, not an untouched test.','',
        '## Models and files','',
        '- The E11-corrected final models with the conservative timing assumption are in [raw_srm_1h/models/final/](raw_srm_1h/models/final/).',
        '- CSV-time models are timing-sensitivity fits, not a confirmed live-production configuration.',
        '- [Comparison table](comparison.csv), [restored pattern analysis](corrected_pattern_analysis.json), [threshold profile](threshold_profile.json).',
        '- [Training audit](training_audit.json) and [feature availability](feature_availability.json) record the cutoffs and timestamps.',
        '- Temperature/humidity and every prior frozen experiment remain unchanged. No GitHub publication is performed.']
    (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    plt,_=plotting(output)
    fig,axes=plt.subplots(1,2,figsize=(14,6),sharex=True)
    fig.subplots_adjust(left=.07,right=.97,top=.76,bottom=.20,wspace=.22)
    fig.suptitle('V6: raw SRM threshold correction and input-timing sensitivity',fontsize=18,y=.95)
    styles=[('original_1h','Old E11 exclusion; +1h','#2464b4','-'),('raw_srm_1h','Raw SRM retained; +1h','#df7c21','--'),('raw_srm_timestamp','Raw SRM; at CSV timestamp','#8b3fb0',':')]
    for ax,station in zip(axes,['X50','X66']):
        for name,label,color,style in styles:
            ax.plot(range(4),[lookup[name,station,h]['network_rain_soil_brier'] for h in [1,6,12,24]],label=label,color=color,linestyle=style,marker='o',linewidth=1.8)
        ax.set_title(station);ax.set_xticks(range(4),['1','6','12','24']);ax.set_xlabel('Forecast window (hours)')
        ax.set_ylabel('Brier score (lower is better)');ax.grid(axis='y',alpha=.2)
    fig.legend(*axes[0].get_legend_handles_labels(),loc='upper center',bbox_to_anchor=(.5,.865),ncol=3,frameon=False,fontsize=9)
    fig.text(.07,.055,'Network-rain-plus-soil learner; identical later-period cases. CSV-time availability is an assumption. No future timestamp is used.',fontsize=10,color='#536778')
    fig.savefig(output/'rain_probability_e11_timing.png',dpi=170,facecolor='white');plt.close(fig)
    summary={}
    for name in ['raw_srm_1h','raw_srm_timestamp']:
        summary[name]={'network_soil_brier_better_than_original_groups':sum(lookup[name,s,h]['network_rain_soil_brier']<lookup['original_1h',s,h]['network_rain_soil_brier'] for s in ['X50','X66'] for h in [1,6,12,24]),
            'selected_rmse_better_than_original_groups':sum(lookup[name,s,h]['selected_rmse']<lookup['original_1h',s,h]['selected_rmse'] for s in ['X50','X66'] for h in [1,6,12,24])}
    import json
    print(json.dumps({'comparison_summary':summary},indent=2),flush=True)
