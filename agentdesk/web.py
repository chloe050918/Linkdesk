import asyncio, json, hashlib, os, re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from . import store, runtime, provider, samples
from .browser import pool

@asynccontextmanager
async def lifespan(app):
    store.init();await pool.start()
    yield
    for t in list(runtime.TASKS.values()):t.cancel()
    await pool.close()

app=FastAPI(title='Linkdesk Agent Workspace',lifespan=lifespan,docs_url=None,redoc_url=None)

@app.middleware('http')
async def local_only(request,call_next):
    host=request.url.hostname
    if host not in ('127.0.0.1','localhost','testserver'):return JSONResponse({'error':'仅允许本机访问'},403)
    origin=request.headers.get('origin')
    if origin and urlsplit(origin).netloc!=request.url.netloc:return JSONResponse({'error':'不允许跨站请求'},403)
    if request.method in ('POST','PUT','PATCH'):
        if int(request.headers.get('content-length','0'))>10_000_000:return JSONResponse({'error':'文件或请求过大'},413)
        if not any(x in request.headers.get('content-type','') for x in ('application/json','multipart/form-data')):return JSONResponse({'error':'需要 JSON 或文件请求'},415)
    try:r=await call_next(request)
    except ValueError as e:return JSONResponse({'error':str(e)},400)
    except Exception:return JSONResponse({'error':'操作未完成，请稍后重试。'},500)
    r.headers['X-Content-Type-Options']='nosniff'
    r.headers['Referrer-Policy']='no-referrer'
    if not request.url.path.startswith('/sample-site/'):
        r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return r

@app.exception_handler(ValueError)
async def bad(request,exc):return JSONResponse({'error':str(exc)},400)
@app.exception_handler(RuntimeError)
async def runtime_error(request,exc):return JSONResponse({'error':str(exc)},502)

@app.get('/')
async def home():return FileResponse(store.ROOT/'web-agent'/'index.html')
app.mount('/assets',StaticFiles(directory=store.ROOT/'web-agent'),name='assets')

@app.get('/api/health')
async def health():return {'ok':True,'browser_ready':bool(pool.browser),'model':provider.public_settings()}
@app.get('/api/settings')
async def settings():return provider.public_settings()
@app.post('/api/settings')
async def config(request:Request):
    b=await request.json();old=provider.settings()
    base=str(b.get('base_url',old['base_url'])).rstrip('/')
    if base not in ('https://api.openai.com/v1','https://ark.cn-beijing.volces.com/api/v3'):raise ValueError('支持 OpenAI 官方与火山方舟北京接入点')
    model=str(b.get('model','')).strip();key=str(b.get('key','')).strip() or old['key']
    if not model or not key or any('\n' in x or '\r' in x for x in (model,key)):raise ValueError('请填写有效模型和密钥')
    cfg={'LINKDESK_PROVIDER':'ark' if 'volces.com' in base else 'openai','LINKDESK_BASE_URL':base,'LINKDESK_MODEL':model,'LINKDESK_API_KEY':key}
    path=store.ROOT/'.env.local';path.write_text('\n'.join(k+'='+v for k,v in cfg.items())+'\n');os.chmod(path,0o600)
    return provider.public_settings()
@app.post('/api/settings/test')
async def check_model():
    msg,meta=await provider.completion([{'role':'user','content':'Reply exactly LINKDESK_OK.'}]);return {'ok':'LINKDESK_OK' in (msg.get('content') or ''),**meta}
@app.get('/api/samples')
async def sample_list(request:Request):
    pool.origin=str(request.base_url).rstrip('/')
    return samples.catalog(pool.origin)
@app.get('/sample-site/{case}/{document}')
async def sample_page(case:str,document:str):
    if case not in samples.CASES:raise ValueError('案例不存在')
    return HTMLResponse(samples.page(case,document))

@app.get('/api/sessions')
async def sessions():return [{k:s.get(k) for k in ('id','title','status','created_at','updated_at','sample','skill_id')} for s in store.listing('session') if not s.get('archived')]
@app.post('/api/sessions')
async def create(request:Request):
    b=await request.json();pool.origin=str(request.base_url).rstrip('/')
    sample=b.get('sample')
    if sample:
        if sample not in samples.CASES:raise ValueError('案例不存在')
        c=samples.CASES[sample]
        s=store.new_session(c['title'],'核验两家公司当前的集团、代理和预算决策关系，检查初筛同集团标签是否有依据。',c['companies'],[pool.origin+'/sample-site/'+sample+'/overview'],sample)
    else:
        title=str(b.get('title','')).strip()[:120];task=str(b.get('task','')).strip()[:6000]
        if not title or not task:raise ValueError('请填写案例名称和核验任务')
        urls=b.get('urls',[])
        if not isinstance(urls,list) or len(urls)>8:raise ValueError('最多添加 8 个来源 URL')
        for url in urls:await pool.safe_url(url)
        companies=b.get('companies',[])
        if not isinstance(companies,list):raise ValueError('主体格式不正确')
        s=store.new_session(title,task,companies,urls)
    if b.get('skill_id'):
        sk=store.get(b['skill_id'],'skill')
        if sk['status']!='active':raise ValueError('先启用该方法')
        s['skill_id']=sk['id'];store.save('session',s)
    return s
@app.get('/api/sessions/{sid}')
async def session(sid:str):
    s=store.get(sid,'session');s['events']=store.events(sid)
    s['source_list']=[{k:d.get(k) for k in ('id','title','url','at','actor','kind','sha256')} for d in [store.get(x,'source') for x in s['sources']]]
    return s
@app.post('/api/sessions/{sid}/chat')
async def chat(sid:str,request:Request):
    b=await request.json();text=str(b.get('text','')).strip()
    if not text or len(text)>12000:raise ValueError('请输入 1 至 12000 字的指令')
    store.get(sid,'session');runtime.start(sid,text);return {'started':True}
@app.post('/api/sessions/{sid}/pause')
async def pause(sid:str):await runtime.stop(sid);return {'paused':True}
@app.post('/api/sessions/{sid}/browser')
async def browser(sid:str,request:Request):
    s=store.get(sid,'session')
    if s['status']=='running':raise ValueError('先暂停 Agent 再接管浏览器')
    b=await request.json();return await pool.action(sid,b['action'],b.get('args',{}),'expert')
@app.get('/api/sources/{id}')
async def source(id:str):return store.get(id,'source')
@app.get('/api/screenshots/{filename}')
async def screenshot(filename:str):
    if not re.fullmatch('src-[a-f0-9]{12}\\.png',filename):raise ValueError('截图不存在')
    p=store.DATA/'screenshots'/filename
    if not p.exists():raise ValueError('截图不存在')
    return FileResponse(p)
@app.post('/api/sessions/{sid}/citation')
async def cite(sid:str,request:Request):
    b=await request.json();src=runtime.source_owned(sid,b['source_id']);q=str(b.get('quote','')).strip()
    if len(q)<8 or q not in src['text']:raise ValueError('请选择来源中的连续原文（至少 8 字）')
    note=str(b.get('note','')).strip()[:2000]
    store.event(sid,'citation','专家引用证据',actor='expert',source_id=src['id'],quote=q,note=note)
    store.message(sid,'user',f'我选中了来源 {src["id"]} 的证据：“{q}”。补充判断：{note}')
    return {'saved':True}
@app.post('/api/sessions/{sid}/review')
async def review(sid:str,request:Request):
    b=await request.json();s=store.get(sid,'session')
    if s['status']=='running':raise ValueError('先暂停 Agent 或等待本轮结束')
    if not s.get('proposal'):raise ValueError('先完成查证并生成标签草稿')
    if b.get('proposal_id')!=s['proposal']['id']:raise ValueError('草稿已更新，请刷新后确认')
    note=str(b.get('note','')).strip()
    if not note:raise ValueError('请填写确认依据或需要保留的边界')
    proposal=runtime.validate_proposal(sid,s['proposal']);proposal['id']=s['proposal']['id']
    review=dict(id=store.uid('review'),proposal_id=proposal['id'],at=store.now(),note=note,labels={d:proposal[d]['value'] for d in runtime.LABELS})
    store.patch_session(sid,review=review);store.event(sid,'review','专家已确认本案结果',actor='expert',review=review)
    return review
@app.post('/api/sessions/{sid}/upload')
async def upload(sid:str,file:UploadFile=File(...)):
    store.get(sid,'session');raw=await file.read(8_000_001)
    if len(raw)>8_000_000:raise ValueError('文件最多 8 MB')
    name=Path(file.filename or '材料.txt').name
    if name.lower().endswith('.pdf'):
        import io
        from pypdf import PdfReader
        text='\n'.join((p.extract_text() or '') for p in PdfReader(io.BytesIO(raw)).pages[:80])
    elif name.lower().endswith(('.txt','.md','.csv','.json')):text=raw.decode('utf-8-sig')
    else:raise ValueError('支持 TXT、MD、CSV、JSON、文字型 PDF')
    if not text.strip():raise ValueError('未提取到文字，请上传文字型文件')
    text=text[:100000];d=dict(id=store.uid('src'),session_id=sid,title=name,url='upload:'+name,text=text,links=[],at=store.now(),sha256=hashlib.sha256(text.encode()).hexdigest(),actor='expert',kind='upload')
    store.save('source',d)
    with store.LOCK:
        s=store.get(sid,'session');s['sources'].append(d['id']);store.save('session',s)
    store.event(sid,'upload','补充材料：'+name,source_id=d['id']);return d
@app.get('/api/skills')
async def skills():return [s for s in store.listing('skill') if not s.get('archived')]
@app.post('/api/sessions/{sid}/distill')
async def distill(sid:str,request:Request):
    b=await request.json();existing=store.get(b['skill_id'],'skill') if b.get('skill_id') else None
    if existing and existing['source_session']!=sid:raise ValueError('请从原始来源案例修订方法')
    return await runtime.distill(sid,str(b.get('instruction',''))[:5000],existing)
@app.post('/api/skills/{id}/edit')
async def edit_skill(id:str,request:Request):
    sk=store.get(id,'skill');b=await request.json();spec=b.get('spec',{})
    for k in ('name','purpose','learning_summary'):
        if not isinstance(spec.get(k),str) or not spec[k].strip() or len(spec[k])>3000:raise ValueError('方法文本不完整')
    for k in ('when_to_use','steps','checks','stop_conditions','not_allowed'):
        if not isinstance(spec.get(k),list) or not 1<=len(spec[k])<=20 or not all(isinstance(x,str) and 0<len(x)<=2000 for x in spec[k]):raise ValueError('方法条件不完整')
    updated=dict(sk,id=store.uid('skill'),spec=spec,status='draft',version=sk['version']+1,parent_id=sk['id'],created_at=store.now())
    store.save('skill',updated);store.event(sk['source_session'],'skill_edited','专家修订了查证方法',actor='expert',skill_id=updated['id'],parent_id=sk['id'])
    return updated

@app.post('/api/skills/{id}/status')
async def skill_status(id:str,request:Request):
    b=await request.json();sk=store.get(id,'skill')
    if b.get('status') not in ('active','disabled'):raise ValueError('状态不合法')
    s=store.get(sk['source_session'],'session')
    if b['status']=='active' and (not s.get('review') or s['review']['proposal_id']!=sk['source_proposal']):raise ValueError('来源案例已变化，需重新确认和提炼')
    sk['status']=b['status'];store.save('skill',sk);return sk
@app.get('/api/skills/{id}/export')
async def export_skill(id:str):
    sk=store.get(id,'skill');p=sk['spec']
    text='---\nname: '+json.dumps(p['name'],ensure_ascii=False)+'\ndescription: '+json.dumps(p['purpose'],ensure_ascii=False)+'\n---\n\n# '+p['name']+'\n\n'
    for k,label in [('when_to_use','适用范围'),('steps','查证步骤'),('checks','验收条件'),('stop_conditions','停止与转人工'),('not_allowed','禁止推导')]:text+='## '+label+'\n\n'+'\n'.join('- '+x for x in p[k])+'\n\n'
    return Response(text,media_type='text/markdown',headers={'Content-Disposition':'attachment; filename="SKILL.md"'})
@app.get('/api/sessions/{sid}/export')
async def export_case(sid:str):
    s=await session(sid);s['sources_full']=[store.get(x,'source') for x in s['sources']]
    return Response(json.dumps(s,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="case-trace.json"'})
