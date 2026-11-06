"""Verify the published V7 package and inherited references without ML libraries."""
import hashlib
import json
from pathlib import Path

V7 = Path(__file__).resolve().parent

def main():
    manifest = json.loads((V7/'publication.json').read_text(encoding='utf-8'))
    for relative, expected in manifest['files_sha256'].items():
        path = V7/relative
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Published V7 file changed: '+relative)
    import run
    result = run.verify()
    result.update(published_files_verified=len(manifest['files_sha256']),
        publication_branch=manifest['branch'], models_retrained_for_publication=False)
    print(json.dumps(result,indent=2))

if __name__ == '__main__':
    main()
