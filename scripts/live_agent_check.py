"""Opt-in live acceptance check. Uses the configured paid model and local browser.
Run with: .venv/bin/python scripts/live_agent_check.py --base http://127.0.0.1:8860
Only synthetic materials are used. Output contains no credentials.
"""
import argparse, json, time, urllib.request, urllib.error
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--base',default='http://127.0.0.1:8860');args=parser.parse_args()
BASE=args.base
OUT=Path(__file__).resolve().parents[1]/'data'/'agent'/'live-check.json';OUT.parent.mkdir(parents=True,exist_ok=True)
report={'started_at':time.strftime('%Y-%m-%dT%H:%M:%S'),'cases':[]}
def req(path,body=None):
    raw=json.dumps(body,ensure_ascii=False).encode() if body is not None else None
    r=urllib.request.Request(BASE+'/api'+path,data=raw,headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(r,timeout=180) as f:return json.load(f)
    except urllib.error.HTTPError as e:raise RuntimeError(str(e.code)+' '+e.read().decode())
def wait(sid):
    until=time.monotonic()+600
    while time.monotonic()<until:
        s=req('/sessions/'+sid)
        if s['status']!='running':
            if s['status']=='error':raise RuntimeError(s['messages'][-1]['content'])
            return s
        time.sleep(2)
    raise TimeoutError('Case exceeded 600 seconds')
def run(sample,skill=None):
    s=req('/sessions',{'sample':sample,'skill_id':skill});sid=s['id']
    print('START',sample,sid,flush=True)
    req('/sessions/'+sid+'/chat',{'text':'请开始查证，阅读索引里的来源链接，核对当前日期与授权范围，分别提交集团、代理、预算决策三个维度的标签草稿。'})
    s=wait(sid);p=s.get('proposal');assert p,'No actual label proposal'
    row={'sample':sample,'session_id':sid,'labels':{d:p[d]['value'] for d in ('group','agency','budget')},'sources':len(s['sources']),'model_calls':sum(e['type']=='model_call' for e in s['events']),'tool_calls':sum(e['type']=='tool_start' for e in s['events']),'skill_id':skill}
    assert row['sources']>=2,'Agent did not inspect multiple sources'
    assert row['model_calls']>=1
    if skill:assert any(e['type']=='skill_used' and e['skill_id']==skill for e in s['events'])
    for d in ('group','agency','budget'):
        for e in p[d]['evidence']:assert req('/sources/'+e['source_id'])['session_id']==sid,'Old-case source reused'
    report['cases'].append(row);OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2));print('RESULT',json.dumps(row,ensure_ascii=False),flush=True);return s
try:
    health=req('/health');assert health['browser_ready'] and health['model']['configured'];report['model']=health['model']['model']
    first=run('agency');assert first['proposal']['agency']['value']=='confirmed';assert first['proposal']['group']['value']=='unknown';assert first['proposal']['budget']['value']=='unknown'
    sid=first['id']
    # A real expert correction is preserved in chat and method extraction.
    req('/sessions/'+sid+'/chat',{'text':'请在草稿中明确我的核验边界：共同 IP 和同 App 只用来发现线索，不能认定同集团。代理授权要核对主体、授权范围和有效期；过期材料不能证明当前代理关系。预算谁最终审批没有证据就保留未知，不需要阻止代理关系先确认。请重新生成草稿。'})
    first=wait(sid);assert first['proposal']['agency']['value']=='confirmed'
    req('/sessions/'+sid+'/review',{'proposal_id':first['proposal']['id'],'note':'已核对合成授权原文：有效期内的广告代投。共享投放信号不证明集团关系，预算审批未知。过期授权需重新核实。'})
    print('DISTILL',flush=True)
    sk=req('/sessions/'+sid+'/distill',{'instruction':'保留专家明确的边界，方法需适用于新公司，不复制旧案例名称、证据和结论。'})
    assert sk['status']=='draft';assert 'stop_conditions' in sk['spec']
    for company in first['companies']:assert company not in json.dumps(sk['spec'],ensure_ascii=False),'Method copied company'
    sk=req('/skills/'+sk['id']+'/status',{'status':'active'});report['skill_id']=sk['id'];report['skill_spec']=sk['spec'];OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2));print('SKILL',sk['id'],flush=True)
    transfer=run('transfer',sk['id']);assert transfer['proposal']['agency']['value']=='confirmed';assert transfer['proposal']['group']['value']=='unknown'
    expired=run('expired',sk['id']);assert expired['proposal']['agency']['value']=='unknown','Expired document incorrectly confirmed current agency'
    conflict=run('conflict',sk['id']);assert conflict['proposal']['group']['value']=='same_group';assert conflict['proposal']['agency']['value']=='confirmed';assert conflict['proposal']['budget']['value']=='unknown'
    report['passed']=True
except Exception as e:
    report['passed']=False;report['error']=str(e);raise
finally:
    report['finished_at']=time.strftime('%Y-%m-%dT%H:%M:%S');OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2));print('REPORT',str(OUT),flush=True)
