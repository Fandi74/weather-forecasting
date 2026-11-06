"""Follow-up retrospective weekly refresh; original validation routing stays fixed.

This schedule is investigated after reviewing the first static-fit results. It
is a development diagnostic and must not be described as an untouched final test.
"""
import datetime as dt
from pathlib import Path

from common import DEFAULT_OUTPUT,FREEZE,ROOT,VERSION_DIR,WIB,digest,no_overwrite,read_json,save_json,verify_references,wib,write_csv
import baselines
from data import SOURCES,read_sources
from experiment import apply_selection,case_signature,predict_all,scores
from features import FAMILIES
from learner import fit
from samples import build_samples


def build():
    output=VERSION_DIR/'output/rolling_refresh_20261106'
    no_overwrite(output);before=verify_references()
    data,quality=read_sources();pack=build_samples(data)
    selection=read_json(DEFAULT_OUTPUT/'selection.json')
    original_routing_hash=digest(DEFAULT_OUTPUT/'selection.json')
    output.mkdir(parents=True)
    save_json(output/'protocol.json',{'status':'Follow-up retrospective development diagnostic; schedule chosen after first static-fit review',
        'refit_dates_wib':['2026-10-20T00:00:00+07:00','2026-10-27T00:00:00+07:00'],
        'routing':'Original 1–19 October validation selection unchanged', 'routing_sha256':original_routing_hash,
        'hyperparameters_changed':False,'soil_receipt_delay_seconds':3600,'new_test_based_model_selection':False})
    audit=[];predictions=[]
    cutoffs=[dt.datetime(2026,10,day,tzinfo=WIB).timestamp() for day in [20,27]]
    for i,cutoff in enumerate(cutoffs):
        next_cutoff=cutoffs[i+1] if i+1<len(cutoffs) else FREEZE
        train=[r for r in pack['samples'] if r['issue']<cutoff and r['label_available_at']<cutoff]
        hourly=[r for r in pack['hourly'] if r['issue']<cutoff and r['label_available_at']<cutoff]
        test=[r for r in pack['samples'] if r['stage']=='test' and cutoff<=r['issue']<next_cutoff]
        label=dt.datetime.fromtimestamp(cutoff,WIB).strftime('%Y%m%d')
        model_root=output/'models'/label
        baseline=baselines.fit(train,hourly,pack['core']);save_json(model_root/'baselines.json',baseline)
        catalog={}
        for family in FAMILIES:
            print(f'Weekly refresh {label}: {family}, {len(train)} prior windows',flush=True)
            catalog[family]=fit(train,family,model_root/family)
        values=predict_all(test,catalog,model_root,baseline,pack['core']);apply_selection(values,selection)
        for r in values:r['model_fit_cutoff_wib']=wib(cutoff)
        predictions+=values
        audit.append({'cutoff_exclusive_wib':wib(cutoff),'cases':len(train),'test_cases':len(test),
            'latest_training_label_available_wib':wib(max(r['label_available_at'] for r in train)),
            'training_signature':case_signature(train)})
    write_csv(output/'predictions.csv',predictions);write_csv(output/'scores.csv',scores(predictions,True))
    save_json(output/'training_audit.json',audit)
    if digest(DEFAULT_OUTPUT/'selection.json')!=original_routing_hash or verify_references()!=before:
        raise ValueError('Fixed routing or earlier models changed')
    if any(digest(SOURCES[s])!=q['sha256'] for s,q in quality.items()):raise ValueError('Source CSV changed')
    save_json(output/'verification.json',{'references_unchanged':True,'selection_unchanged':True,'source_csvs_unchanged':True,
        'earlier_locked_files':315,'test_cases':len(predictions),'prospective_validation':False})
    print({'output':str(output),'test_cases':len(predictions)},flush=True)


if __name__=='__main__':build()
