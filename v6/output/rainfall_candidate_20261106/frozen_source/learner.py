"""Fixed rainfall learners; sensor features do not rewrite gauge targets."""
import math
from pathlib import Path

import lightgbm as lgb
import numpy as np

from common import save_json
from features import BASE,names

PARAMETERS={'num_boost_round':400,'max_depth':4,'num_leaves':15,'learning_rate':.04,'lambda_l2':10.,
    'min_data_in_leaf':50,'feature_fraction':1.,'bagging_fraction':1.,'bagging_freq':0,'seed':2601106,
    'num_threads':4,'deterministic':True,'force_col_wise':True,'verbosity':-1}


def matrix(rows,keys):
    return np.array([[np.nan if r['features'].get(k) is None else r['features'][k] for k in keys] for r in rows],dtype=float)


def fit(rows,family,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    keys=names(family);x=matrix(rows,keys);y=np.array([r['actual'] for r in rows]);wet=y>=.28-1e-9
    descriptor={'family':family,'target':'independent_gauge_rain_window_mm','feature_names':keys,'training_cases':len(rows),'unique_target_ends':len({(r['station'],r['end']) for r in rows}),
        'wet_cases':int(wet.sum()),'parameters':PARAMETERS}
    base={k:v for k,v in PARAMETERS.items() if k!='num_boost_round'}
    if min(int(wet.sum()),int((~wet).sum()))>=10:
        classifier=lgb.train({**base,'objective':'binary'},lgb.Dataset(x,label=wet.astype(int),feature_name=keys),num_boost_round=PARAMETERS['num_boost_round'])
        classifier.save_model(str(folder/'occurrence.txt'));descriptor['occurrence']='occurrence.txt'
    else:descriptor['constant_probability']=float(wet.mean())
    if int(wet.sum())>=10:
        amount=lgb.train({**base,'objective':'regression'},lgb.Dataset(x[wet],label=y[wet],feature_name=keys),num_boost_round=PARAMETERS['num_boost_round'])
        amount.save_model(str(folder/'positive_amount.txt'));descriptor['positive_amount']='positive_amount.txt'
    else:descriptor['constant_positive_amount']=float(y[wet].mean()) if wet.any() else .28
    save_json(folder/'descriptor.json',descriptor)
    return descriptor


def predict(rows,descriptor,folder):
    folder=Path(folder);x=matrix(rows,descriptor['feature_names'])
    if not rows:return [],[]
    p=(lgb.Booster(model_file=str(folder/descriptor['occurrence'])).predict(x,num_threads=4) if 'occurrence' in descriptor else np.full(len(rows),descriptor['constant_probability']))
    amount=(lgb.Booster(model_file=str(folder/descriptor['positive_amount'])).predict(x,num_threads=4) if 'positive_amount' in descriptor else np.full(len(rows),descriptor['constant_positive_amount']))
    p=np.clip(p,0,1);amount=np.maximum(.28,amount)
    return (p*amount).tolist(),p.tolist()


def fit_logistic(rows):
    x=matrix(rows,BASE);mean=x.mean(axis=0);std=x.std(axis=0);std[std<1e-8]=1
    z=np.column_stack([np.ones(len(x)),(x-mean)/std]);y=np.array([r['actual']>=.28-1e-9 for r in rows],dtype=float)
    frequency=float(y.mean());beta=np.zeros(z.shape[1]);beta[0]=math.log(max(frequency,1e-8)/max(1-frequency,1e-8))
    penalty=np.eye(z.shape[1])*10;penalty[0,0]=0
    for _ in range(60):
        p=1/(1+np.exp(-np.clip(z@beta,-35,35)))
        h=z.T@(z*np.maximum(p*(1-p),1e-8)[:,None])+penalty
        step=np.linalg.solve(h,z.T@(y-p)-penalty@beta);beta+=step
        if np.max(np.abs(step))<1e-7:break
    climate={station+'_'+str(horizon):float(np.mean([r['actual']>=.28-1e-9 for r in rows if r['station']==station and r['horizon']==horizon])) for station in ['X50','X66'] for horizon in [1,6,12,24]}
    return {'mean':mean.tolist(),'std':std.tolist(),'coefficients':beta.tolist(),'climatology':climate}


def logistic_predict(rows,model):
    x=matrix(rows,BASE);z=np.column_stack([np.ones(len(x)),(x-np.array(model['mean']))/np.array(model['std'])])
    p=1/(1+np.exp(-np.clip(z@np.array(model['coefficients']),-35,35)))
    climate=[model['climatology'][r['station']+'_'+str(r['horizon'])] for r in rows]
    return p.tolist(),climate
