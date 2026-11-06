"""E11 correction and explicit timestamp-availability sensitivity for V6.

Rainfall labels, case IDs, original validation routing and learner settings stay
fixed. This is retrospective development work; no new blind-test claim is made.
"""
import bisect
import csv
import datetime as dt
from pathlib import Path
import re
import shutil

from common import (DEFAULT_OUTPUT,FREEZE,HORIZONS,VERSION_DIR,WIB,digest,no_overwrite,
    read_json,save_json,verify_references,wib,write_csv)
from data import KNOWN_CODES,SOURCES,number,read_sources,soil_change
from experiment import apply_selection,case_signature,predict_all,scores
from features import FAMILIES,RAIN,SOIL,all_features
from learner import fit
from patterns import analyze
from samples import build_samples

OUTPUT=VERSION_DIR/'output/e11_corrected_20261106'


def keep_raw_adc(data,raw_by_station):
    """E11 is a threshold flag; preserve real ADC values, never invent sm."""
    result={}
    for station,original in data.items():
        records=[]
        for old in original['records']:
            row=dict(old)
            raw=raw_by_station[station][old['time']]
            codes=set(re.findall(r'\bE\d+\b',raw.get('error','').upper()))
            adc=number(raw.get('srm'))
            if 'E11' in codes and not (codes-KNOWN_CODES):
                valid=adc is not None and adc>0
                row.update(srm=adc if valid else None,soil_ok=valid,sm=None)
            records.append(row)
        result[station]={**original,'records':records}
    return result


class TimingHistory:
    def __init__(self,data,delay_seconds):
        if delay_seconds not in [0,3600]:raise ValueError('Explicit 0h/1h sensitivity only')
        self.data=data;self.delay=delay_seconds;self.cache={};self.audit=[]
        self.rain={s:sorted([dict(p,feature_available_at=p['observed_at']+delay_seconds)
            for p in d['hours'].values() if p['rain'] is not None],key=lambda p:p['feature_available_at']) for s,d in data.items()}
        self.arrivals={s:[p['feature_available_at'] for p in rows] for s,rows in self.rain.items()}

    def get(self,station,issue):
        key=(station,issue)
        if key in self.cache:return self.cache[key]
        data=self.data[station];used=[];measured=[]
        rain=self.rain[station][:bisect.bisect_right(self.arrivals[station],issue)]
        latest=rain[-1] if rain else None
        values={k:None for k in RAIN+SOIL}
        age=(issue-latest['observed_at'])/3600 if latest else None
        values['rain_age_hours']=age;recent=latest is not None and age<=6
        def use_rain(point):
            used.append(point['feature_available_at']);measured.append(point['observed_at'])
            return point['rain']
        if recent:values['rain_latest_mm']=use_rain(latest)
        by_time={p['time']:p for p in rain}
        for hours in [3,6]:
            points=[by_time.get(latest['time']-k*3600) for k in range(hours)] if recent else []
            good=[p for p in points if p is not None]
            observations=[use_rain(p) for p in good]
            values[f'rain_{hours}h_coverage']=len(good)/hours
            values[f'rain_{hours}h_mm']=sum(observations) if len(good)==hours else None
        wet=[p for p in rain if p['rain']>=.28-1e-9 and issue-p['observed_at']<=72*3600]
        if wet:
            values['last_wet_age_hours']=(issue-wet[-1]['observed_at'])/3600;use_rain(wet[-1])
        i=bisect.bisect_right(data['times'],issue-self.delay)-1
        while i>=0 and not data['records'][i]['soil_ok']:i-=1
        soil=data['records'][i] if i>=0 else None
        soil_age=(issue-soil['time'])/3600 if soil else None
        values['soil_age_hours']=soil_age
        if soil is not None and soil_age<=6:
            used.append(soil['time']+self.delay);measured.append(soil['time'])
            values.update(srm_latest=soil['srm'],sm_latest=soil['sm'])
            for minutes in [30,60,180]:
                change=soil_change(data,soil['time'],minutes)
                if change is not None:
                    values[f'srm_drop_{minutes}m_pct']=change['drop_pct']
                    if minutes==60:values['sm_change_60m']=change['sm_change']
                    if minutes==180:values['srm_range_180m_pct']=change['srm_range_pct']
        if used and (max(used)>issue or max(measured)>issue):raise ValueError('Future observation used')
        self.audit.append({'station':station,'issue':issue,'assumed_delay_seconds':self.delay,
            'max_assumed_availability_used':max(used) if used else None,
            'max_csv_timestamp_used':max(measured) if measured else None})
        self.cache[key]=values
        return values


def replace_features(rows,history):
    return [{**r,'features':all_features(r['station'],r['issue'],r['horizon'],r['gfs_source_issue'],r['hourly_forecasts'],history)} for r in rows]


def verify_prior():
    result={'earlier_versions':verify_references()}
    for folder,lock_name in [(DEFAULT_OUTPUT,'candidate_lock.json'),(VERSION_DIR/'output/rolling_refresh_20261106','rolling_lock.json')]:
        lock=read_json(folder/lock_name)
        for relative,expected in lock['immutable_files'].items():
            if digest(folder/relative)!=expected:raise ValueError('Prior experiment changed: '+relative)
        result[folder.name]={'lock_sha256':digest(folder/lock_name),'files':len(lock['immutable_files'])}
    return result


def build():
    no_overwrite(OUTPUT);before=verify_prior()
    strict,quality=read_sources();raw={}
    for station,path in SOURCES.items():
        with path.open(encoding='utf-8-sig',newline='') as stream:
            raw[station]={int(r['timestamp_ms'])/1000:r for r in csv.DictReader(stream)}
    corrected=keep_raw_adc(strict,raw)
    pack=build_samples(strict)
    selection=read_json(DEFAULT_OUTPUT/'selection.json');routing_hash=digest(DEFAULT_OUTPUT/'selection.json')
    OUTPUT.mkdir(parents=True)
    save_json(OUTPUT/'protocol.json',{'version':'engine_v6_rainfall.2','status':'Post-clarification retrospective development comparison',
        'E11_policy':'Retain available finite positive raw srm under the user-described threshold flag; keep missing/flagged sm unavailable. Missing raw ADC is never imputed.',
        'numeric_threshold_hardcoded':False,'user_threshold_estimate':'Approximately 7000, unconfirmed; existing E11 flags are respected without recomputing a cutoff',
        'timestamp_interpretation':'CSV-assigned timestamp; measurement versus server-arrival semantics not confirmed',
        'timing_cases_seconds':[3600,0],'zero_delay_status':'Sensitivity assuming availability at the assigned CSV time, not a confirmed delivery fact',
        'rain_labels_and_case_partitions':'Original conservative label receipt and identical case IDs retained to isolate feature changes',
        'model_routing_sha256':routing_hash,'routing_and_hyperparameters_changed':False,'prior_results_used_for_model_selection':False})
    profile={}
    for station,rows in raw.items():
        flagged=[r for r in rows.values() if 'E11' in r['error'].split()]
        flagged_adc=[number(r['srm']) for r in flagged if number(r['srm']) is not None]
        unflagged=[number(r['srm']) for r in rows.values() if 'E11' not in r['error'].split() and number(r['srm']) is not None]
        profile[station]={'E11_rows':len(flagged),'E11_raw_srm_present':len(flagged_adc),
            'E11_raw_range':[min(flagged_adc),max(flagged_adc)] if flagged_adc else None,
            'unflagged_raw_range':[min(unflagged),max(unflagged)],'unflagged_raw_below_7000':sum(v<7000 for v in unflagged)}
    save_json(OUTPUT/'threshold_profile.json',profile)
    pattern,flags,onsets,_=analyze(corrected)
    save_json(OUTPUT/'corrected_pattern_analysis.json',pattern);write_csv(OUTPUT/'soil_rain_flags.csv',flags)
    write_csv(OUTPUT/'rain_onset_soil_response.csv',onsets)
    old_root=VERSION_DIR/'output/rolling_refresh_20261106/models'
    cutoffs=[dt.datetime(2026,10,d,tzinfo=WIB).timestamp() for d in [20,27]]
    audit=[];histories={};all_scores=[]
    for scenario,delay in [('raw_srm_1h',3600),('raw_srm_timestamp',0)]:
        history=TimingHistory(corrected,delay);histories[scenario]=history
        predictions=[]
        for i,cutoff in enumerate(cutoffs):
            next_cutoff=cutoffs[i+1] if i+1<len(cutoffs) else FREEZE
            train_original=[r for r in pack['samples'] if r['issue']<cutoff and r['label_available_at']<cutoff]
            test_original=[r for r in pack['samples'] if r['stage']=='test' and cutoff<=r['issue']<next_cutoff]
            train=replace_features(train_original,history);test=replace_features(test_original,history)
            date=dt.datetime.fromtimestamp(cutoff,WIB).strftime('%Y%m%d')
            source=old_root/date;destination=OUTPUT/scenario/'models'/date
            catalog={}
            destination.mkdir(parents=True)
            shutil.copyfile(source/'baselines.json',destination/'baselines.json')
            for family in FAMILIES:
                needs_fit=(delay==0 and family!='gfs') or (delay==3600 and i==1 and family in ['local_rain_soil','network_rain_soil'])
                if needs_fit:
                    print(f'{scenario} {date}: fit {family}, {len(train)} prior windows',flush=True)
                    catalog[family]=fit(train,family,destination/family)
                else:
                    shutil.copytree(source/family,destination/family)
                    catalog[family]=read_json(destination/family/'descriptor.json')
                audit.append({'scenario':scenario,'fit_cutoff_exclusive_wib':wib(cutoff),'family':family,
                    'model_refitted':needs_fit,'training_cases':len(train),'training_case_signature':case_signature(train),
                    'max_training_label_available_wib':wib(max(r['label_available_at'] for r in train))})
            values=predict_all(test,catalog,destination,read_json(source/'baselines.json'),pack['core']);apply_selection(values,selection)
            for r in values:r.update(scenario=scenario,model_fit_cutoff_wib=wib(cutoff))
            predictions+=values
        write_csv(OUTPUT/scenario/'predictions.csv',predictions)
        score=scores(predictions,True)
        for r in score:r['scenario']=scenario
        write_csv(OUTPUT/scenario/'scores.csv',score);all_scores+=score
    # Actual E11 correction, with the previous conservative timing retained.
    history=histories['raw_srm_1h']
    final_original=[r for r in pack['samples'] if r['issue']<FREEZE and r['label_available_at']<FREEZE]
    final=replace_features(final_original,history)
    final_root=OUTPUT/'raw_srm_1h/models/final';final_root.mkdir(parents=True)
    previous_final=DEFAULT_OUTPUT/'models/final'
    shutil.copyfile(previous_final/'baselines.json',final_root/'baselines.json')
    required=sorted({v[k] for station in selection.values() for v in station.values() for k in ['amount_method','probability_method'] if v[k] in FAMILIES})
    catalog={}
    for family in required:
        if 'soil' in family:
            print(f'E11-corrected final fit: {family}, {len(final)} pre-November windows',flush=True)
            catalog[family]=fit(final,family,final_root/family)
        else:
            shutil.copytree(previous_final/family,final_root/family)
            catalog[family]=read_json(final_root/family/'descriptor.json')
    save_json(OUTPUT/'model_catalog.json',{'final_models':'raw_srm_1h/models/final','selection':selection,
        'feature_receipt_delay_assumption_seconds':3600,'zero_delay_models_are_sensitivity_only':True,'E11_raw_ADC_retained':True})
    save_json(OUTPUT/'training_audit.json',audit)
    save_json(OUTPUT/'feature_availability.json',{name:h.audit for name,h in histories.items()})
    if verify_prior()!=before or digest(DEFAULT_OUTPUT/'selection.json')!=routing_hash:raise ValueError('Prior results changed')
    if any(digest(SOURCES[s])!=q['sha256'] for s,q in quality.items()):raise ValueError('Source CSV changed')
    for history in histories.values():
        if any(r['max_assumed_availability_used'] is not None and (r['max_assumed_availability_used']>r['issue'] or r['max_csv_timestamp_used']>r['issue']) for r in history.audit):raise ValueError('Future feature used')
    from clarification_report import write_report
    write_report(OUTPUT,all_scores,pattern,profile)
    save_json(OUTPUT/'verification.json',{'prior_experiments_unchanged':True,'prior_locked_files':431,
        'raw_source_files_unchanged':True,'same_validation_routing':True,'same_learner_parameters':True,
        'future_timestamp_features_used':False,'feature_timing_unconfirmed':True})
    snapshot=OUTPUT/'frozen_source';snapshot.mkdir()
    for p in VERSION_DIR.glob('*.py'):shutil.copyfile(p,snapshot/p.name)
    files={p.relative_to(OUTPUT).as_posix():digest(p) for p in sorted(OUTPUT.rglob('*')) if p.is_file() and '.matplotlib_cache' not in p.relative_to(OUTPUT).parts}
    save_json(OUTPUT/'clarification_lock.json',{'status':'Retrospective clarification comparison','immutable_files':files})
    print({'output':str(OUTPUT),'locked_files':len(files),'threshold_profile':profile},flush=True)


if __name__=='__main__':build()
