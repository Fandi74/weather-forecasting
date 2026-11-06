"""Train rainfall-only ablations, select on validation, then score later periods."""
import collections
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil

from common import (DEFAULT_OUTPUT,FREEZE,HORIZONS,ROOT,TRAIN_END,VALIDATION_END,VERSION_DIR,WIB,
    digest,locate,metrics,no_overwrite,read_json,save_json,verify_references,wib,write_csv)
from data import SOURCES,read_sources,window_label
from features import FAMILIES,all_features
from learner import fit,predict
import baselines
from patterns import analyze
from samples import build_samples

AMOUNT_MODELS=['v2_recipe','raw_gfs']+FAMILIES
PROBABILITY_MODELS=['v2_recipe','gfs_logistic','training_climatology']+FAMILIES


def case_signature(rows):
    return hashlib.sha256(json.dumps([[r['station'],r['issue'],r['horizon'],r['actual'],r['label_available_at']] for r in rows],separators=(',',':')).encode()).hexdigest()


def predict_all(rows,descriptors,model_root,baseline,core):
    old=baselines.predict(rows,baseline,core)
    records=[]
    for i,row in enumerate(rows):
        records.append({k:row[k] for k in ['station','issue','horizon','end','actual','label_available_at','label_source','stage','gfs_source_issue']})
        records[-1].update(issue_wib=wib(row['issue']),end_wib=wib(row['end']))
        records[-1].update({k:values[i] for k,values in old.items()})
    for family,descriptor in descriptors.items():
        amount,prob=predict(rows,descriptor,model_root/family)
        for record,a,p in zip(records,amount,prob):record.update({family+'_amount':a,family+'_probability':p})
    return records


def scores(records,include_selected=False):
    result=[]
    for station in ['X50','X66']:
        for horizon in HORIZONS:
            sample=[r for r in records if r['station']==station and r['horizon']==horizon]
            if not sample:continue
            actual=[r['actual'] for r in sample]
            candidates=list(dict.fromkeys(AMOUNT_MODELS+PROBABILITY_MODELS+(['selected'] if include_selected else [])))
            for model in candidates:
                amount=[r.get(model+'_amount') for r in sample];prob=[r.get(model+'_probability') for r in sample]
                has_amount=all(v is not None for v in amount);has_prob=all(v is not None for v in prob)
                if not has_amount and not has_prob:continue
                values=metrics(actual,amount if has_amount else actual,prob if has_prob else None)
                if not has_amount:
                    for key in ['mae','rmse','bias','wet_mae','hits_amount_threshold','misses_amount_threshold','false_alarms_amount_threshold','precision_amount_threshold','recall_amount_threshold']:values[key]=None
                result.append({'station':station,'horizon':horizon,'model':model,'amount_available':has_amount,'probability_available':has_prob,**values})
    return result


def select(validation_scores):
    selection={}
    for station in ['X50','X66']:
        selection[station]={}
        for horizon in HORIZONS:
            candidates=[r for r in validation_scores if r['station']==station and r['horizon']==horizon and r['n']>=48]
            a=[r for r in candidates if r['amount_available']];p=[r for r in candidates if r['probability_available']]
            if not a or not p:raise ValueError('Insufficient validation support')
            best_a=min(a,key=lambda r:(r['rmse'],AMOUNT_MODELS.index(r['model'])))
            best_p=min(p,key=lambda r:(r['brier'],PROBABILITY_MODELS.index(r['model'])))
            selection[station][str(horizon)]={'amount_method':best_a['model'],'probability_method':best_p['model'],
                'validation_rmse_mm':best_a['rmse'],'validation_brier':best_p['brier'],'validation_cases':best_a['n'],
                'reason':'Selected on 1–19 October; later test outcomes excluded'}
    return selection


def apply_selection(records,selection):
    for row in records:
        choice=selection[row['station']][str(row['horizon'])]
        row['selected_amount']=row[choice['amount_method']+'_amount']
        row['selected_probability']=row[choice['probability_method']+'_probability']
        row['selected_amount_method']=choice['amount_method'];row['selected_probability_method']=choice['probability_method']


def build(output=DEFAULT_OUTPUT):
    output=Path(output).resolve();no_overwrite(output)
    before=verify_references();data,quality=read_sources()
    output.mkdir(parents=True)
    save_json(output/'protocol.json',read_json(VERSION_DIR/'protocol.json'))
    save_json(output/'reference_locks.json',before);save_json(output/'source_quality.json',quality)
    pattern,flags,onsets,matched=analyze(data)
    save_json(output/'pattern_analysis.json',pattern);write_csv(output/'soil_rain_flags.csv',flags)
    write_csv(output/'rain_onset_soil_response.csv',onsets);write_csv(output/'matched_hourly_rain.csv',matched)
    print('Preparing matched hourly-issue windows with past-only station context.',flush=True)
    pack=build_samples(data);rows=pack['samples'];core=pack['core']
    train=[r for r in rows if r['stage']=='train'];val=[r for r in rows if r['stage']=='validation']
    test=[r for r in rows if r['stage']=='test'];diagnostic=[r for r in rows if r['stage']=='november_diagnostic']
    train_hourly=[r for r in pack['hourly'] if r['issue']<TRAIN_END and r['label_available_at']<TRAIN_END]
    if not train or not val or not test:raise ValueError('Missing chronological partition')
    save_json(output/'sample_coverage.json',{'stage_counts':dict(collections.Counter(r['stage'] for r in rows)),
        'label_sources':dict(collections.Counter(r['label_source'] for r in rows)),'omissions':pack['coverage'],
        'training_cases':len(train),'training_unique_gauge_window_ends':len({(r['station'],r['end']) for r in train}),
        'training_signature':case_signature(train),'validation_signature':case_signature(val),'test_signature':case_signature(test)})
    audit=[];descriptors={}
    baseline=baselines.fit(train,train_hourly,core);save_json(output/'models/validation/baselines.json',baseline)
    for family in FAMILIES:
        print(f'Validation fit {family}: {len(train)} rain-window cases',flush=True)
        descriptors[family]=fit(train,family,output/'models/validation'/family)
        audit.append({'stage':'validation','family':family,'target':'independent_gauge_window_mm','cases':len(train),
            'latest_label_available_wib':wib(max(r['label_available_at'] for r in train)),
            'cutoff_exclusive_wib':wib(TRAIN_END),'row_signature':case_signature(train)})
    validation_predictions=predict_all(val,descriptors,output/'models/validation',baseline,core)
    validation_scores=scores(validation_predictions);selection=select(validation_scores)
    save_json(output/'selection.json',selection);selection_hash=digest(output/'selection.json')
    apply_selection(validation_predictions,selection)
    write_csv(output/'validation_predictions.csv',validation_predictions)
    write_csv(output/'validation_scores.csv',scores(validation_predictions,True))
    print('Selection frozen from validation; evaluating the later October period.',flush=True)
    test_predictions=predict_all(test,descriptors,output/'models/validation',baseline,core);apply_selection(test_predictions,selection)
    write_csv(output/'test_predictions.csv',test_predictions);write_csv(output/'test_scores.csv',scores(test_predictions,True))
    # Diagnostic November predictions retain the exact same pre-October models.
    diagnostic_predictions=predict_all(diagnostic,descriptors,output/'models/validation',baseline,core);apply_selection(diagnostic_predictions,selection)
    write_csv(output/'november_diagnostic_predictions.csv',diagnostic_predictions)
    write_csv(output/'november_diagnostic_scores.csv',scores(diagnostic_predictions,True))
    if digest(output/'selection.json')!=selection_hash:raise ValueError('Test outcomes changed model selection')
    final=[r for r in rows if r['issue']<FREEZE and r['label_available_at']<FREEZE]
    final_hourly=[r for r in pack['hourly'] if r['issue']<FREEZE and r['label_available_at']<FREEZE]
    final_baseline=baselines.fit(final,final_hourly,core);save_json(output/'models/final/baselines.json',final_baseline)
    needed=sorted({choice[key] for station in selection.values() for choice in station.values() for key in ['amount_method','probability_method'] if choice[key] in FAMILIES})
    final_descriptors={}
    for family in needed:
        print(f'Final fit {family}: {len(final)} pre-November rain windows',flush=True)
        final_descriptors[family]=fit(final,family,output/'models/final'/family)
        audit.append({'stage':'final','family':family,'target':'independent_gauge_window_mm','cases':len(final),
            'latest_label_available_wib':wib(max(r['label_available_at'] for r in final)),
            'cutoff_exclusive_wib':wib(FREEZE),'row_signature':case_signature(final)})
    # Same original 3 November issue: only then-available soil/rain context enters.
    initial=[]
    original_gfs=read_json(locate()['V2'][0]/'frozen_predictions.json')['predictions']
    gfs_index={(r['station'],r['time']):r for r in original_gfs}
    for station in ['X50','X66']:
        for horizon in HORIZONS:
            forecasts=[gfs_index[station,FREEZE+k*3600] for k in range(1,horizon+1)]
            initial.append({'station':station,'issue':FREEZE,'horizon':horizon,'end':FREEZE+horizon*3600,
                'actual':None,'label_available_at':None,'label_source':'future_label_not_used','stage':'frozen_initial',
                'gfs_source_issue':FREEZE,'hourly_forecasts':forecasts,
                'features':all_features(station,FREEZE,horizon,FREEZE,forecasts,pack['history'])})
    initial_predictions=predict_all(initial,final_descriptors,output/'models/final',final_baseline,core)
    apply_selection(initial_predictions,selection)
    write_csv(output/'frozen_window_forecasts.csv',initial_predictions)
    save_json(output/'model_catalog.json',{'families':final_descriptors,'selection':selection,'windows_hours':HORIZONS,
        'forecast_issue_wib':wib(FREEZE),'gfs_run_initialized_utc':'2026-11-02T06:00:00+00:00',
        'no_new_hourly_gfs_runs_assumed':True,'created_at_utc':dt.datetime.now(dt.timezone.utc).isoformat()})
    v5=read_json(locate()['V5'][0]/'frozen_predictions.json')['predictions']
    passthrough=[{'station':r['station'],'time':r['time'],'temperature_c':r['selected_t'],'humidity_pct':r['selected_h']} for r in v5]
    save_json(output/'temperature_humidity_passthrough.json',passthrough)
    save_json(output/'training_audit.json',audit);save_json(output/'feature_availability.json',pack['history'].audit)
    save_json(output/'gfs_input_checksums.json',pack['gfs_checksums'])
    if verify_references()!=before or any(digest(SOURCES[s])!=q['sha256'] for s,q in quality.items()):raise ValueError('Reference or input changed')
    from reporting import report_and_plots
    report_and_plots(output,data,pattern,flags,test_predictions,scores(test_predictions,True))
    snapshot=output/'frozen_source';snapshot.mkdir()
    for p in VERSION_DIR.glob('*'):
        if p.is_file() and p.suffix in {'.py','.json','.md','.txt'}:shutil.copyfile(p,snapshot/p.name)
    files={p.relative_to(output).as_posix():digest(p) for p in sorted(output.rglob('*')) if p.is_file() and not {'.matplotlib_cache','jobs'}.intersection(p.relative_to(output).parts)}
    save_json(output/'candidate_lock.json',{'version':'engine_v6_rainfall.1','immutable_files':files,
        'created_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'retrospective_research':True,'temperature_humidity_unchanged':True})
    print(json.dumps({'output':str(output),'selection':selection,'locked_files':len(files),'test_summary':[r for r in scores(test_predictions,True) if r['model'] in ['selected','v2_recipe','gfs_logistic']]},indent=2),flush=True)


def verify(output=DEFAULT_OUTPUT):
    output=Path(output);lock=read_json(output/'candidate_lock.json')
    for path,expected in lock['immutable_files'].items():
        if digest(output/path)!=expected:raise ValueError('V6 immutable file changed: '+path)
    if verify_references()!=read_json(output/'reference_locks.json'):raise ValueError('Earlier reference changed')
    current=read_json(output/'temperature_humidity_passthrough.json')
    v5=read_json(locate()['V5'][0]/'frozen_predictions.json')['predictions']
    expected=[{'station':r['station'],'time':r['time'],'temperature_c':r['selected_t'],'humidity_pct':r['selected_h']} for r in v5]
    if current!=expected:raise ValueError('V6 changed protected V5 temperature/humidity')
    return {'verified':True,'v6_locked_files':len(lock['immutable_files']),'earlier_locked_files':315,'unchanged_temperature_humidity_rows':len(current)}
