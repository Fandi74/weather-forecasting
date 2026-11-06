"""Small, constrained ensembles selected by chronological development validation."""
import statistics

import numpy as np
from scipy.optimize import linprog

COMPONENTS = ['v2_h', 'catboost_hsht_h', 'lightgbm_hsht_h']
FAMILIES = ['v2', 'catboost_hsht', 'lightgbm_hsht', 'equal_three', 'equal_trees', 'v2_bias', 'convex', 'convex_bias']


def eligible_calibration(rows, issue):
    return [r for r in rows if r['issue'] < issue and max(r['time'], r['available_at'], r['observed_at']) < issue]


def fit(rows, family):
    if not rows:
        raise ValueError('No earlier calibration labels')
    fixed = {'v2': [1, 0, 0], 'catboost_hsht': [0, 1, 0], 'lightgbm_hsht': [0, 0, 1],
             'equal_three': [1/3]*3, 'equal_trees': [0, .5, .5], 'v2_bias': [1, 0, 0]}
    if family in fixed:
        bias = statistics.median(r['observed'] - r['v2_h'] for r in rows) if family == 'v2_bias' else 0
        return {'family': family, 'components': COMPONENTS, 'weights': fixed[family], 'bias_pp': bias, 'training_rows': len(rows)}
    if family not in ('convex', 'convex_bias'):
        raise ValueError(family)
    x = np.array([[r[k] for k in COMPONENTS] for r in rows], dtype=float)
    y = np.array([r['observed'] for r in rows])
    allow_bias = family == 'convex_bias'
    design = np.column_stack([x, np.ones(len(x))]) if allow_bias else x
    k, n = design.shape[1], len(rows)
    constraints = np.vstack([np.column_stack([design, -np.eye(n)]), np.column_stack([-design, -np.eye(n)])])
    objective = np.concatenate([np.zeros(k), np.ones(n)/n])
    equality = np.zeros((1, k+n)); equality[0, :3] = 1
    bounds = [(0, 1)]*3 + ([(-100, 100)] if allow_bias else []) + [(0, None)]*n
    solution = linprog(objective, A_ub=constraints, b_ub=np.concatenate([y, -y]),
                       A_eq=equality, b_eq=[1], bounds=bounds, method='highs')
    if not solution.success:
        raise ValueError('Humidity blend fit failed: ' + solution.message)
    return {'family': family, 'components': COMPONENTS, 'weights': solution.x[:3].tolist(),
            'bias_pp': float(solution.x[3]) if allow_bias else 0, 'training_rows': n}


def predict(model, rows):
    return [min(100., max(0., sum(w*r[k] for w, k in zip(model['weights'], COMPONENTS)) + model['bias_pp'])) for r in rows]
