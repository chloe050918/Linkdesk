#!/bin/bash
set -e
cd "$(dirname "$0")"
python3 - <<'PY'
import json,urllib.request,subprocess,sys,time
from pathlib import Path
root=Path.cwd();url='http://127.0.0.1:8850'
try:
 with urllib.request.urlopen(url+'/health',timeout=2) as r:status=json.load(r)
 if status.get('app')!='linkdesk':raise RuntimeError('端口 8850 已被其他服务使用。')
except (OSError,urllib.error.URLError):
 (root/'data').mkdir(exist_ok=True)
 with (root/'data'/'server.log').open('ab') as log:
  subprocess.Popen([sys.executable,str(root/'server.py'),'--port','8850'],cwd=root,stdout=log,stderr=log,start_new_session=True)
 for _ in range(30):
  time.sleep(.2)
  try:
   with urllib.request.urlopen(url+'/health',timeout=1) as r:status=json.load(r)
   if status.get('app')=='linkdesk':break
  except OSError:pass
 else:raise SystemExit('服务启动失败，请查看 data/server.log。')
print('Linkdesk 已启动：'+url)
subprocess.run(['open',url],check=False)
PY
