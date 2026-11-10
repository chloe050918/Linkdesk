import json, sqlite3, threading, uuid, os
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv('LINKDESK_DATA', str(ROOT / 'data' / 'agent')))
LOCK = threading.RLock()

def now(): return datetime.now(timezone.utc).isoformat()
def uid(prefix): return prefix + '-' + uuid.uuid4().hex[:12]
def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DATA / 'workspace.sqlite3', timeout=30)
    c.execute('PRAGMA journal_mode=WAL')
    return c

def init():
    with connect() as c:
        c.execute('CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, kind TEXT, payload TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, payload TEXT)')
    for s in listing('session'):
        if s.get('status') == 'running':
            s['status']='interrupted'; save('session',s)
            event(s['id'],'interrupted','上次运行因服务重启中断。可以继续对话。')

def save(kind, obj):
    obj['updated_at']=now()
    with LOCK, connect() as c:
        c.execute('INSERT OR REPLACE INTO records VALUES (?,?,?)',(obj['id'], kind, json.dumps(obj, ensure_ascii=False)))
    return obj

def get(id, kind=None):
    with connect() as c: row=c.execute('SELECT kind,payload FROM records WHERE id=?',(id,)).fetchone()
    if not row or (kind and row[0]!=kind): raise ValueError('记录不存在')
    return json.loads(row[1])

def listing(kind):
    with connect() as c: rows=c.execute('SELECT payload FROM records WHERE kind=? ORDER BY rowid DESC',(kind,)).fetchall()
    return [json.loads(x[0]) for x in rows]

def event(sid, type, text, **data):
    payload=dict(at=now(),type=type,text=text,**data)
    with LOCK,connect() as c:
        cur=c.execute('INSERT INTO events (session_id,payload) VALUES (?,?)',(sid,json.dumps(payload,ensure_ascii=False)))
        payload['seq']=cur.lastrowid
    return payload

def events(sid, after=0):
    with connect() as c: rows=c.execute('SELECT seq,payload FROM events WHERE session_id=? AND seq>? ORDER BY seq',(sid,after)).fetchall()
    return [dict(json.loads(row[1]),seq=row[0]) for row in rows]

def patch_session(sid, **updates):
    with LOCK:
        s=get(sid,'session'); s.update(updates); return save('session',s)

def message(sid, role, content, **extra):
    with LOCK:
        s=get(sid,'session')
        s['messages'].append(dict(id=uid('msg'),role=role,content=content,at=now(),**extra))
        save('session',s)
    event(sid,'message',content[:180],role=role)

def new_session(title, task, companies, urls=None, sample=None):
    s=dict(id=uid('case'),title=title,task=task,companies=companies,urls=urls or [],sample=sample,
           status='idle',messages=[],sources=[],proposal=None,review=None,skill_id=None,
           created_at=now(),browser={},version=0)
    save('session',s);event(s['id'],'created','建立核验任务')
    return s
