#!/usr/bin/env python3
"""Package repository sources; exclude local databases, credentials and caches."""
from pathlib import Path
import zipfile
root=Path(__file__).resolve().parents[1]
out=root.parent/'Linkdesk-project.zip'
excluded={'data','__pycache__','.git','.DS_Store','verification'}
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
 for p in sorted(root.rglob('*')):
  rel=p.relative_to(root)
  if not p.is_file() or any(part in excluded for part in rel.parts):continue
  if p.name.startswith('.env') and p.name!='.env.example':continue
  if p.suffix in ('.pyc','.zip','.sqlite3','.log'):continue
  archive.write(p,Path('Linkdesk')/rel)
with zipfile.ZipFile(out) as archive:
 assert archive.testzip() is None
print(out)
