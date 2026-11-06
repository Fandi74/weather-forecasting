"""Train, verify, freeze or later score a separate CatBoost candidate locally."""
import argparse
import json
from pathlib import Path

from weather_catboost.common import DEFAULT_OUTPUT, WORKSPACE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'verify', 'lock', 'score'))
    parser.add_argument('--workspace', type=Path, default=WORKSPACE)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--device-map', type=Path, help='Optional scoring-only station-to-device-ID JSON mapping')
    args = parser.parse_args()
    from weather_catboost.experiment import build, lock, verify
    if args.action == 'build':
        build(args.workspace, args.output)
    elif args.action == 'lock':
        print(json.dumps(lock(args.output), indent=2))
    elif args.action == 'verify':
        print(json.dumps(verify(args.output), indent=2))
    else:
        if not args.source_root:
            parser.error('score requires --source-root')
        from weather_catboost.scoring import score
        print(json.dumps(score(args.workspace, args.output, args.source_root, args.device_map), indent=2))


if __name__ == '__main__':
    main()
