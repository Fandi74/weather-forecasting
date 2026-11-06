"""Immutable GFS downloads for the 3–9 November 2026 frozen benchmark.

This is a fresh collector, independent of dashboard/engine.mjs.
Historical target dates stop on 2 November; frozen future targets come from a
single GFS initialization on 2 November, never a 3/4/5 November update.
"""
import argparse
import calendar
import datetime as dt
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/engine_v2/gfs'
UTC = dt.timezone.utc
WIB = dt.timezone(dt.timedelta(hours=7))
START = dt.date(2025, 11, 3)
END = dt.date(2026, 11, 2)
FREEZE = dt.datetime(2026, 11, 3, tzinfo=WIB)
# Use an earlier run with a conservative publication margin. Actual historical
# Open-Meteo publication timestamps are unavailable; do not label this verified.
RUN = dt.datetime(2026, 11, 2, 6, tzinfo=UTC)
ASSUMED_AVAILABILITY = RUN + dt.timedelta(hours=6)
MODEL = 'gfs_seamless'
VARIABLES = ('temperature_2m', 'relative_humidity_2m', 'precipitation')
FIELDS = tuple(f'{v}_previous_day{d}' for v in VARIABLES for d in range(1, 8))


def utc_now():
    return dt.datetime.now(UTC).isoformat()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.pending')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def months(start=START, end=END):
    while start <= end:
        last = min(end, dt.date(start.year, start.month, calendar.monthrange(start.year, start.month)[1]))
        yield start, last
        start = last + dt.timedelta(days=1)


def common_params(stations):
    return {
        'latitude': ','.join(str(s['latitude']) for s in stations.values()),
        'longitude': ','.join(str(s['longitude']) for s in stations.values()),
        'elevation': ','.join(str(s['elevation_m']) for s in stations.values()),
        'models': MODEL, 'timezone': 'Asia/Jakarta', 'timeformat': 'unixtime'
    }


def expected_times(start, end):
    begin = int(dt.datetime.combine(start, dt.time(), WIB).timestamp())
    return list(range(begin, begin + ((end - start).days + 1) * 86400, 3600))


def validate(payload, stations, fields, start, end):
    slots = payload if isinstance(payload, list) else [payload]
    if len(slots) != len(stations):
        raise ValueError('Wrong number of location responses')
    summaries = {}
    for station, slot in zip(stations, slots):
        if slot.get('error'):
            raise ValueError(slot.get('reason', 'Provider error'))
        hourly = slot.get('hourly', {})
        times = hourly.get('time', [])
        if tuple(fields) == VARIABLES:
            first = int(dt.datetime.combine(start, dt.time(), WIB).timestamp())
            last = int(dt.datetime.combine(end + dt.timedelta(days=1), dt.time(), WIB).timestamp())
            required = set(range(first, last + 1, 3600))
            if not required.issubset(times) or times != sorted(set(times)):
                raise ValueError(f'{station}: frozen run does not cover the entire benchmark')
        elif times != expected_times(start, end):
            raise ValueError(f'{station}: incomplete or unexpected timestamp range')
        n = len(hourly['time'])
        for field in fields:
            if len(hourly.get(field, [])) != n or field not in slot.get('hourly_units', {}):
                raise ValueError(f'{station}: missing variable/units {field}')
        summaries[station] = {
            'hours': n, 'missing_values': {v: sum(x is None for x in hourly[v]) for v in fields},
            'returned_grid': {k: slot.get(k) for k in ('latitude', 'longitude', 'elevation')},
            'units': slot['hourly_units']
        }
    return summaries


def get_archive(path, url, stations, fields, start, end):
    if path.exists():
        envelope = json.loads(path.read_text(encoding='utf-8'))
        if envelope.get('request_url') != url:
            raise ValueError('Cached query mismatch; refusing to replace archived data')
        raw = json.dumps(envelope['payload'], sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        if hashlib.sha256(raw).hexdigest() != envelope['payload_sha256']:
            raise ValueError('Cached payload checksum failed')
        return {'file': str(path.relative_to(DATA)), 'cached': True,
                'coverage': validate(envelope['payload'], stations, fields, start, end),
                'retrieved_at_utc': envelope['retrieved_at_utc']}
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'Fieldcast-EngineV2-Research/1.0'})
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read(25_000_001)
            if len(body) > 25_000_000:
                raise ValueError('Response exceeds archive limit')
            payload = json.loads(body)
            coverage = validate(payload, stations, fields, start, end)
            raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
            retrieved = utc_now()
            save(path, {'request_url': url, 'retrieved_at_utc': retrieved,
                        'payload_sha256': hashlib.sha256(raw).hexdigest(), 'payload': payload})
            return {'file': str(path.relative_to(DATA)), 'cached': False,
                    'coverage': coverage, 'retrieved_at_utc': retrieved}
        except urllib.error.HTTPError as error:
            details = error.read(4000).decode('utf-8', errors='replace')
            if error.code == 429 or error.code < 500 or attempt == 2:
                raise RuntimeError(f'HTTP {error.code}; Retry-After={error.headers.get("Retry-After")}; {details}') from error
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 * (attempt + 1))


def collect(phase):
    stations = json.loads((ROOT / 'engine_v2/stations.json').read_text(encoding='utf-8'))
    DATA.mkdir(parents=True, exist_ok=True)
    manifest_path = DATA / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.update({
        'model': MODEL, 'history_start_wib': START.isoformat(), 'history_end_wib': END.isoformat(),
        'history_expected_hours_per_station': len(expected_times(START, END)),
        'freeze_wib': FREEZE.isoformat(), 'frozen_run_initialized_utc': RUN.isoformat(),
        'assumed_run_available_utc': ASSUMED_AVAILABILITY.isoformat(),
        'availability_note': 'Conservative six-hour publication assumption; actual historical Open-Meteo availability is not independently verified. Retrieval now is a retrospective reconstruction, not a forecast archived on 2 November.',
        'stations': stations, 'updated_at_utc': utc_now()
    })
    assert ASSUMED_AVAILABILITY <= FREEZE.astimezone(UTC)
    try:
        if phase in ('frozen', 'all'):
            # Include Nov 10 00:00 for the last preceding-hour rain interval.
            start, end = dt.date(2026, 11, 3), dt.date(2026, 11, 9)
            params = {**common_params(stations), 'hourly': ','.join(VARIABLES),
                      'run': RUN.strftime('%Y-%m-%dT%H:%M'), 'forecast_days': 10}
            url = 'https://single-runs-api.open-meteo.com/v1/forecast?' + urllib.parse.urlencode(params)
            manifest['frozen'] = get_archive(DATA / 'frozen/gfs_run_20261102T0600Z.json', url, stations, VARIABLES, start, end)
            save(manifest_path, manifest)
            print('Frozen GFS run archived for four target locations.', flush=True)
        if phase in ('history', 'all'):
            chunks = []
            for start, end in months():
                params = {**common_params(stations), 'hourly': ','.join(FIELDS),
                          'start_date': start.isoformat(), 'end_date': end.isoformat()}
                url = 'https://previous-runs-api.open-meteo.com/v1/forecast?' + urllib.parse.urlencode(params)
                result = get_archive(DATA / f'history/{start}_{end}.json', url, stations, FIELDS, start, end)
                chunks.append({**result, 'start': start.isoformat(), 'end': end.isoformat()})
                manifest['history_chunks'] = chunks
                manifest['history_complete'] = end == END
                save(manifest_path, manifest)
                print(f'GFS history: {start} through {end}; four locations; cached={result["cached"]}', flush=True)
                if not result['cached']:
                    time.sleep(2)
        if phase in ('samples', 'all'):
            samples = []
            issue = dt.date(2026, 4, 7)
            while issue <= dt.date(2026, 10, 27):
                run = dt.datetime.combine(issue - dt.timedelta(days=1), dt.time(6), UTC)
                end = issue + dt.timedelta(days=6)
                params = {**common_params(stations), 'hourly': ','.join(VARIABLES),
                          'run': run.strftime('%Y-%m-%dT%H:%M'), 'forecast_days': 10}
                url = 'https://single-runs-api.open-meteo.com/v1/forecast?' + urllib.parse.urlencode(params)
                result = get_archive(DATA / f'samples/gfs_run_{run:%Y%m%dT%H%MZ}.json', url, stations, VARIABLES, issue, end)
                samples.append({**result, 'service_issue_wib': dt.datetime.combine(issue, dt.time(), WIB).isoformat(),
                                'run_initialized_utc': run.isoformat(), 'window_end_exclusive_wib':
                                dt.datetime.combine(end + dt.timedelta(days=1), dt.time(), WIB).isoformat()})
                manifest['weekly_samples'] = samples
                save(manifest_path, manifest)
                print(f'Exact weekly GFS sample: issue {issue}; run {run:%Y-%m-%d %H UTC}; cached={result["cached"]}', flush=True)
                issue += dt.timedelta(days=7)
                if not result['cached']:
                    time.sleep(2)
        manifest.pop('last_error', None)
    except Exception as error:
        manifest['last_error'] = {'at_utc': utc_now(), 'message': str(error)}
        save(manifest_path, manifest)
        raise
    save(manifest_path, manifest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('history', 'frozen', 'samples', 'all'), default='all')
    collect(parser.parse_args().phase)
