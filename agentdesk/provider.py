import os, json, httpx, asyncio, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def settings():
    cfg={}
    p=ROOT/'.env.local'
    if p.exists():
        for line in p.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k,v=line.split('=',1);cfg[k.strip()]=v.strip().strip('"').strip("'")
    cfg.update({k:v for k,v in os.environ.items() if k.startswith('LINKDESK_') or k.startswith('OPENAI_')})
    return dict(provider=cfg.get('LINKDESK_PROVIDER','openai'),
                base_url=cfg.get('LINKDESK_BASE_URL',cfg.get('OPENAI_BASE_URL','https://api.openai.com/v1')).rstrip('/'),
                model=cfg.get('LINKDESK_MODEL','gpt-4.1'),
                key=cfg.get('LINKDESK_API_KEY',cfg.get('OPENAI_API_KEY','')))

def public_settings():
    c=settings();return {k:v for k,v in c.items() if k!='key'} | {'configured':bool(c['key'])}

async def completion(messages, tools=None, json_mode=False):
    cfg=settings()
    if not cfg['key']: raise RuntimeError('尚未配置模型 API。请在设置中连接模型。')
    body={'model':cfg['model'],'messages':messages,'max_tokens':4200}
    if cfg['provider']=='ark':body['thinking']={'type':'disabled'}
    if tools:body.update(tools=tools,tool_choice='auto')
    if json_mode:body['response_format']={'type':'json_object'}
    start=time.monotonic()
    async with httpx.AsyncClient(timeout=httpx.Timeout(90,connect=15)) as client:
        for attempt in range(3):
            try:
                r=await client.post(cfg['base_url']+'/chat/completions',headers={'Authorization':'Bearer '+cfg['key']},json=body)
                if r.status_code in (429,502,503,504) and attempt<2:
                    await asyncio.sleep(2**attempt); continue
                if r.status_code>=400:
                    # Deliberately do not log the key, request headers, or raw provider body.
                    raise RuntimeError('模型 API 返回 HTTP %s；请检查模型、额度或权限。'%r.status_code)
                data=r.json()
                return data['choices'][0]['message'],dict(model=data.get('model',cfg['model']),usage=data.get('usage',{}),latency_ms=round((time.monotonic()-start)*1000))
            except (httpx.TimeoutException,httpx.ConnectError) as exc:
                if attempt==2:raise RuntimeError('模型连接超时或不可达，请稍后重试。') from exc
                await asyncio.sleep(2**attempt)
