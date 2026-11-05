#!/usr/bin/env python3
"""Restore only fictional batch cases, retaining backups and policy history."""
import json,urllib.request,argparse
parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8850);args=parser.parse_args()
base=f'http://127.0.0.1:{args.port}/api/'
def get(path):return json.load(urllib.request.urlopen(base+path,timeout=10))
def post(path,data):
 req=urllib.request.Request(base+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
 return json.load(urllib.request.urlopen(req,timeout=10))
cases=[c for c in get('bootstrap')['cases'] if c.get('batch') and c.get('sample') and not c.get('hidden')]
ids={c['id'] for c in cases}
for p in get('operations')['policies']:
 if p['source_id'] in ids and p['status']!='disabled':post('policies/'+p['id']+'/disable',{})
for c in cases:post('cases/'+c['id']+'/restart',{})
print(f'已恢复 {len(cases)} 条合成批次案例。旧记录已保留；相关模板已停用。请刷新工作台。')
