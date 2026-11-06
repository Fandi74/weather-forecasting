"""Independent LightGBM learners with the same targets/features used by V3."""
import lightgbm as lgb
import numpy as np

from .common import EVENT_MM, save_json
from .features import feature_names, matrix

PARAMETERS = {'num_boost_round': 400, 'max_depth': 4, 'num_leaves': 15,
              'learning_rate': 0.04, 'lambda_l2': 10.0, 'min_data_in_leaf': 50,
              'feature_fraction': 1.0, 'bagging_fraction': 1.0, 'bagging_freq': 0,
              'seed': 2601106, 'num_threads': 4, 'deterministic': True,
              'force_col_wise': True, 'verbosity': -1}
MODEL_CACHE = {}


def fit(rows, variant, variable, history, folder, output):
    folder.mkdir(parents=True, exist_ok=True)
    names = feature_names(variant)
    x = matrix(rows, variant, history)
    y = np.array([r['observed'] for r in rows], dtype=float)
    descriptor = {'variant': variant, 'variable': variable, 'feature_names': names,
                  'training_rows': len(rows), 'parameters': PARAMETERS}
    importance = []

    def train(values, labels, objective, component):
        params = {key: value for key, value in PARAMETERS.items() if key != 'num_boost_round'}
        params['objective'] = objective
        dataset = lgb.Dataset(values, label=labels, feature_name=names)
        model = lgb.train(params, dataset, num_boost_round=PARAMETERS['num_boost_round'])
        path = folder / (component + '.txt')
        model.save_model(str(path))
        gains = model.feature_importance(importance_type='gain').astype(float)
        if gains.sum() > 0:
            gains = gains / gains.sum() * 100
        importance.extend({'component': component, 'feature': name, 'importance': float(value)}
                          for name, value in zip(names, gains))
        return str(path.relative_to(output)).replace('\\', '/')

    if variable in ('temperature', 'humidity'):
        residual = y - np.array([r['raw'] for r in rows])
        descriptor.update(kind='residual', model=train(x, residual, 'regression_l1', 'residual'))
    elif variable == 'rain':
        wet = y >= EVENT_MM - 1e-9
        if min(int(wet.sum()), int((~wet).sum())) >= 10:
            descriptor['occurrence'] = {'kind': 'model', 'path': train(x, wet.astype(int), 'binary', 'occurrence')}
        else:
            descriptor['occurrence'] = {'kind': 'constant', 'probability': float(wet.mean())}
        if int(wet.sum()) >= 10:
            descriptor['positive_amount'] = {'kind': 'model', 'path': train(x[wet], y[wet], 'regression', 'positive_amount')}
        else:
            descriptor['positive_amount'] = {'kind': 'constant', 'amount': float(y[wet].mean()) if wet.any() else EVENT_MM}
        descriptor.update(kind='hurdle', wet_training_rows=int(wet.sum()))
    else:
        raise ValueError(variable)
    descriptor['feature_importance'] = importance
    save_json(folder / 'descriptor.json', descriptor)
    return descriptor


def loaded(path):
    key = str(path)
    if key not in MODEL_CACHE:
        MODEL_CACHE[key] = lgb.Booster(model_file=key)
    return MODEL_CACHE[key]


def predict(descriptor, rows, history, output):
    if not rows:
        return [], []
    x = matrix(rows, descriptor['variant'], history)
    if descriptor['feature_names'] != feature_names(descriptor['variant']):
        raise ValueError('Saved feature schema differs from inference schema')
    def prediction(path):
        model = loaded(output / path)
        if model.feature_name() != descriptor['feature_names']:
            raise ValueError('LightGBM feature order mismatch')
        return model.predict(x, num_threads=PARAMETERS['num_threads'])
    if descriptor['kind'] == 'residual':
        values = prediction(descriptor['model']) + np.array([r['raw'] for r in rows])
        if descriptor['variable'] == 'humidity':
            values = np.clip(values, 0, 100)
        return values.tolist(), [None] * len(rows)
    occurrence = descriptor['occurrence']
    probability = (prediction(occurrence['path']) if occurrence['kind'] == 'model'
                   else np.full(len(rows), occurrence['probability']))
    probability = np.clip(probability, 0, 1)
    amount = descriptor['positive_amount']
    wet_mean = prediction(amount['path']) if amount['kind'] == 'model' else np.full(len(rows), amount['amount'])
    return (probability * np.maximum(EVENT_MM, wet_mean)).tolist(), probability.tolist()
