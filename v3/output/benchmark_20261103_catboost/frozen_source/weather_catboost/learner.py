"""Fixed, modest CPU CatBoost models; no benchmark-driven hyperparameter tuning."""
import statistics

import numpy as np
from catboost import CatBoostClassifier, CatBoostRegressor, Pool

from .common import EVENT_MM, VARIABLES, read_json, save_json
from .features import feature_names, matrix

PARAMETERS = {'iterations': 400, 'depth': 4, 'learning_rate': 0.04,
              'l2_leaf_reg': 10.0, 'random_seed': 2601106, 'thread_count': 4,
              'task_type': 'CPU', 'has_time': True, 'bootstrap_type': 'No',
              'allow_writing_files': False, 'verbose': False}
MODEL_CACHE = {}


def fit(rows, variant, variable, history, folder, output):
    folder.mkdir(parents=True, exist_ok=True)
    names = feature_names(variant)
    x = matrix(rows, variant, history)
    y = np.array([r['observed'] for r in rows], dtype=float)
    descriptor = {'variant': variant, 'variable': variable, 'feature_names': names,
                  'training_rows': len(rows), 'parameters': PARAMETERS}

    def store_model(model, name):
        path = folder / (name + '.cbm')
        model.save_model(str(path))
        return str(path.relative_to(output)).replace('\\', '/')

    importance = []
    if variable in ('temperature', 'humidity'):
        model = CatBoostRegressor(**PARAMETERS, loss_function='MAE')
        model.fit(Pool(x, y - np.array([r['raw'] for r in rows]), feature_names=names))
        descriptor.update(kind='residual', model=store_model(model, 'residual'))
        importance.append(('residual', model.feature_importances_))
    elif variable == 'rain':
        wet = y >= EVENT_MM - 1e-9
        frequency = float(wet.mean())
        if min(int(wet.sum()), int((~wet).sum())) >= 10:
            classifier = CatBoostClassifier(**PARAMETERS, loss_function='Logloss')
            classifier.fit(Pool(x, wet.astype(int), feature_names=names))
            descriptor['occurrence'] = {'kind': 'model', 'path': store_model(classifier, 'occurrence')}
            importance.append(('occurrence', classifier.feature_importances_))
        else:
            descriptor['occurrence'] = {'kind': 'constant', 'probability': frequency}
        if int(wet.sum()) >= 10:
            amount = CatBoostRegressor(**PARAMETERS, loss_function='RMSE')
            amount.fit(Pool(x[wet], y[wet], feature_names=names))
            descriptor['positive_amount'] = {'kind': 'model', 'path': store_model(amount, 'positive_amount')}
            importance.append(('positive_amount', amount.feature_importances_))
        else:
            descriptor['positive_amount'] = {'kind': 'constant', 'amount': float(y[wet].mean()) if wet.any() else EVENT_MM}
        descriptor.update(kind='hurdle', wet_training_rows=int(wet.sum()))
    else:
        raise ValueError(variable)
    descriptor['feature_importance'] = [{'component': part, 'feature': name, 'importance': float(value)}
                                      for part, values in importance for name, value in zip(names, values)]
    save_json(folder / 'descriptor.json', descriptor)
    return descriptor


def loaded(path, classifier=False):
    key = str(path)
    if key not in MODEL_CACHE:
        model = CatBoostClassifier() if classifier else CatBoostRegressor()
        model.load_model(key)
        MODEL_CACHE[key] = model
    return MODEL_CACHE[key]


def predict(descriptor, rows, history, output):
    if not rows:
        return [], []
    x = matrix(rows, descriptor['variant'], history)
    pool = Pool(x, feature_names=descriptor['feature_names'])
    if descriptor['kind'] == 'residual':
        values = loaded(output / descriptor['model']).predict(pool) + np.array([r['raw'] for r in rows])
        if descriptor['variable'] == 'humidity':
            values = np.clip(values, 0, 100)
        return values.tolist(), [None] * len(rows)
    occurrence = descriptor['occurrence']
    probability = (loaded(output / occurrence['path'], classifier=True).predict_proba(pool)[:, 1]
                   if occurrence['kind'] == 'model' else np.full(len(rows), occurrence['probability']))
    amount = descriptor['positive_amount']
    wet_mean = (loaded(output / amount['path']).predict(pool)
                if amount['kind'] == 'model' else np.full(len(rows), amount['amount']))
    expected = probability * np.maximum(EVENT_MM, wet_mean)
    return expected.tolist(), probability.tolist()
