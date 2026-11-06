"""Fair past-only refits of the original V2 rain recipe and window controls."""
from common import locate,read_json
from learner import fit_logistic,logistic_predict


def fit(rows,hourly,core):
    original=read_json(locate()['V2'][0]/'models.json')['models']
    result={'stations':{},'window_probability':fit_logistic(rows)}
    for station in ['X50','X66']:
        train=[r for r in hourly if r['station']==station]
        recipe=original[station]['rain'];p=original[station]['rain_probability']
        amount=core.fit_rain(train,recipe['method'],recipe.get('penalty',1.))
        probability=core.fit_logistic(train,p.get('penalty',1.)) if p and p['method']=='logistic' else {
            'method':'climatology','probability':sum(r['observed']>=.28-1e-9 for r in train)/len(train)}
        result['stations'][station]={'amount':amount,'probability':probability,'training_hourly_cases':len(train),
            'unique_gauge_hours':len({r['time'] for r in train})}
    return result


def predict(rows,model,core):
    amounts=[];hourly_probability=[]
    logistic,climate=logistic_predict(rows,model['window_probability'])
    for row in rows:
        forecasts=[{**r,'raw':r['forecast_rain']} for r in row['hourly_forecasts']]
        station=model['stations'][row['station']]
        amounts.append(sum(core.rain_predict(forecasts,station['amount'])))
        hourly_probability.append(core.probability_predict(forecasts,station['probability'])[0] if row['horizon']==1 else None)
    return {'v2_recipe_amount':amounts,'v2_recipe_probability':hourly_probability,
        'gfs_logistic_probability':logistic,'training_climatology_probability':climate,
        'raw_gfs_amount':[r['features']['gfs_rain_sum'] for r in rows]}
