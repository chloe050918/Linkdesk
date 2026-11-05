import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy
import operations as ops
import server
from batch_fixtures import batch_seeds

class RoutingTests(unittest.TestCase):
    def test_fixed_seed_reproduces_plan(self):
        a=ops.queue(batch_seeds(),4,'s1');b=ops.queue(batch_seeds(),4,'s1')
        self.assertEqual(a['selected'],b['selected'])
    def test_plan_reserves_one_random_audit(self):
        q=ops.queue(batch_seeds(),4,'s1')
        self.assertEqual(len(q['selected']),4)
        self.assertEqual(sum(x['selection']=='随机抽检' for x in q['selected']),1)
        self.assertEqual(len({x['id'] for x in q['selected']}),4)
    def test_conflict_and_large_bridge_first(self):
        q=ops.queue(batch_seeds(),4)
        self.assertEqual([r['id'] for r in q['selected'][:2]],['batch-08','batch-07'])
        self.assertEqual(q['rows'][0]['impact'],14)
    def test_priority_slots_diversify_before_second_pattern_case(self):
        q=ops.queue(batch_seeds(),5)
        chosen=q["selected"][:-1]
        self.assertEqual(sum(r["route"]=="模式复核" for r in chosen),1)
    def test_rule_groups_do_not_share_labels(self):
        q=ops.queue(batch_seeds());self.assertEqual(len(q['cluster']),6)
        self.assertEqual(q['eligible'],3)
        self.assertEqual(next(r for r in q['cluster'] if r['id']=='batch-06')['group'],'同一集团')
    def test_audit_can_select_non_priority_rows(self):
        choices={ops.queue(batch_seeds(),4,str(i))['selected'][-1]['id'] for i in range(30)}
        self.assertIn('batch-09',choices);self.assertIn('batch-12',choices)
    def test_archived_cases_not_scheduled(self):
        c=batch_seeds();c[7]['status']='已归档';c[7]['archived']=True
        self.assertNotIn('batch-08',[r['id'] for r in ops.queue(c)['selected']])
    def test_boundary_suite_not_all_abstain(self):
        p=dict(id='x',source_id='x',source_review_id='x',source_fingerprint='x',version=ops.POLICY_VERSION,name='x',rationale='x')
        e=ops.evaluate(p)
        self.assertEqual(e['total'],10);self.assertEqual(e['failed'],0)
        self.assertEqual(sum(r['actual'] for r in e['rows']),2)
        self.assertEqual(e['baseline_passed'],3)

class PolicyWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=server.DB;server.DB=Path(self.tmp.name)/'test.sqlite3';server.initialize()
    def tearDown(self):server.DB=self.old;self.tmp.cleanup()
    def approve_source(self):
        server.change_case('batch-01','submit',dict(selected=['agency'],rationale='按原文确认代理，集团未知。',name='初标员'))
        server.change_case('batch-01','approve',dict(name='专家',note='核对了主体、有效期和授权范围。'))
    def make_rule(self):
        self.approve_source()
        return server.change_policy('create',dict(source_id='batch-01',rationale='授权只支持代理关系，不能证明同集团。'))
    def active_rule(self):
        p=self.make_rule();server.change_policy('evaluate',{},p['id']);return server.change_policy('activate',{},p['id'])
    def test_rule_requires_approved_source(self):
        with self.assertRaises(ValueError):server.change_policy('create',dict(source_id='batch-01',rationale='test'))
    def test_rule_activation_requires_current_evaluation(self):
        p=self.make_rule()
        with self.assertRaises(ValueError):server.change_policy('activate',{},p['id'])
        server.change_policy('evaluate',{},p['id']);p=server.change_policy('activate',{},p['id'])
        self.assertTrue(p['effective'])
    def test_evaluation_tied_to_policy_hash(self):
        p=self.make_rule();p=server.change_policy('evaluate',{},p['id']);p['rationale']='changed';server.save_operation(p)
        with self.assertRaises(ValueError):server.change_policy('activate',{},p['id'])
    def test_source_change_suspends_reuse(self):
        p=self.active_rule();server.change_case('batch-01','verify-material',{'material_id':'batch-01-A'})
        self.assertFalse(server.policy_view(server.policy_by_id(p['id']),server.list_cases())['effective'])
    def test_source_revocation_suspends_reuse(self):
        p=self.active_rule();server.change_case('batch-01','revoke',dict(name='专家',note='来源需要重查'))
        self.assertFalse(server.policy_view(server.policy_by_id(p['id']),server.list_cases())['effective'])
    def test_preview_excludes_missing_expired_and_control_evidence(self):
        p=self.active_rule();v=server.change_policy('preview',{},p['id'])
        self.assertEqual([r['id'] for r in v['rows'] if r['eligible']],['batch-02','batch-03'])
    def test_batch_creates_own_evidence_drafts_not_labels(self):
        p=self.active_rule();v=server.change_policy('preview',{},p['id'])
        r=server.change_policy('apply',dict(ids=['batch-02','batch-03'],token=v['token']),p['id'])
        self.assertEqual(r['count'],2)
        for c in r['cases']:
            self.assertFalse(c['archived']);self.assertEqual(c['reviews'],[]);self.assertEqual(c['status'],'调查中')
            self.assertEqual(c['prepared']['refs'],[c['id']+'-A'])
            self.assertIn(c['a'],c['prepared']['rationale']);self.assertNotIn('青禾科技',c['prepared']['rationale'])
            self.assertEqual(c['analysis']['dimensions']['group']['value'],'unknown')
    def test_preview_staleness_blocks_apply(self):
        p=self.active_rule();v=server.change_policy('preview',{},p['id'])
        server.change_case('batch-02','verify-material',{'material_id':'batch-02-A'})
        with self.assertRaisesRegex(ValueError,'重新预览'):server.change_policy('apply',dict(ids=['batch-03'],token=v['token']),p['id'])
    def test_cannot_smuggle_ineligible_case(self):
        p=self.active_rule();v=server.change_policy('preview',{},p['id'])
        with self.assertRaises(ValueError):server.change_policy('apply',dict(ids=['batch-04'],token=v['token']),p['id'])
        self.assertNotIn('prepared',server.get_case('batch-04'))
    def test_repeating_apply_does_not_duplicate_drafts(self):
        p=self.active_rule();v=server.change_policy('preview',{},p['id'])
        server.change_policy('apply',dict(ids=['batch-02'],token=v['token']),p['id'])
        with self.assertRaises(ValueError):server.change_policy('apply',dict(ids=['batch-02'],token=v['token']),p['id'])
    def test_disabled_rule_cannot_apply(self):
        p=self.active_rule();v=server.change_policy('preview',{},p['id']);server.change_policy('disable',{},p['id'])
        with self.assertRaises(ValueError):server.change_policy('apply',dict(ids=['batch-02'],token=v['token']),p['id'])
    def test_rules_persist_after_initialize(self):
        p=self.active_rule();server.initialize();self.assertEqual(server.policy_by_id(p['id'])['status'],'active')

if __name__=='__main__':unittest.main()
