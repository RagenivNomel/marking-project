"""Fingerprint frozen source/design and existing production evidence, read-only."""
from pathlib import Path
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / 'design' / 'stage-2b' / 'integrity-baseline.json'
FOLDERS = ('application', 'grading', 'excel', 'workflow', 'rendering', 'scanning',
           'config', 'tests', 'design/stage-2a', 'design references', 'jobs',
           'output', 'outputs', '_HELD_FOR_SEPARATE_GRADING')
SKIP = {'node_modules', '__pycache__', '.git', 'test-temp', 'test-workspace-temp'}

def snapshot():
    records, unreadable = {}, []
    paths = list(ROOT.glob('*.py')) + list(ROOT.glob('*.xlsx')) + list(ROOT.glob('*.txt'))
    for folder in FOLDERS:
        for directory, dirs, files in os.walk(ROOT / folder, onerror=lambda e: unreadable.append(str(e))):
            dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith('tmp')]
            paths.extend(Path(directory) / name for name in files if not name.endswith(('.pyc', '.pyo')))
    for path in sorted(set(paths)):
        try:
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            records[str(path.relative_to(ROOT))] = {'sha256': digest, 'mtime_ns': path.stat().st_mtime_ns}
        except OSError as exc:
            unreadable.append(str(exc))
    return {'files': records, 'unreadable': unreadable}

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--record', action='store_true')
    args = parser.parse_args()
    current = snapshot()
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    if args.record:
        if BASELINE.exists():
            raise SystemExit('Baseline already exists; refusing to replace it.')
        BASELINE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'recorded': len(current['files']), 'unreadable': current['unreadable']}))
    else:
        old = json.loads(BASELINE.read_text(encoding='utf-8'))
        changed = [p for p, data in old['files'].items() if current['files'].get(p) != data]
        added = sorted(set(current['files']) - set(old['files']))
        unexpected_unreadable = sorted(set(current['unreadable']) - set(old['unreadable']))
        result = {'checked': len(old['files']), 'changed_or_missing': changed, 'added': added,
                  'baseline_unreadable_exclusions': old['unreadable'], 'unexpected_unreadable': unexpected_unreadable}
        (BASELINE.parent / 'integrity-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
        if changed or added or unexpected_unreadable:
            raise SystemExit(1)

if __name__ == '__main__':
    main()
