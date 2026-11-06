"""Read station exports without altering originals or assigning ambiguous devices."""
import argparse
import collections
import csv
import datetime as dt
import hashlib
import itertools
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIB = dt.timezone(dt.timedelta(hours=7))
WEATHER = ('t', 'h', 'ap', 'rf', 'rfc')


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def local_time(ms):
    return dt.datetime.fromtimestamp(ms / 1000, WIB).isoformat()


def inspect_folder(folder):
    output, signatures = [], {}
    for source in sorted(folder.glob('*.csv')):
        by_time = {}
        devices, errors, dates, qualities = (collections.Counter() for _ in range(4))
        gps, duplicate, conflicts, invalid = [], 0, 0, 0
        with source.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames
            for row in reader:
                try:
                    ms = int(row['timestamp_ms'])
                except (KeyError, ValueError):
                    invalid += 1
                    continue
                devices[row.get('device_id', '')] += 1
                errors[row.get('error', '').strip() or '(blank)'] += 1
                dates[local_time(ms)[:10]] += 1
                values = tuple(number(row.get(key)) for key in WEATHER)
                signature = (*values, row.get('error', '').strip())
                if ms in by_time:
                    duplicate += 1
                    conflicts += signature != by_time[ms]
                by_time[ms] = signature
                for key, value in zip(WEATHER, values):
                    if value is not None:
                        qualities[key + '_numeric'] += 1
                lat, lon = number(row.get('lat')), number(row.get('lon'))
                if lat is not None and lon is not None and lat != 0 and lon != 0:
                    gps.append({'time_wib': local_time(ms), 'latitude': lat, 'longitude': lon})
        times = sorted(by_time)
        output.append({
            'source': str(source), 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'columns': fields, 'device_ids': dict(devices), 'rows': sum(devices.values()),
            'unique_timestamps': len(times), 'duplicates': duplicate, 'conflicts': conflicts,
            'invalid_timestamp_rows': invalid,
            'first_wib': local_time(times[0]) if times else None,
            'last_wib': local_time(times[-1]) if times else None,
            'dates_after_cutoff': {k: v for k, v in sorted(dates.items()) if k >= '2026-11-03'},
            'errors': dict(errors), 'numeric_counts': dict(qualities), 'gps': gps[-10:]
        })
        signatures.update(by_time)
    return output, signatures


def build(base):
    inventory, signatures = {}, {}
    for station in ('X50', 'X51', 'X66', 'X67'):
        inventory[station], signatures[station] = inspect_folder(base / station)
    overlap = []
    for left, right in itertools.combinations(signatures, 2):
        common = signatures[left].keys() & signatures[right].keys()
        identical = sum(signatures[left][t] == signatures[right][t] for t in common)
        overlap.append({'stations': [left, right], 'common_timestamps': len(common),
                        'identical_weather_and_error': identical,
                        'identical_fraction': identical / len(common) if common else None})
    return {'cutoff_exclusive_wib': '2026-11-03T00:00:00+07:00',
            'station_sources': inventory, 'cross_station_overlap': overlap}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'data/engine_v2/station_inventory.json')
    args = parser.parse_args()
    result = build(args.source_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
