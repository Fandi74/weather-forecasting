"""Explicit percentages for distinct prediction tasks; no single aggregate accuracy."""
import math
import statistics

def continuous(actual,predicted,tolerance):
    if not actual or len(actual)!=len(predicted) or tolerance<0:
        raise ValueError('Matched nonempty samples and a nonnegative tolerance are required')
    errors=[float(p)-float(a) for a,p in zip(actual,predicted)]
    if not all(math.isfinite(x) for x in errors):
        raise ValueError('Non-finite evaluation value')
    hits=sum(abs(e)<=tolerance+1e-12 for e in errors)
    return {'n':len(errors),'tolerance':tolerance,'within_tolerance_count':hits,
        'within_tolerance_pct':100*hits/len(errors),
        'mae':statistics.mean(abs(e) for e in errors),
        'rmse':math.sqrt(statistics.mean(e*e for e in errors)),
        'bias':statistics.mean(errors)}

def rain_event(actual,probability,event_threshold=.28,decision_threshold=.5):
    if not actual or len(actual)!=len(probability):
        raise ValueError('Matched nonempty samples required')
    if any(not math.isfinite(float(p)) or not 0<=float(p)<=1 for p in probability):
        raise ValueError('Probabilities must be finite values in [0,1]')
    truth=[float(a)>=event_threshold-1e-9 for a in actual]
    decision=[float(p)>=decision_threshold for p in probability]
    tp=sum(a and p for a,p in zip(truth,decision))
    tn=sum(not a and not p for a,p in zip(truth,decision))
    fp=sum(not a and p for a,p in zip(truth,decision))
    fn=sum(a and not p for a,p in zip(truth,decision))
    wet=tp+fn;dry=tn+fp
    return {'n':len(truth),'wet_cases':wet,'dry_cases':dry,
        'event_threshold_mm':event_threshold,'decision_threshold':decision_threshold,
        'true_positive':tp,'true_negative':tn,'false_positive':fp,'false_negative':fn,
        'accuracy_pct':100*(tp+tn)/len(truth),
        'balanced_accuracy_pct':50*(tp/wet+tn/dry) if wet and dry else None,
        'precision_pct':100*tp/(tp+fp) if tp+fp else None,
        'recall_pct':100*tp/wet if wet else None,
        'all_dry_accuracy_pct':100*dry/len(truth),
        'brier':statistics.mean((float(p)-a)**2 for p,a in zip(probability,truth))}

def rmse(actual,predicted):
    return math.sqrt(statistics.mean((float(p)-float(a))**2 for a,p in zip(actual,predicted)))
