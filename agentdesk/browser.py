import asyncio, hashlib, ipaddress, socket, json, os
from pathlib import Path
from urllib.parse import urlsplit, urljoin, quote
from playwright.async_api import async_playwright
from . import store

MAX_TEXT=30000
class BrowserPool:
    def __init__(self): self.driver=None;self.browser=None;self.pages={};self.locks={};self.origin='http://127.0.0.1:8860';self.dns={}
    async def start(self):
        self.driver=await async_playwright().start()
        options=dict(headless=True,args=['--disable-dev-shm-usage'])
        channel=os.getenv('LINKDESK_BROWSER_CHANNEL')
        if channel:options['channel']=channel
        elif Path('/Applications/Google Chrome.app').exists():
            options['channel']='chrome'
        self.browser=await self.driver.chromium.launch(**options)
    async def close(self):
        if self.browser:await self.browser.close()
        if self.driver:await self.driver.stop()
    async def safe_url(self,url):
        p=urlsplit(url)
        if p.scheme not in ('https','http') or not p.hostname or p.username or p.password:raise ValueError('仅支持公开 HTTP / HTTPS 网页')
        # Only our purpose-built sample pages may use loopback. The app API is never browsable by the agent.
        if url.startswith(self.origin+'/sample-site/') and p.netloc==urlsplit(self.origin).netloc:return url
        host=p.hostname.lower()
        if host in ('localhost','localhost.localdomain') or host.endswith(('.local','.internal')):raise ValueError('不允许访问本机或内网地址')
        if p.port and p.port not in (80,443):raise ValueError('公开网页仅支持 80/443 端口')
        if host not in self.dns:
            infos=await asyncio.get_running_loop().getaddrinfo(host,None)
            self.dns[host]={i[4][0] for i in infos}
        if not self.dns[host] or any(not ipaddress.ip_address(ip).is_global for ip in self.dns[host]):raise ValueError('不允许访问私有网络地址')
        return url
    async def get(self,sid):
        if sid not in self.pages:
            context=await self.browser.new_context(viewport={'width':1120,'height':780},accept_downloads=False,service_workers='block')
            async def route(r):
                try:
                    await self.safe_url(r.request.url)
                    if r.request.method not in ('GET','HEAD'):
                        await r.abort();return
                    await r.continue_()
                except Exception:await r.abort()
            await context.route('**/*',route)
            page=await context.new_page()
            page.on('dialog',lambda d:d.dismiss())
            context.on('page',lambda p: asyncio.create_task(p.close()) if p!=page else None)
            self.pages[sid]=page;self.locks[sid]=asyncio.Lock()
            previous=store.get(sid,'session').get('browser',{})
            if previous.get('url'):
                try:
                    await self.safe_url(previous['url'])
                    await page.goto(previous['url'],wait_until='domcontentloaded',timeout=20000)
                    await page.evaluate('(y)=>window.scrollTo(0,y)',previous.get('scroll_y',0))
                except Exception:pass
        return self.pages[sid]
    async def snapshot(self,sid,actor='agent',action='read',args=None):
        page=await self.get(sid)
        if page.url=='about:blank':return {'url':'about:blank','text':'尚未打开网页','links':[]}
        text=(await page.locator('body').inner_text(timeout=12000))[:MAX_TEXT]
        links=await page.locator('a[href]').evaluate_all('(els)=>els.filter(e=>e.innerText.trim()).slice(0,70).map(e=>({text:e.innerText.trim().slice(0,120),url:e.href}))')
        links=[l for l in links if l['url'].startswith(('http://','https://'))]
        title=await page.title();source_id=store.uid('src')
        shot=store.DATA/'screenshots'/(source_id+'.png');shot.parent.mkdir(parents=True,exist_ok=True)
        await page.screenshot(path=str(shot))
        doc=dict(id=source_id,session_id=sid,title=title,url=page.url,text=text,links=links,at=store.now(),
                 sha256=hashlib.sha256(text.encode()).hexdigest(),actor=actor,screenshot=source_id+'.png',kind='web')
        store.save('source',doc)
        with store.LOCK:
            s=store.get(sid,'session');s['sources'].append(source_id)
            s['browser']={k:doc[k] for k in ('id','title','url','screenshot','at')};s['browser']['scroll_y']=await page.evaluate('window.scrollY');store.save('session',s)
        store.event(sid,'browser',title,actor=actor,action=action,source_id=source_id,url=page.url,args=args or {})
        return {k:v for k,v in doc.items() if k not in ('session_id',)}
    async def action(self,sid,action,args,actor='agent'):
        page=await self.get(sid)
        async with self.locks[sid]:
            if action=='open_url':
                url=await self.safe_url(args['url'])
                try:
                    await page.goto(url,wait_until='domcontentloaded',timeout=35000)
                    if 'bing.com/search' in page.url:
                        try:await page.locator('#b_results .b_algo').first.wait_for(state='visible',timeout=8000)
                        except Exception:pass
                except Exception:
                    if page.url=='about:blank':raise ValueError('网页无法打开，请换一个来源')
            elif action=='click_link':
                loc=page.get_by_role('link',name=args['text'],exact=False).first
                href=await loc.get_attribute('href',timeout=6000)
                if not href:raise ValueError('没有找到这个链接')
                await self.safe_url(urljoin(page.url,href));await loc.click(timeout=12000)
                await page.wait_for_load_state('domcontentloaded',timeout=15000)
            elif action=='find_text':
                q=args['text'][:200]
                # DOM-based location; source text remains untrusted data, never code.
                loc=page.get_by_text(q,exact=False).first
                if await loc.count():await loc.scroll_into_view_if_needed(timeout=5000)
            elif action=='click':
                x=max(0,min(1119,float(args['x'])));y=max(0,min(779,float(args['y'])))
                await page.mouse.click(x,y)
                await asyncio.sleep(.3)
            elif action=='scroll':await page.mouse.wheel(0,max(-1500,min(1500,int(args.get('delta',500)))));await asyncio.sleep(.15)
            elif action=='back':await page.go_back(wait_until='domcontentloaded',timeout=15000)
            elif action=='type':await page.keyboard.insert_text(str(args['text'])[:1000])
            elif action=='key':
                key=args['key']
                if key not in ('Enter','Tab','Escape','ArrowDown','ArrowUp','Backspace'):raise ValueError('不支持该按键')
                await page.keyboard.press(key)
            elif action!='read_page':raise ValueError('未知浏览器操作')
            return await self.snapshot(sid,actor,action,args)
    async def search(self,sid,query):
        return await self.action(sid,'open_url',{'url':'https://www.bing.com/search?q='+quote(query[:400])})

pool=BrowserPool()
