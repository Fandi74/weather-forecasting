"""Verify V4/V3/V2 snapshots and shared-scale graph files without private inputs."""
import hashlib
import json
from pathlib import Path

V4 = Path(__file__).resolve().parent
REPO = V4.parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(directory, name):
    lock = json.loads((directory / name).read_text(encoding='utf-8'))
    for relative, expected in lock['immutable_files'].items():
        candidate = directory / relative.replace('\\', '/')
        if digest(candidate) != expected:
            raise ValueError('Immutable snapshot mismatch: ' + str(candidate))
    return len(lock['immutable_files'])


def main():
    output = V4 / 'output/benchmark_20261103_lightgbm'
    counts = {
        'v4_locked_files': verify(output, 'candidate_lock.json'),
        'v3_locked_files': verify(REPO / 'v3/output/benchmark_20261103_catboost', 'candidate_lock.json'),
        'v2_locked_files': verify(REPO / 'v2/output/engine_v2/benchmark_20261103', 'benchmark_lock.json')
    }
    metadata = json.loads((output / 'graphs/graph_metadata.json').read_text(encoding='utf-8'))
    for filename, expected in metadata['files'].items():
        if digest(output / 'graphs' / filename) != expected:
            raise ValueError('Graph hash mismatch: ' + filename)
    print(json.dumps({'verified': True, **counts, 'comparison_graphs': len(metadata['files']),
                      'benchmark_actuals_seen': False}, indent=2))


if __name__ == '__main__':
    main()
