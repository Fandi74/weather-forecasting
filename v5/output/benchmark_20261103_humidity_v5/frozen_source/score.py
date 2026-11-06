"""Separate scoring of a sealed humidity candidate; never refit or update caches."""
import csv
import datetime as dt
from pathlib import Path

from common import FREEZE, WIB, digest, metrics, no_overwrite, read_json, save_json, wib, write_csv
from data import DEVICE, sht_value


def score(candidate, source, output):
    from run import verify
    candidate, source, output = Path(candidate).resolve(), Path(source).resolve(), Path(output).resolve()
    before = verify(candidate)
    no_overwrite(output)
    source_hash = digest(source)
    with source.open(encoding='utf-8-sig', newline='') as stream:
        raw = list(csv.DictReader(stream))
    if {r['device_id'] for r in raw} != {DEVICE}:
        raise ValueError('Expected an independent X66 export')
    points = {}
    for row in raw:
        stamp = int(row['timestamp_ms']) / 1000
        if stamp < FREEZE or stamp > dt.datetime.now(dt.timezone.utc).timestamp() + 300:
            raise ValueError('Actuals outside elapsed benchmark period')
        value = sht_value(row)
        target = int(round(stamp / 3600)) * 3600
        if value is not None and abs(stamp - target) <= 300 and (target not in points or abs(stamp - target) < abs(points[target]['observed_at'] - target)):
            points[target] = {'actual_hsht': value, 'observed_at': stamp}
    saved = read_json(candidate / 'frozen_predictions.json')
    rows = []
    end = int(max(int(r['timestamp_ms']) / 1000 for r in raw) // 3600) * 3600
    for row in saved['predictions']:
        if row['station'] != 'X66' or row['time'] > end or row['time'] not in points:
            continue
        rows.append({'time': row['time'], 'time_wib': wib(row['time']), **points[row['time']],
            'V2_h': row['v2_h'], 'V3_h': row['v3_h'], 'V4_h': row['v4_h'], 'V5_h': row['selected_h'],
            'CatBoost_hsht_h': row['catboost_hsht_h'], 'LightGBM_hsht_h': row['lightgbm_hsht_h']})
    if not rows:
        raise ValueError('No matched hourly humidity observations')
    scores = [{'model': name, **metrics([r['actual_hsht'] for r in rows], [r[name + '_h'] for r in rows])}
              for name in ['V2','V3','V4','V5','CatBoost_hsht','LightGBM_hsht']]
    metadata = {'source': str(source), 'source_sha256': source_hash,
        'first_observation_wib': wib(min(int(r['timestamp_ms']) / 1000 for r in raw)),
        'last_observation_wib': wib(max(int(r['timestamp_ms']) / 1000 for r in raw)),
        'candidate_created_at_utc': saved['candidate_created_at_utc'], 'future_confirmation_start_wib': saved['future_confirmation_start_wib'],
        'evaluation_status': 'Post-development diagnostic; partial November actuals were already revealed in chat',
        'reference_humidity': 'hsht', 'models_refitted': False, 'github_push_performed': False}
    output.mkdir(parents=True)
    write_csv(output / 'hourly_comparison.csv', rows)
    write_csv(output / 'metrics.csv', scores)
    save_json(output / 'protocol.json', metadata)
    from reporting import score_report
    score_report(output, rows, scores, metadata)
    if verify(candidate) != before or digest(source) != source_hash:
        raise ValueError('Sealed candidate or actual export changed during scoring')
    save_json(output / 'verification.json', {**before, 'source_unchanged': True, 'models_refitted': False})
    print({'output': str(output), 'scores': scores})
