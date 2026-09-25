from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'handover' / 'Mums Reading Project'
skip = {'__pycache__', 'test-workspace-temp', 'test-temp', '.venv', '.pytest_cache'}
files = [p for p in DEST.rglob('*') if p.is_file() and not any(part in skip for part in p.relative_to(DEST).parts) and p.name != 'FILE_MANIFEST.json']
changed = {'rendering/renderer.py', 'grading/codex_sol_grader.py', 'rendering/template/layout_v1.json', 'rendering/template/layout_v1_1.json', 'rendering/template/layout_v1_2.json'}
manifest = {}
matched = 0
for p in files:
    rel = p.relative_to(DEST).as_posix()
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    source = ROOT / rel
    if source.is_file() and rel not in changed:
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest, f'Source changed: {rel}'
        matched += 1
    manifest[rel] = {'bytes': p.stat().st_size, 'sha256': digest}
mf = DEST / 'FILE_MANIFEST.json'
mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
archive = ROOT / 'handover' / 'Mums-Reading-Project-Mac.zip'
with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for p in files + [mf]:
        info = zipfile.ZipInfo.from_file(p, (Path(DEST.name) / p.relative_to(DEST)).as_posix())
        info.create_system = 3
        info.external_attr = (0o100755 if p.suffix == '.sh' else 0o100644) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        with p.open('rb') as src, z.open(info, 'w', force_zip64=True) as out:
            import shutil
            shutil.copyfileobj(src, out, 1024 * 1024)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
(archive.parent / 'Mums-Reading-Project-Mac.zip.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
print(json.dumps({'archive': str(archive), 'files': len(files)+1, 'unchanged_source_files_verified': matched, 'size_MB': round(archive.stat().st_size/1e6, 1), 'sha256': digest}))
