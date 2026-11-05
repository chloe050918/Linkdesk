#!/usr/bin/env python3
"""Local-only Relation Desk. Python standard library; no secrets in the client."""
import argparse, json, os, sqlite3, threading, time, uuid, mimetypes
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, unquote, parse_qs
from datetime import datetime, timezone
from copy import deepcopy
from engine import analyze, fingerprint, VERSION, LABELS, TYPES
from fixtures import seeds
from batch_fixtures import batch_seeds
import operations as ops

ROOT=Path(__file__).resolve().parent
DB=Path(os.environ.get('RELATION_DB',str(ROOT/'data'/'workspace.sqlite3')))
LOCK=threading.RLock(); JOBS={}

def now(): return datetime.now(timezone.utc).isoformat()
def connection():
    con=sqlite3.connect(DB,timeout=10); con.execute('PRAGMA journal_mode=WAL'); return con

def initialize():
    DB.parent.mkdir(parents=True,exist_ok=True)
    with connection() as con:
        con.execute('CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        con.execute('CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL)')
        for c in seeds()+batch_seeds():
            c['created_at']=now(); c['updated_at']=now()
            c['analysis']=dict(analyze(c),created_at=now())
            c['history']=[{'at':now(),'type':'created','text':'建立调查，导入初始材料。'},{'at':now(),'type':'analysis','text':'完成本地证据规则分析。','snapshot':c['analysis']}]
            con.execute('INSERT OR IGNORE INTO cases VALUES (?,?)',(c['id'],json.dumps(c,ensure_ascii=False)))

def get_case(id):
    with connection() as con: row=con.execute('SELECT payload FROM cases WHERE id=?',(id,)).fetchone()
    if not row: raise ValueError('找不到这项调查。')
    return json.loads(row[0])

def list_cases():
    with connection() as con: result=[json.loads(r[0]) for r in con.execute('SELECT payload FROM cases ORDER BY rowid')]
    order={'rel-blue':0,'rel-island':1,'rel-mist':2}
    return sorted(result,key=lambda c:(order.get(c['id'],3),c.get('created_at','')))

def save(c):
    c['updated_at']=now(); c['revision']+=1
    with connection() as con: con.execute('INSERT OR REPLACE INTO cases VALUES (?,?)',(c['id'],json.dumps(c,ensure_ascii=False)))

def save_operation(record,kind='policy'):
    with connection() as con:
        con.execute('INSERT OR REPLACE INTO operations VALUES (?,?,?)',(record['id'],kind,json.dumps(record,ensure_ascii=False)))

def operation_records(kind='policy'):
    with connection() as con:
        return [json.loads(r[0]) for r in con.execute('SELECT payload FROM operations WHERE kind=? ORDER BY rowid DESC',(kind,))]

def policy_by_id(id):
    p=next((p for p in operation_records() if p['id']==id),None)
    if not p:raise ValueError('找不到这项规则。')
    return p

def policy_view(p,cases):
    p=deepcopy(p);p['source_valid']=ops.source_valid(p,cases)
    p['effective']=p['status']=='active' and p['source_valid'] and ops.evaluation_current(p)
    p['effective_label']='已启用' if p['effective'] else '需重新核验' if p['status']=='active' else {'draft':'草稿','validated':'回归通过','disabled':'已停用'}.get(p['status'],p['status'])
    return p

def preview_result(p,cases):
    rows=ops.preview(p,cases)
    return {'rows':rows,'token':ops.digest({'policy':ops.policy_hash(p),'rows':rows}),
            'source_valid':ops.source_valid(p,cases)}

def change_policy(action,data,id=None):
    with LOCK:
        cases=list_cases()
        if action=='create':
            c=get_case(clean(data.get('source_id','')))
            r=next((r for r in reversed(c['reviews']) if r['status']=='approved' and 'agency' in r['selected']),None)
            if not r or r['fingerprint']!=fingerprint(c) or not ops.eligibility(c)[0]:
                raise ValueError('先完成一个有有效代理授权、控制关系未确认的案例复核，再沉淀规则。')
            rationale=clean(data.get('rationale',''),2000)
            if not rationale:raise ValueError('请填写这次复核得到的业务判断。')
            p=dict(id='RULE-'+uuid.uuid4().hex[:6],name='操作重合中的代理授权检查',version=ops.POLICY_VERSION,
                source_id=c['id'],source_title=c['title'],source_review_id=r['id'],source_fingerprint=fingerprint(c),
                rationale=rationale,status='draft',created_at=now(),evaluation=None,
                history=[dict(at=now(),action='create',text='从已复核案例建立检查模板。')])
            save_operation(p);return policy_view(p,cases)
        p=policy_by_id(id)
        if action=='preview':return preview_result(p,cases)
        if action=='evaluate':
            if not ops.source_valid(p,cases):raise ValueError('来源案例已变更或撤回，请重新核验后建立新版本。')
            p['evaluation']=dict(ops.evaluate(p),at=now());p['status']='validated'
            p['history'].append(dict(at=now(),action='evaluate',text='完成固定边界回归。'))
        elif action=='activate':
            if not ops.source_valid(p,cases) or not ops.evaluation_current(p):raise ValueError('需要有效来源与当前版本的全部边界回归通过。')
            p['status']='active';p['history'].append(dict(at=now(),action='activate',text='启用复核草稿模板；不自动确认标签。'))
        elif action=='disable':
            p['status']='disabled';p['history'].append(dict(at=now(),action='disable',text='停止生成新的复核草稿；已生成草稿保留来源。'))
        elif action=='apply':
            if not policy_view(p,cases)['effective']:raise ValueError('规则未启用或依据失效，不能生成草稿。')
            preview=preview_result(p,cases)
            if data.get('token')!=preview['token']:raise ValueError('案例或材料已更新，请重新预览适用范围。')
            ids=data.get('ids')
            if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)):raise ValueError('请明确选择需要生成草稿的案例。')
            allowed={r['id'] for r in preview['rows'] if r['eligible']}
            if not set(ids)<=allowed:raise ValueError('所选案例中包含不适用项，请逐项核对。')
            changed=[]
            for cid in ids:
                c=get_case(cid);c['prepared']=dict(ops.make_draft(p,c),created_at=now())
                log(c,'prepared','应用 '+p['id']+' 生成本案复核草稿；仍需人工提交与复核。')
                c['revision']+=1;c['updated_at']=now();changed.append(c)
            p['history'].append(dict(at=now(),action='apply',text='生成 '+str(len(changed))+' 份逐案证据草稿。',case_ids=ids))
            with connection() as con:
                for c in changed:con.execute('INSERT OR REPLACE INTO cases VALUES (?,?)',(c['id'],json.dumps(c,ensure_ascii=False)))
                con.execute('INSERT OR REPLACE INTO operations VALUES (?,?,?)',(p['id'],'policy',json.dumps(p,ensure_ascii=False)))
            return {'count':len(changed),'cases':changed,'policy':policy_view(p,list_cases())}
        else:raise ValueError('不支持的规则操作。')
        save_operation(p);return policy_view(p,cases)

def log(c,type,text,**extra): c['history'].append(dict(at=now(),type=type,text=text,**extra))
def invalidate(c):
    c['archived']=False
    if c['status'] in ('待复核','已归档'): c['status']='调查中'
    for r in c['reviews']:
        if r['status'] in ('pending','approved'): r['status']='superseded'

def clean(v,limit=300):
    if not isinstance(v,str): raise ValueError('输入格式不正确。')
    v=v.strip()
    if len(v)>limit: raise ValueError('输入内容过长。')
    return v

def material_from(data):
    title=clean(data.get('title',''),140); body=clean(data.get('text',''),40000)
    if not title or not body: raise ValueError('请填写材料标题和正文。')
    kind=data.get('kind','note')
    if kind not in TYPES: raise ValueError('请选择有效的材料类型。')
    for key in ('date','expires'):
        if data.get(key):
            try: datetime.strptime(data[key],'%Y-%m-%d')
            except (ValueError,TypeError): raise ValueError('日期格式应为 YYYY-MM-DD。')
    return {'id':'EV-'+uuid.uuid4().hex[:7].upper(),'title':title,'text':body,'kind':kind,'source':clean(data.get('source','用户提供'),200),'date':data.get('date') or datetime.now().date().isoformat(),'expires':data.get('expires',''),'verified':data.get('verified') is True,'active':True}

def current_analysis(c):
    a=c.get('analysis')
    if not a or a['fingerprint']!=fingerprint(c): raise ValueError('材料已变化，请先重新分析，再提交复核。')
    return a

def change_case(id, action, data):
    with LOCK:
        c=get_case(id)
        if 'revision' in data and data['revision']!=c['revision']: raise ValueError('这项调查已有更新，请刷新后重试。')
        if action=='material':
            m=material_from(data); c['materials'].append(m); invalidate(c)
            log(c,'material','补充材料：'+m['title'],material_id=m['id'])
        elif action=='library':
            m=next((x for x in c['library'] if x['id']==data.get('material_id')),None)
            if not m: raise ValueError('找不到这份样例材料。')
            if any(x['id']==m['id'] for x in c['materials']): raise ValueError('这份材料已加入调查。')
            c['materials'].append(deepcopy(m)); invalidate(c); log(c,'material','补充材料：'+m['title'],material_id=m['id'])
        elif action=='toggle-material':
            m=next((x for x in c['materials'] if x['id']==data.get('material_id')),None)
            if not m: raise ValueError('材料不存在。')
            m['active']=not m.get('active',True); invalidate(c); log(c,'material',('恢复材料：' if m['active'] else '排除材料：')+m['title'])
        elif action=='verify-material':
            m=next((x for x in c['materials'] if x['id']==data.get('material_id')),None)
            if not m: raise ValueError('材料不存在。')
            m['verified']=not m['verified']; invalidate(c); log(c,'material',('核对来源：' if m['verified'] else '撤销来源核对：')+m['title'])
        elif action=='task':
            dim=data.get('dimension'); a=current_analysis(c)
            gap=next((x for x in a['gaps'] if x['dimension']==dim),None)
            if not gap: raise ValueError('该维度目前没有待补事项。')
            if any(t['dimension']==dim and t['status']=='open' for t in c['tasks']): raise ValueError('已建立该补证任务。')
            task=dict(id='TK-'+uuid.uuid4().hex[:6],dimension=dim,owner=clean(data.get('owner',gap['owner'])),question=gap['question'],status='open',created_at=now())
            c['tasks'].append(task); log(c,'task','建立补证任务：'+gap['question'],task_id=task['id'])
        elif action=='task-response':
            t=next((t for t in c['tasks'] if t['id']==data.get('task_id')),None)
            if not t or t['status']!='open': raise ValueError('补证任务已关闭或不存在。')
            answer=clean(data.get('answer',''),4000)
            if not answer: raise ValueError('请填写补充说明或选择暂时无法补充。')
            t.update(answer=answer,status='answered',answered_at=now())
            # A response is a lead, not silently promoted to verified direct evidence.
            m=material_from({'title':'补证回复 · '+t['owner'],'text':answer,'kind':'note','source':t['owner'],'verified':False})
            c['materials'].append(m); invalidate(c); log(c,'task','收到补证回复；作为待核对业务说明保存。',task_id=t['id'])
        elif action=='submit':
            a=current_analysis(c); rationale=clean(data.get('rationale',''),2000)
            selected=data.get('selected',[])
            if not isinstance(selected,list) or any(d not in LABELS for d in selected): raise ValueError('复核维度无效。')
            if not rationale: raise ValueError('请填写复核说明。')
            if not selected: raise ValueError('至少选择一项有直接证据支持的关系；证据不足时请保存待补证。')
            if any(a['dimensions'][d]['value'] in ('unknown','conflict') for d in selected): raise ValueError('所选关系存在冲突或证据不足，暂不能确认。')
            if any(r['status']=='pending' for r in c['reviews']): raise ValueError('已有待复核记录。')
            review={'id':'RV-'+uuid.uuid4().hex[:6],'status':'pending','at':now(),'selected':selected,'rationale':rationale,'analysis':deepcopy(a),'submitted_by':clean(data.get('name','资料整理员')),'fingerprint':a['fingerprint']}
            c['reviews'].append(review); c['status']='待复核'; log(c,'submit','提交 '+str(len(selected))+' 项关系复核；其余维度保留未确认。')
        elif action in ('approve','return','revoke'):
            r=next((r for r in reversed(c['reviews']) if r['status'] in ('pending','approved')),None)
            if not r: raise ValueError('没有可处理的复核记录。')
            note=clean(data.get('note',''),2000); name=clean(data.get('name','业务复核员'))
            if not note: raise ValueError('请填写处理意见。')
            if action=='approve':
                if r['status']!='pending': raise ValueError('这条记录已处理。')
                if name==r['submitted_by']: raise ValueError('请使用不同的复核人姓名。')
                if r['fingerprint']!=fingerprint(c): raise ValueError('材料已变化，请重新分析并提交。')
                r.update(status='approved',reviewed_at=now(),reviewed_by=name,note=note); c['status']='已归档'; c['archived']=True
            elif action=='return':
                if r['status']!='pending': raise ValueError('仅待复核记录可以退回。')
                r.update(status='returned',reviewed_at=now(),reviewed_by=name,note=note); c['status']='调查中'
            else:
                if r['status']!='approved': raise ValueError('仅已归档记录可以撤回。')
                r.update(status='revoked',revoked_at=now(),revoked_by=name,revoke_note=note); c['status']='调查中'; c['archived']=False
            log(c,action,{'approve':'复核通过，保存关系档案。','return':'退回补充：','revoke':'撤回关系档案：'}[action]+('' if action=='approve' else note),review_id=r['id'])
        elif action=='park':
            note=clean(data.get('note',''),1000)
            if not note: raise ValueError('请注明待核验事项。')
            if c['status'] in ('待复核','已归档'): raise ValueError('请先处理或撤回复核记录。')
            c['status']='待补证'; log(c,'park','保留待补证：'+note)
        else: raise ValueError('不支持的操作。')
        save(c); return c

def run_analysis(jobid,id,mode,snapshot):
    try:
        JOBS[jobid].update(stage='核对材料与适用范围',progress=20)
        time.sleep(.25)
        JOBS[jobid].update(stage='提取可引用的关系陈述',progress=45)
        result=analyze(snapshot,mode)
        JOBS[jobid].update(stage='校验引用与证据适用性',progress=85)
        time.sleep(.25)
        with LOCK:
            c=get_case(id)
            if fingerprint(c)!=fingerprint(snapshot): raise ValueError('分析期间材料已变化，本次结果未保存。请重新分析。')
            result['created_at']=now()
            old=c.get('analysis'); changes=[]
            if old:
                for d in LABELS:
                    before=old['dimensions'][d]['label']; after=result['dimensions'][d]['label']
                    if before!=after: changes.append({'dimension':d,'before':before,'after':after})
            result['changes']=changes
            if changes and any(r['status'] in ('approved','pending') for r in c['reviews']):
                invalidate(c)
                log(c,'analysis-change','重新分析改变关系判断，旧复核已失效。')
            c['analysis']=result; log(c,'analysis','完成'+('在线模型' if mode=='online' else '本地证据规则')+'分析。',snapshot=deepcopy(result))
            save(c)
        JOBS[jobid].update(status='done',progress=100,stage='分析完成',case=c)
    except Exception as e:
        JOBS[jobid].update(status='failed',error=str(e) if isinstance(e,ValueError) else '分析失败，请稍后重试。')

def export_md(c):
    lines=['# 客户关系核验档案', '', '**样例工作区 · 虚构数据 · 未连接业务系统**','', '调查：'+c['title'],'问题：'+c['question'],'核验日期：'+c['as_of'],'当前状态：'+c['status'],'']
    a=c.get('analysis')
    if a:
        stale=a['fingerprint']!=fingerprint(c)
        lines+=['## 分析建议'+('（材料已变化，需重新分析）' if stale else ''),a['headline'],a['summary'],'']
        for d,v in a['dimensions'].items():
            lines+=['- '+{'group':'集团关系','agency':'代理合作','budget':'预算决策'}[d]+'：'+v['label']]
            for claim in v['claims']: lines+=['  - '+claim['material_id']+'：'+claim['quote']+'；'+claim['detail']+'；适用范围：'+claim['scope']]
        lines+=['','分析方式：'+a['mode']+' / '+a['version'],'']
    lines+=['## 复核记录']
    for r in c['reviews']:
        lines+=['- '+r['id']+' / '+r['status']+' / '+r['at'], '  - 提交人：'+r['submitted_by']+'；意见：'+r['rationale'], '  - 复核人：'+r.get('reviewed_by','未复核')+'；意见：'+r.get('note','')]
    lines+=['','## 来源材料']
    for m in c['materials']: lines+=['','### '+m['id']+' '+m['title'],'来源：'+m['source']+'；日期：'+m['date']+'；'+('已核对来源' if m['verified'] else '来源待核对')+'；'+('纳入' if m.get('active',True) else '已排除'),'',m['text']]
    lines+=['','## 操作记录']
    for h in c['history']: lines+=['- '+h['at']+' '+h['text']]
    return '\n'.join(lines)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args): pass
    def send_json(self,value,status=200):
        body=json.dumps(value,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        p=urlsplit(self.path).path
        try:
            if p=='/api/bootstrap': return self.send_json({'cases':list_cases(),'online_available':all(os.getenv(k) for k in ('RELATION_LLM_BASE_URL','RELATION_LLM_API_KEY','RELATION_LLM_MODEL')),'version':VERSION})
            if p=='/api/operations':
                q=parse_qs(urlsplit(self.path).query);cases=list_cases()
                return self.send_json({'queue':ops.queue(cases,int(q.get('budget',['4'])[0]),q.get('seed',['review-01'])[0]),
                    'policies':[policy_view(x,cases) for x in operation_records()],
                    'plans':operation_records('plan')[:10]})
            if p.startswith('/api/policies/') and p.endswith('/export'):
                record=policy_by_id(p.split('/')[3]);raw=json.dumps(record,ensure_ascii=False,indent=2).encode()
                self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Content-Disposition','attachment; filename="'+record['id']+'.json"');self.end_headers();self.wfile.write(raw);return
            if p.startswith('/api/jobs/'):
                job=JOBS.get(p.rsplit('/',1)[-1]); return self.send_json(job or {'error':'任务不存在'},200 if job else 404)
            if p.startswith('/api/cases/'):
                parts=p.split('/'); c=get_case(parts[3])
                if len(parts)==5 and parts[4]=='export':
                    fmt=urlsplit(self.path).query
                    if fmt=='format=md': raw=export_md(c).encode(); mime='text/markdown; charset=utf-8'; ext='md'
                    else: raw=json.dumps(c,ensure_ascii=False,indent=2).encode(); mime='application/json'; ext='json'
                    self.send_response(200); self.send_header('Content-Type',mime); self.send_header('Content-Disposition','attachment; filename="'+c['id']+'.'+ext+'"'); self.end_headers(); self.wfile.write(raw); return
                if len(parts)==4: return self.send_json(c)
            if p=='/health': return self.send_json({'ok':True,'app':'linkdesk'})
            if p=='/project/README.md':
                raw=(ROOT/'README.md').read_bytes();self.send_response(200);self.send_header('Content-Type','text/plain; charset=utf-8');self.end_headers();self.wfile.write(raw);return
            if p.startswith('/project-assets/'):
                f=ROOT/'screenshots'/unquote(p.rsplit('/',1)[-1])
                if f.resolve().parent!=ROOT/'screenshots' or f.suffix not in ('.png','.jpg','.svg'):return self.send_json({'error':'Not found'},404)
            elif p.startswith('/sample-materials/'):
                f=ROOT/unquote(p.lstrip('/'))
                if f.resolve().parent!=ROOT/'sample-materials': return self.send_json({'error':'Not found'},404)
            else:
                f=ROOT/'static'/('index.html' if p=='/' else unquote(p.lstrip('/')))
                if not f.resolve().is_relative_to(ROOT/'static'): return self.send_json({'error':'Not found'},404)
            if not f.is_file(): return self.send_json({'error':'Not found'},404)
            raw=f.read_bytes(); self.send_response(200); self.send_header('Content-Type',(mimetypes.guess_type(str(f))[0] or 'application/octet-stream')+('; charset=utf-8' if f.suffix in ('.html','.css','.js','.txt') else '')); self.send_header('Cache-Control','no-cache'); self.end_headers(); self.wfile.write(raw)
        except ValueError as e: self.send_json({'error':str(e)},404)
        except Exception: self.send_json({'error':'读取失败'},500)
    def do_POST(self):
        # Same-origin and JSON guard protects the local service from other websites.
        origin=self.headers.get('Origin')
        host=self.headers.get('Host','')
        if host not in ('127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)) or (origin and origin not in ('http://'+host,)):
            return self.send_json({'error':'请求来源不匹配'},403)
        if not self.headers.get('Content-Type','').startswith('application/json'): return self.send_json({'error':'需要 JSON 请求'},415)
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n>1000000: return self.send_json({'error':'文件过大'},413)
            data=json.loads(self.rfile.read(n)); p=urlsplit(self.path).path
            if not isinstance(data,dict): raise ValueError('请求格式不正确。')
            if p=='/api/policies':return self.send_json(change_policy('create',data),201)
            if p.startswith('/api/policies/'):
                parts=p.split('/')
                if len(parts)!=5:raise ValueError('规则路径无效。')
                return self.send_json(change_policy(parts[4],data,parts[3]))
            if p=='/api/review-plans':
                q=ops.queue(list_cases(),int(data.get('budget',4)),clean(data.get('seed','review-01')))
                record={'id':'PLAN-'+uuid.uuid4().hex[:6],'at':now(),'budget':q['budget'],'seed':q['seed'],'selected':q['selected']}
                save_operation(record,'plan');return self.send_json(record,201)
            if p=='/api/cases':
                a=clean(data.get('a','')); b=clean(data.get('b','')); q=clean(data.get('question',''),1000)
                if not a or not b or a==b or not q: raise ValueError('请填写两个不同的公司主体和调查问题。')
                c=dict(id='rel-'+uuid.uuid4().hex[:8],title=a+' × '+b,a=a,b=b,question=q,context=clean(data.get('context',''),1000),owner=clean(data.get('owner','客户经理')),region='自建',priority='关系调查',as_of=datetime.now().date().isoformat(),status='调查中',materials=[],library=[],revision=0,analysis=None,history=[],tasks=[],reviews=[],archived=False,sample=False,created_at=now())
                log(c,'created','建立调查。'); save(c); return self.send_json(c,201)
            parts=p.split('/')
            if len(parts)!=5 or parts[1:3]!=['api','cases']: return self.send_json({'error':'Not found'},404)
            id,action=parts[3:]
            if action=='analyze':
                with LOCK:
                    c=get_case(id); mode=data.get('mode','local')
                    if mode not in ('local','online'): raise ValueError('无效的分析模式。')
                    if any(j['case_id']==id and j['status']=='running' for j in JOBS.values()): raise ValueError('分析正在进行，请稍候。')
                    if not any(m.get('active',True) for m in c['materials']): raise ValueError('请先添加一份材料。')
                    jobid=uuid.uuid4().hex; JOBS[jobid]=dict(case_id=id,status='running',stage='读取材料',progress=10)
                    threading.Thread(target=run_analysis,args=(jobid,id,mode,deepcopy(c)),daemon=True).start()
                return self.send_json({'job_id':jobid},202)
            if action=='restart':
                c=get_case(id)
                if not c.get('sample'): raise ValueError('只有样例可以重新开始。')
                seed=next((x for x in seeds()+batch_seeds() if x['id']==id),None)
                if not seed: raise ValueError('样例不存在。')
                with LOCK:
                    # Preserve the previous session as an exportable local backup.
                    backup=deepcopy(c); backup['id']=c['id']+'-backup-'+uuid.uuid4().hex[:6]
                    backup['hidden']=True; save(backup)
                    seed['revision']=c['revision']; seed['created_at']=now(); seed['analysis']=dict(analyze(seed),created_at=now()); log(seed,'created','重新建立样例调查；上次记录已本地备份。'); save(seed)
                return self.send_json(seed)
            return self.send_json(change_case(id,action,data))
        except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e: self.send_json({'error':str(e)},400)
        except Exception: self.send_json({'error':'操作未完成，请刷新后重试。'},500)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=8850); args=parser.parse_args(); initialize()
    print('Relation Desk http://127.0.0.1:'+str(args.port),flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
