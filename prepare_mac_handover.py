"""Build a separate handover copy; never edit original data or saved jobs."""
from pathlib import Path
import os
import shutil
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'handover' / 'Mums Reading Project'
EXCLUDE_ROOT = {'handover', 'test-workspace-temp', 'tmp', '.acceptance', 'complete.zip', 'full_source_dump.txt', 'prepare_mac_handover.py', 'NotoSansSC-OFL.txt'}
EXCLUDE_DIR = {'__pycache__', '.venv', '.git', '.codex', '.agents', '.pytest_cache', 'test-temp'}
skipped = []

def excluded(name):
    return name in EXCLUDE_DIR or name.startswith('tmp') or name.startswith('.env') or name in {'auth.json', '.DS_Store', '.pipeline.lock'} or name.endswith(('.pyc', '.pyo')) or name.startswith('~$')

def copy_dir(src, dst):
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        rel = item.relative_to(ROOT).as_posix()
        if excluded(item.name) or (src == ROOT and item.name in EXCLUDE_ROOT):
            skipped.append(rel)
            continue
        if item.is_symlink():
            raise RuntimeError(f'Unexpected symlink: {rel}')
        if item.is_dir():
            copy_dir(item, dst / item.name)
        else:
            shutil.copy2(item, dst / item.name)

if DEST.exists():
    raise SystemExit('Handover already exists; refusing to overwrite it.')
copy_dir(ROOT, DEST)
fonts = DEST / 'rendering/template/fonts'
fonts.mkdir()
shutil.copy2('C:/Windows/Fonts/NotoSansSC-VF.ttf', fonts / 'NotoSansSC-VF.ttf')
shutil.copy2(ROOT / 'NotoSansSC-OFL.txt', fonts / 'OFL.txt')
for p in (DEST / 'rendering/template').glob('layout_v*.json'):
    p.write_text(p.read_text(encoding='utf-8').replace('C:/Windows/Fonts/NotoSansSC-VF.ttf', 'fonts/NotoSansSC-VF.ttf'), encoding='utf-8')
p = DEST / 'rendering/renderer.py'
p.write_text(p.read_text(encoding='utf-8').replace('    font_path = Path(layout["font"]["path"])', '    font_path = Path(layout["font"]["path"])\n    if not font_path.is_absolute():\n        font_path = path.parent / font_path'), encoding='utf-8')
p = DEST / 'grading/codex_sol_grader.py'
p.write_text(p.read_text(encoding='utf-8').replace('"USERPROFILE", "APPDATA", "LOCALAPPDATA", "CODEX_HOME",', '"USERPROFILE", "APPDATA", "LOCALAPPDATA", "CODEX_HOME",\n        "HOME", "TMPDIR", "LANG", "LC_ALL",'), encoding='utf-8')
(DEST / 'TRANSFER_NOTES.json').write_text(json.dumps({'excluded': skipped, 'changes': ['Bundled original pinned Chinese font and OFL licence.', 'Resolved relative fonts against layout directory.', 'Retained Mac HOME/TMPDIR/locale in grading subprocess environment.'], 'saved_work': 'All non-temporary jobs, outputs, scans and backups retained unchanged. Old absolute paths in historical records intentionally preserved; destination Codex must assess resume compatibility.'}, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Prepared {DEST}')
