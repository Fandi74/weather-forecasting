"""Verify the published V3/V2 frozen snapshots without private training inputs."""
import hashlib
import json
from pathlib import Path

V3 = Path(__file__).resolve().parent
REPO = V3.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(directory, name):
    lock = json.loads((directory / name).read_text(encoding='utf-8'))
    for path, expected in lock['immutable_files'].items():
        candidate = directory / path.replace('\\', '/')
        if digest(candidate) != expected:
            raise ValueError('Immutable snapshot mismatch: ' + str(candidate))
    return len(lock['immutable_files'])


def main():
    v3 = verify(V3 / 'output/benchmark_20261103_catboost', 'candidate_lock.json')
    v2 = verify(REPO / 'v2/output/engine_v2/benchmark_20261103', 'benchmark_lock.json')
    meta = json.loads((V3 / 'graphs/graph_metadata.json').read_text(encoding='utf-8'))
    for filename, expected in meta['files'].items():
        if digest(V3 / 'graphs' / filename) != expected:
            raise ValueError('Comparison graph hash mismatch: ' + filename)
    print(json.dumps({'verified': True, 'v3_locked_files': v3, 'v2_locked_files': v2,
                      'comparison_graphs': len(meta['files']), 'benchmark_actuals_seen': False}, indent=2))


if __name__ == '__main__':
    main()
