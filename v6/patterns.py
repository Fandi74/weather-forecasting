"""Descriptive rain/soil evidence. Future soil response is diagnostic only."""
import bisect
import math
import statistics

from common import TIP_MM, wib
from data import soil_change


def analyze(data):
    station_stats,hourly_flags,onset_rows={},{},[]
    for station,values in data.items():
        records=values['records']; other=data['X66' if station=='X50' else 'X50']
        adjacent=[]
        for a,b in zip(records,records[1:]):
            nominal=round(b['time']/600)*600
            interval=values['intervals'].get(nominal)
            if interval and a['soil_ok'] and b['soil_ok'] and b['time']-a['time']<=900 and (a['rid'] is None or b['rid'] is None or b['rid']>=a['rid']):
                adjacent.append({'wet':interval['amount']>=TIP_MM-1e-9,'drop':b['srm']<a['srm']})
        wet=[r for r in adjacent if r['wet']]; dry=[r for r in adjacent if not r['wet']]
        flags=[]
        for end,hour in sorted(values['hours'].items()):
            change=soil_change(values,end+90,60)
            if change is None or hour['rain'] is None: continue
            nearby=[other['hours'].get(end+k*3600) for k in [-1,0,1]]
            neighbor_complete=all(r and r['rain'] is not None for r in nearby)
            neighbor_rain=sum(r['rain'] for r in nearby) if neighbor_complete else None
            flags.append({'station':station,'time':end,'time_wib':wib(end),'own_rain_mm':hour['rain'],
                'srm_drop_1h_pct':change['drop_pct'],'sm_change_1h':change['sm_change'],
                'neighbor_rain_within_1h_mm':neighbor_rain,'significant_soil_drop':change['drop_pct']>=5,
                'possible_gauge_disagreement':change['drop_pct']>=5 and hour['rain']==0 and neighbor_rain is not None and neighbor_rain>=TIP_MM-1e-9,
                'ambiguous_wetting_no_gauge_rain':change['drop_pct']>=5 and hour['rain']==0 and neighbor_rain==0})
        hourly_flags[station]=flags
        # Rain onset requires six known dry intervals before the wet interval.
        for end,interval in sorted(values['intervals'].items()):
            if interval['amount']<TIP_MM-1e-9: continue
            prior=[values['intervals'].get(end-k*600) for k in range(1,7)]
            if not all(p is not None and p['amount']==0 for p in prior): continue
            j=bisect.bisect_right(values['times'],end-600+90)-1
            if j<0 or abs(records[j]['time']-(end-600))>90 or not records[j]['soil_ok']: continue
            before=records[j]
            for lag in [10,30,60,180]:
                follow=[r for r in records[j+1:] if end-90<=r['time']<=end+lag*60+90]
                if len(follow)<lag//10 or not all(r['soil_ok'] for r in follow): continue
                if any(b['time']-a['time']>900 or (a['rid'] is not None and b['rid'] is not None and b['rid']<a['rid']) for a,b in zip([before]+follow,follow)): continue
                minimum=min(r['srm'] for r in follow)
                onset_rows.append({'station':station,'time':end,'time_wib':wib(end),'response_minutes':lag,
                    'max_srm_drop_pct':100*(before['srm']-minimum)/before['srm']})
        responses={}
        for lag in [10,30,60,180]:
            sample=[r for r in onset_rows if r['station']==station and r['response_minutes']==lag]
            responses[str(lag)]={'onsets':len(sample),'any_drop':sum(r['max_srm_drop_pct']>0 for r in sample),
                'drop_at_least_1pct':sum(r['max_srm_drop_pct']>=1 for r in sample),
                'drop_at_least_5pct':sum(r['max_srm_drop_pct']>=5 for r in sample)}
        station_stats[station]={'checked_wet_10min_with_soil':len(wet),'wet_10min_immediate_srm_drop':sum(r['drop'] for r in wet),
            'checked_dry_10min_with_soil':len(dry),'dry_10min_immediate_srm_drop':sum(r['drop'] for r in dry),
            'onset_soil_response':responses,'hourly_pairs_for_soil_check':len(flags),
            'significant_drop_hours':sum(r['significant_soil_drop'] for r in flags),
            'possible_gauge_disagreement_hours':sum(r['possible_gauge_disagreement'] for r in flags),
            'ambiguous_wetting_no_gauge_rain_hours':sum(r['ambiguous_wetting_no_gauge_rain'] for r in flags)}
    common=[]
    for time,a in sorted(data['X50']['hours'].items()):
        b=data['X66']['hours'].get(time)
        if a['rain'] is not None and b is not None and b['rain'] is not None:
            common.append({'time':time,'X50_rain':a['rain'],'X66_rain':b['rain']})
    both=sum(r['X50_rain']>=TIP_MM-1e-9 and r['X66_rain']>=TIP_MM-1e-9 for r in common)
    wet50=sum(r['X50_rain']>=TIP_MM-1e-9 for r in common);wet66=sum(r['X66_rain']>=TIP_MM-1e-9 for r in common)
    cross={'matched_complete_hours':len(common),'X50_wet_hours':wet50,'X66_wet_hours':wet66,'both_wet_hours':both,
        'X50_only_wet_hours':wet50-both,'X66_only_wet_hours':wet66-both,
        'X50_total_mm_matched':sum(r['X50_rain'] for r in common),'X66_total_mm_matched':sum(r['X66_rain'] for r in common),
        'hourly_amount_correlation':statistics.correlation([r['X50_rain'] for r in common],[r['X66_rain'] for r in common])}
    return {'station_patterns':station_stats,'cross_station':cross,
        'interpretation':'Soil drops support wetting evidence; neither a drop nor nearby rain confirms rain at the target or provides rainfall mm. No labels are mirrored or imputed.'},[r for flags in hourly_flags.values() for r in flags],onset_rows,common
