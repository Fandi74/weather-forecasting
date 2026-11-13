"""Numerical baseline transforms; model parameters are loaded separately."""
import math
import numpy as np

def clip(value, variable):
    if variable == 'humidity':
        return min(100.0, max(0.0, value))
    return max(0.0, value) if variable == 'rain' else value

def offset_predict(row, model, variable):
    if model['method'] == 'raw':
        return row['raw']
    adjustment = model.get('hour_offsets', {}).get(str(row['hour']), model['offset'])
    return clip(row['raw'] + adjustment, variable)

def rain_features(rows):
    return np.array([[math.log1p(max(0, r['forecast_rain'])), r['forecast_h'] / 100,
                      math.sin(2 * math.pi * r['hour'] / 24), math.cos(2 * math.pi * r['hour'] / 24),
                      r['day'] / 7] for r in rows], dtype=float)

def scale_features(rows, transform=None):
    raw = rain_features(rows)
    if transform is None:
        mean, std = raw.mean(axis=0), raw.std(axis=0)
        std[std < 1e-8] = 1
        transform = {'mean': mean.tolist(), 'std': std.tolist()}
    x = (raw - np.array(transform['mean'])) / np.array(transform['std'])
    return np.column_stack([np.ones(len(x)), x]), transform

def sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -35, 35)))

def probability_predict(rows, model):
    if model['method'] == 'climatology':
        return [model['probability']] * len(rows)
    x, _ = scale_features(rows, model['transform'])
    return sigmoid(x @ np.array(model['coefficients'])).tolist()

def rain_predict(rows, model):
    if model['method'] == 'raw':
        return [r['raw'] for r in rows]
    if model['method'] == 'nonnegative_slope':
        return [max(0.0, r['raw'] * model['slope']) for r in rows]
    probabilities = probability_predict(rows, model['occurrence'])
    amount = model['positive_amount']
    x, _ = scale_features(rows, amount['transform'])
    positive_mean = np.exp(np.clip(x @ np.array(amount['coefficients']), -20, 20)) * amount['smearing']
    return (np.array(probabilities) * positive_mean).tolist()
