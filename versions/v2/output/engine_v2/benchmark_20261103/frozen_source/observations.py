"""Fresh, sensor-specific observation preparation for the blind benchmark."""
import collections
import csv
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

from inventory import WEATHER, local_time, number

ROOT = Path(__file__).resolve().parents[1]
TIP_MM = 0.28
POINT_TOLERANCE_SECONDS = 300
CLOCK_SNAP_SECONDS = 90
ARRIVAL_DELAY_SECONDS = 3600
KNOWN_CODES = {'E2', 'E3', 'E4', 'E5', 'E8', 'E11', 'E12', 'E16'}


def quality(row):
    codes = set(re.findall(r'\bE\d+\b', row.get('error', '').upper()))
    unknown = codes - KNOWN_CODES
    t, h = number(row.get('t')), number(row.get('h'))
    rf, rfc = number(row.get('rf')), number(row.get('rfc'))
    # E3 affects thdc/hhdc, not the BME280 t/h used here. E8/E11/E12 are
    # soil-temperature, soil-moisture and leaf-wetness flags respectively.
    t_ok = not unknown and 'E2' not in codes and t is not None and -50 <= t <= 65
    h_ok = not unknown and 'E2' not in codes and h is not None and 0 <= h <= 100
    rain_ok = not unknown and 'E4' not in codes and rf is not None and rfc is not None and rf >= 0 and rfc >= 0
    return {'t': t if t_ok else None, 'h': h if h_ok else None,
            'rf': rf, 'rfc': rfc, 'rain_ok': rain_ok, 'unknown_codes': sorted(unknown)}


def load_station(station, metadata, source_root, station_config):
    rows, sources, issues = {}, [], []
    owners = {m['expected_device_id']: s for s, m in station_config.items() if m.get('expected_device_id')}
    for source in sorted((source_root / station).glob('*.csv')):
        with source.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            records = list(reader)
            fields = reader.fieldnames or []
        devices = {r.get('device_id', '') for r in records}
        expected = metadata.get('expected_device_id')
        if expected is None or devices != {expected}:
            issue = 'unconfirmed_device_identity'
            if any(d in owners and owners[d] != station for d in devices):
                issue = 'device_belongs_to_another_station'
            issues.append({'source': source.name, 'reason': issue, 'device_ids': sorted(devices)})
            continue
        sources.append({'path': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                        'rows': len(records), 'has_hdc_fields': any(k in fields for k in ('thdc', 'hhdc')),
                        'has_sht_fields': any(k in fields for k in ('tsht', 'hsht'))})
        for raw in records:
            ms = int(raw['timestamp_ms'])
            record = {'ms': ms, **quality(raw), 'source_error': raw.get('error', '').strip()}
            if ms in rows and rows[ms] != record:
                raise ValueError(f'{station}: conflicting source records at timestamp {ms}')
            rows[ms] = record
    return [rows[t] for t in sorted(rows)], sources, issues


def prepare_hours(records):
    hours, nearest, intervals, qc = {}, {}, {}, collections.Counter()
    for row in records:
        timestamp = row['ms'] / 1000
        point = int(round(timestamp / 3600)) * 3600
        delta = abs(point - timestamp)
        for variable in ('t', 'h'):
            if row[variable] is None:
                qc[f'{variable}_excluded'] += 1
                continue
            if delta <= POINT_TOLERANCE_SECONDS and delta < nearest.get((point, variable), float('inf')):
                nearest[point, variable] = delta
                target = hours.setdefault(point, {'time': point})
                target[variable] = row[variable]
                target[variable + '_observed_at'] = timestamp
                target[variable + '_available_at'] = timestamp + ARRIVAL_DELAY_SECONDS
                target[variable + '_offset_seconds'] = round(timestamp - point, 3)
        for code in row['unknown_codes']:
            qc['unmapped_' + code] += 1
    for previous, row in zip(records, records[1:]):
        a, b = previous['ms'] / 1000, row['ms'] / 1000
        nominal_a, nominal_b = int(round(a / 600)) * 600, int(round(b / 600)) * 600
        reason = None
        if not previous['rain_ok'] or not row['rain_ok']:
            reason = 'sensor_or_value_unavailable'
        elif row['rfc'] < previous['rfc']:
            reason = 'counter_reset'
        elif not 0 < b - a <= 900:
            reason = 'sampling_gap'
        elif abs(row['rf'] - (row['rfc'] - previous['rfc']) * TIP_MM) > 0.011:
            reason = 'counter_amount_mismatch'
        elif abs(a - nominal_a) > CLOCK_SNAP_SECONDS or abs(b - nominal_b) > CLOCK_SNAP_SECONDS or nominal_b - nominal_a != 600:
            reason = 'clock_alignment_unavailable'
        if reason:
            qc['rain_' + reason] += 1
            continue
        if nominal_b in intervals:
            intervals[nominal_b] = None
            qc['rain_duplicate_interval'] += 1
        else:
            intervals[nominal_b] = (row['rf'], b)
            qc['rain_good_interval'] += 1
    candidates = {((end - 1) // 3600 + 1) * 3600 for end in intervals}
    for end in candidates:
        pieces = [intervals.get(end - offset * 600) for offset in range(6)]
        if all(piece is not None for piece in pieces):
            target = hours.setdefault(end, {'time': end})
            target['rain'] = sum(piece[0] for piece in pieces)
            target['rain_observed_at'] = max(piece[1] for piece in pieces)
            target['rain_available_at'] = target['rain_observed_at'] + ARRIVAL_DELAY_SECONDS
            target['rain_coverage_seconds'] = 3600
            qc['rain_complete_hours'] += 1
        else:
            qc['rain_incomplete_hours'] += 1
    return hours, dict(qc)


def prepare_all(source_root, save_directory=None, config=None):
    config = config or json.loads((ROOT / 'engine_v2/stations.json').read_text())
    observations, report = {}, {}
    for station, metadata in config.items():
        records, sources, issues = load_station(station, metadata, source_root, config)
        hours, qc = prepare_hours(records)
        observations[station] = hours
        report[station] = {'sources': sources, 'excluded_sources': issues, 'qc': qc,
                           'accepted_source_records': len(records),
                           'first_wib': local_time(records[0]['ms']) if records else None,
                           'last_wib': local_time(records[-1]['ms']) if records else None,
                           'hourly_targets': {v: sum(v in x for x in hours.values()) for v in ('t', 'h', 'rain')},
                           'arrival_delay_assumption_seconds': ARRIVAL_DELAY_SECONDS,
                           'point_matching_tolerance_seconds': POINT_TOLERANCE_SECONDS,
                           'rain_clock_snap_tolerance_seconds': CLOCK_SNAP_SECONDS,
                           'sensor_stream': 'BME280 t/h only; no HDC/SHT substitution'}
        if station == 'X66':
            report[station]['reference_discrepancy'] = {
                'period': '2026-10', 'median_t_c': 12.02, 'median_tsht_c': 18.885,
                'median_h_pct': 100, 'median_hsht_pct': 90,
                'user_decision': 'Retain t/h and flag discrepancy; secondary streams are not substituted',
                'interpretation': 'Scores are against the retained sensor stream, whose physical accuracy is unverified'}
        if save_directory:
            save_directory.mkdir(parents=True, exist_ok=True)
            (save_directory / f'{station}_hourly.json').write_text(json.dumps(list(hours.values()), separators=(',', ':')), encoding='utf-8')
    if save_directory:
        (save_directory / 'normalization_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return observations, report
