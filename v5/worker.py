"""One humidity-only learner, runnable in an existing CatBoost or LightGBM runtime."""
import argparse
import importlib.metadata
from pathlib import Path

from common import read_json, save_json

CATBOOST = {'iterations': 400, 'depth': 4, 'learning_rate': .04, 'l2_leaf_reg': 10., 'random_seed': 2601106,
            'thread_count': 4, 'task_type': 'CPU', 'has_time': True, 'bootstrap_type': 'No', 'allow_writing_files': False, 'verbose': False}
LIGHTGBM = {'num_boost_round': 400, 'max_depth': 4, 'num_leaves': 15, 'learning_rate': .04, 'lambda_l2': 10.,
            'min_data_in_leaf': 50, 'feature_fraction': 1., 'bagging_fraction': 1., 'bagging_freq': 0, 'seed': 2601106,
            'num_threads': 4, 'deterministic': True, 'force_col_wise': True, 'verbosity': -1, 'objective': 'regression_l1'}


def run(job_path):
    import numpy as np
    job = read_json(job_path)
    if job['target'] != 'hsht_humidity_residual':
        raise ValueError('V5 workers can train humidity only')
    x = np.array(job['train_x'], dtype=float)
    y = np.array(job['train_y_residual'], dtype=float)
    val = np.array(job['predict_x'], dtype=float)
    path = Path(job['model_path'])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError('Refuse to overwrite a trained model')
    if job['algorithm'] == 'catboost':
        from catboost import CatBoostRegressor, Pool
        model = CatBoostRegressor(**CATBOOST, loss_function='MAE')
        model.fit(Pool(x, y, feature_names=job['feature_names']))
        model.save_model(str(path))
        reloaded = CatBoostRegressor()
        reloaded.load_model(str(path))
        pred = reloaded.predict(Pool(val, feature_names=job['feature_names']))
        parameters = CATBOOST
    elif job['algorithm'] == 'lightgbm':
        import lightgbm as lgb
        parameters = {k: v for k, v in LIGHTGBM.items() if k != 'num_boost_round'}
        model = lgb.train(parameters, lgb.Dataset(x, label=y, feature_name=job['feature_names']), num_boost_round=LIGHTGBM['num_boost_round'])
        model.save_model(str(path))
        pred = lgb.Booster(model_file=str(path)).predict(val, num_threads=4)
        parameters = LIGHTGBM
    else:
        raise ValueError(job['algorithm'])
    result = np.clip(np.array(job['raw_predict']) + pred, 0, 100).tolist()
    save_json(job['result_path'], {'algorithm': job['algorithm'], 'package_version': importlib.metadata.version(job['algorithm']),
        'target': job['target'], 'parameters': parameters, 'training_rows': len(y), 'feature_names': job['feature_names'], 'predictions': result})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job', type=Path)
    run(parser.parse_args().job)
