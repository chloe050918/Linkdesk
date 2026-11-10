import asyncio, hashlib, tempfile, unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from agentdesk import store, runtime, provider
from agentdesk.browser import BrowserPool
from agentdesk.web import app
import httpx

class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=store.DATA;store.DATA=Path(self.tmp.name);store.init()
        self.s=store.new_session('合成核验','确认当前代理关系',['甲','乙'])
        self.src=dict(id=store.uid('src'),session_id=self.s['id'],title='授权',url='https://example.org/authorization',text='甲方授权乙方提供广告代理服务，授权有效期截至2027年12月31日。',sha256='abc',kind='web')
        store.save('source',self.src)
        self.proposal={d:dict(value='unknown',reason='证据不足',evidence=[]) for d in runtime.LABELS}
        self.proposal.update(summary='集团和预算未知',missing=['预算审批人'])
        self.proposal['agency']=dict(value='confirmed',reason='有效授权',evidence=[dict(source_id=self.src['id'],quote=self.src['text'])])
        self.modelpatch=patch.object(provider,'completion',new=AsyncMock(return_value=({'content':'{\"supported\":true,\"issues\":[]}'},{'model':'mock-test','usage':{},'latency_ms':0})));self.modelpatch.start()
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver')
    async def asyncTearDown(self):
        self.modelpatch.stop();await self.client.aclose();store.DATA=self.old;self.tmp.cleanup()
    def test_supported_quote(self):
        p=runtime.validate_proposal(self.s['id'],self.proposal);self.assertEqual(p['agency']['evidence'][0]['source_hash'],'abc')
    def test_whitespace_normalization_preserves_source(self):
        original='*\u00a0 denotes LinkedIn acquisition'
        self.assertEqual(runtime.canonical_quote(original,'*  denotes LinkedIn acquisition'),original)
        with self.assertRaises(ValueError):runtime.canonical_quote(original,'* denotes Microsoft acquisition')
    def test_fabricated_quote_rejected(self):
        self.proposal['agency']['evidence'][0]['quote']='甲乙两家公司属于同一集团控制'
        with self.assertRaises(ValueError):runtime.validate_proposal(self.s['id'],self.proposal)
    def test_cross_case_source_rejected(self):
        with self.assertRaises(ValueError):runtime.validate_proposal('other-case',self.proposal)
    def test_label_requires_evidence(self):
        self.proposal['agency']['evidence']=[]
        with self.assertRaises(ValueError):runtime.validate_proposal(self.s['id'],self.proposal)
    def test_missing_evidence_allows_unknown(self):
        self.proposal['agency']=dict(value='unknown',reason='缺授权',evidence=[])
        self.assertEqual(runtime.validate_proposal(self.s['id'],self.proposal)['agency']['value'],'unknown')
    async def test_semantic_verifier_blocks_unsupported_label(self):
        provider.completion.return_value=({'content':'{"supported":false,"issues":["过期授权不证明当前没有代理关系"]}'},{'model':'mock-test','usage':{},'latency_ms':0})
        self.proposal['agency']['value']='none'
        with self.assertRaises(ValueError):await runtime.execute(self.s['id'],'propose_labels',self.proposal)
        self.assertIsNone(store.get(self.s['id'])['proposal'])
    async def test_unknown_label_rejected(self):
        self.proposal['group']['value']='probably';
        with self.assertRaises(ValueError):runtime.validate_proposal(self.s['id'],self.proposal)
    async def test_revision_invalidates_review(self):
        store.patch_session(self.s['id'],review={'id':'old'})
        await runtime.execute(self.s['id'],'propose_labels',self.proposal)
        self.assertIsNone(store.get(self.s['id'])['review'])
    async def test_stale_review_rejected(self):
        await runtime.execute(self.s['id'],'propose_labels',self.proposal)
        r=await self.client.post('/api/sessions/'+self.s['id']+'/review',json={'proposal_id':'old','note':'已核实'})
        self.assertEqual(r.status_code,400)
    async def test_review_then_distill_required(self):
        with self.assertRaises(ValueError):await runtime.distill(self.s['id'])
    async def test_confirm_current_draft(self):
        await runtime.execute(self.s['id'],'propose_labels',self.proposal)
        p=store.get(self.s['id'])['proposal'];r=await self.client.post('/api/sessions/'+self.s['id']+'/review',json={'proposal_id':p['id'],'note':'仅能确认代理关系'})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['labels']['group'],'unknown')
    async def test_expert_citation_records_note(self):
        r=await self.client.post('/api/sessions/'+self.s['id']+'/citation',json={'source_id':self.src['id'],'quote':self.src['text'],'note':'核对授权有效期'})
        self.assertEqual(r.status_code,200);self.assertIn('有效期',store.get(self.s['id'])['messages'][-1]['content'])
    def test_restart_marks_interrupted(self):
        store.patch_session(self.s['id'],status='running');store.init();self.assertEqual(store.get(self.s['id'])['status'],'interrupted')
    async def test_private_network_rejected(self):
        pool=BrowserPool()
        for url in ['http://127.0.0.1/','http://localhost:8860/api/settings','http://169.254.169.254/latest/','file:///etc/passwd','http://user:pass@example.com']:
            with self.assertRaises(ValueError,msg=url):await pool.safe_url(url)
    async def test_only_sample_path_on_local_origin(self):
        pool=BrowserPool();self.assertTrue(await pool.safe_url(pool.origin+'/sample-site/agency/overview'))
        with self.assertRaises(ValueError):await pool.safe_url(pool.origin+'/api/settings')
    async def test_host_and_origin_guard(self):
        a=await self.client.get('/api/health',headers={'Host':'attacker.example'});b=await self.client.post('/api/sessions',headers={'Origin':'https://attacker.example'},json={})
        self.assertEqual(a.status_code,403);self.assertEqual(b.status_code,403)
    async def test_model_key_not_returned(self):
        with patch.object(provider,'settings',return_value={'provider':'ark','base_url':'https://example.com','model':'test','key':'secret-only-test'}):
            r=await self.client.get('/api/settings');self.assertNotIn('secret-only-test',r.text);self.assertTrue(r.json()['configured'])
    async def test_screenshot_path_traversal(self):
        r=await self.client.get('/api/screenshots/not-a-source.png');self.assertEqual(r.status_code,400)
    async def test_stop_waits_for_task(self):
        sid=self.s['id'];task=asyncio.create_task(asyncio.sleep(100));runtime.TASKS[sid]=task
        await runtime.stop(sid);self.assertTrue(task.done());runtime.TASKS.pop(sid,None)

if __name__=='__main__':unittest.main()
